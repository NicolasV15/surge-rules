"""Print the public Rule lines, in the order used by the reference profile."""
import json

from rules import ROOT

BASE = "https://raw.githubusercontent.com/NicolasV15/surge-rules/main"
# Placeholders in the comments mark the insertion points for private rules.
ORDER = [
    "anti-ad", "apple", "# Insert any device-specific Apple overrides here.",
    "local/codex", "local/gemini", "claude-code", "local/ai-other",
    "github", "microsoft", "telegram", "local/wechat",
    "youtube", "bilibili", "china-media", "global-media", "google",
    "# Insert local direct/routing exceptions here.",
    "proxy", "china-asn",
    "# Insert existing China fallback, LAN and FINAL rules here.",
]
POLICY = {
    "anti-ad": "REJECT,extended-matching",
    "apple": "Apple",
    "local/codex": '"AI Platform"',
    "local/gemini": '"AI Platform"',
    "claude-code": '"AI Platform"',
    "local/ai-other": '"AI Platform"',
    "github": "Proxy",
    "microsoft": "Microsoft",
    "telegram": "Telegram",
    "local/wechat": "DIRECT,extended-matching",
    "youtube": "YouTube",
    "bilibili": "BiliBili",
    "china-media": "DIRECT",
    "global-media": "GlobalMedia",
    "google": "Google",
    "proxy": "Proxy,extended-matching",
    "china-asn": "DIRECT,extended-matching",
}


def main():
    sources = {item["id"]: item for item in json.loads((ROOT / "sources.json").read_text())}
    print("[Rule]")
    for name in ORDER:
        if name.startswith("#"):
            print(name)
            continue
        match = sources.get(name)
        kind = match["kind"] if match else "RULE-SET"
        path = f"rules/{match['mode']}/{name}" if match else name
        print(f"{kind},{BASE}/{path}.list,{POLICY[name]}")


if __name__ == "__main__":
    main()
