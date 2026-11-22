"""Validate Surge lists and prepare reviewed updates from upstream snapshots."""
import argparse
from collections import Counter
import concurrent.futures
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = re.compile(r"(?=.{1,253}$)[a-z0-9_][a-z0-9_-]*(?:\.[a-z0-9_][a-z0-9_-]*)*", re.I)
SIMPLE = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD",
          "IP-CIDR", "IP-CIDR6", "IP-ASN", "GEOIP", "USER-AGENT", "PROCESS-NAME"}
FLAGS = {"no-resolve", "extended-matching"}


def list_path(source):
    return ROOT / "rules" / source["mode"] / (source["id"] + ".list")


def parse(payload, kind):
    result = []
    for number, raw in enumerate(payload.decode("utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        line = re.split(r"\s+//", line, maxsplit=1)[0].rstrip()
        try:
            result.append(normalize(line, kind))
        except ValueError as error:
            raise ValueError(f"line {number}: {error}") from error
    if not result:
        raise ValueError("empty rule list")
    return result


def normalize(line, kind):
    if kind == "DOMAIN-SET":
        if not DOMAIN.fullmatch(line.lstrip(".")) or line.startswith(".."):
            raise ValueError(f"invalid domain: {line}")
        return line.lower()
    rule, sep, body = line.partition(",")
    rule, body = rule.strip(), body.strip()
    if not sep or not body:
        raise ValueError(f"missing rule payload: {line}")
    if rule in ("AND", "OR", "NOT"):
        # These lists use the Surge logical syntax ((RULE,...),(RULE,...)).
        members = logical_members(body)
        valid_count = len(members) == 1 if rule == "NOT" else len(members) >= 2
        if not valid_count:
            raise ValueError(f"invalid number of operands: {line}")
        return rule + ",(" + ",".join("(" + normalize(member, kind) + ")" for member in members) + ")"
    if rule == "URL-REGEX":
        try:
            re.compile(body)
        except re.error as error:
            raise ValueError(f"invalid regular expression: {body}") from error
        return rule + "," + body
    if rule not in SIMPLE:
        raise ValueError(f"unknown rule type: {rule}")
    value, *options = (part.strip() for part in body.split(","))
    if not value or set(options) - FLAGS:
        raise ValueError(f"invalid value or option: {line}")
    if rule in ("DOMAIN", "DOMAIN-SUFFIX") and not DOMAIN.fullmatch(value):
        raise ValueError(f"invalid domain: {value}")
    if rule in ("IP-CIDR", "IP-CIDR6"):
        net = ipaddress.ip_network(value, strict=False)
        if net.version != (6 if rule.endswith("6") else 4):
            raise ValueError(f"address family mismatch: {value}")
        value = str(net)
    if rule == "IP-ASN" and not value.isdecimal():
        raise ValueError(f"invalid ASN: {value}")
    if rule in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD"):
        value = value.lower()
    return ",".join([rule, value, *sorted(options)])


def logical_members(body):
    if not body.startswith("((") or not body.endswith("))"):
        raise ValueError(f"invalid logical expression: {body}")
    members = []
    depth = 0
    start = 0
    escaped = False
    for position, char in enumerate(body[1:-1]):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            members.append(body[1:-1][start:position].strip())
            start = position + 1
        if depth < 0:
            raise ValueError(f"unbalanced logical expression: {body}")
    members.append(body[1:-1][start:].strip())
    if depth or any(not (part.startswith("(") and part.endswith(")")) for part in members):
        raise ValueError(f"unbalanced logical expression: {body}")
    return [member[1:-1] for member in members]


def broad(rule, kind):
    if kind == "DOMAIN-SET":
        return "." not in rule.lstrip(".")
    name, value, *_ = rule.split(",")
    if name in ("IP-CIDR", "IP-CIDR6"):
        net = ipaddress.ip_network(value)
        return net.prefixlen <= (16 if net.version == 4 else 48)
    return (name in ("IP-ASN", "GEOIP", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD")
            or name == "DOMAIN-SUFFIX" and "." not in value)


def summarize(source, before, after):
    added = Counter(after) - Counter(before)
    removed = Counter(before) - Counter(after)
    added_count = sum(added.values())
    removed_count = sum(removed.values())
    warnings = []
    if removed_count >= 5 and removed_count / len(before) >= 0.2:
        warnings.append("删除至少 20% 的规则")
    wide = [rule for rule in added if broad(rule, source["kind"])]
    if wide:
        examples = ", ".join("`" + rule.replace("`", "") + "`" for rule in wide[:5])
        warnings.append(f"新增 {len(wide)} 条宽泛匹配（{examples}）")
    if not added and not removed:
        warnings.append("规则顺序有变化")
    return source, added_count, removed_count, warnings


def retrieve(source):
    payload = subprocess.check_output(
        ["curl", "-fsSL", "--proto", "=https", "--proto-redir", "=https",
         "--retry", "2", "--max-time", "50", "--max-filesize", "30000000", source["url"]]
    )
    path = list_path(source)
    before = parse(path.read_bytes(), source["kind"])
    after = parse(payload, source["kind"])
    return payload, summarize(source, before, after) if before != after else None


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def validate(sources, snapshots):
    expected = set()
    for source in sources:
        path = list_path(source)
        if path in expected:
            raise ValueError(f"duplicate source {path}")
        expected.add(path)
        payload = path.read_bytes()
        parse(payload, source["kind"])
        if source["mode"] == "track" and snapshots[source["id"]]["sha256"] != digest(payload):
            raise ValueError(f"snapshot checksum mismatch: {path.name}")
    if expected != set((ROOT / "rules").glob("*/*.list")):
        raise ValueError("manifest and rule files differ")
    for path in (ROOT / "local").glob("*.list"):
        parse(path.read_bytes(), "RULE-SET")


def sync(sources, snapshots, report):
    changes = []
    failures = []
    tracked = [source for source in sources if source["mode"] == "track"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        pending = {pool.submit(retrieve, source): source for source in tracked}
        for future in concurrent.futures.as_completed(pending):
            try:
                payload, summary = future.result()
                if summary:
                    changes.append((payload, summary))
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                failures.append(f"{pending[future]['id']}: {error}")
    for failure in sorted(failures):
        print(f"同步失败，保留已发布版本：{failure}", file=sys.stderr)
    # Keep the entire candidate unchanged on partial upstream failure.
    if failures:
        return 1
    lines = ["每日上游规则同步。请审阅差异后合并。", "",
             "| 规则集 | 新增 | 删除 | 提醒 |", "| --- | ---: | ---: | --- |"]
    for payload, (source, added, removed, warnings) in sorted(changes, key=lambda entry: entry[1][0]["id"]):
        list_path(source).write_bytes(payload)
        snapshots[source["id"]] = {"sha256": digest(payload)}
        note = "；".join(warnings).replace("|", r"\|")
        lines.append(f"| [{source['id']}]({source['url']}) | {added} | {removed} | {note} |")
    if changes:
        (ROOT / "snapshots.json").write_text(json.dumps(snapshots, indent=2) + "\n")
        validate(sources, snapshots)
    report.write_text("\n".join(lines if changes else ["规则内容无变化。"]) + "\n")
    print(f"{len(changes)} 个规则集有变化")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["validate", "sync"])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.action == "sync" and args.report is None:
        parser.error("sync requires --report")
    sources = json.loads((ROOT / "sources.json").read_text())
    snapshots = json.loads((ROOT / "snapshots.json").read_text())
    try:
        validate(sources, snapshots)
        return sync(sources, snapshots, args.report) if args.action == "sync" else 0
    except (ValueError, OSError, KeyError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
