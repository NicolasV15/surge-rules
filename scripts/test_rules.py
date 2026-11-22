import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import rules


class RuleTests(unittest.TestCase):
    def test_semantics_ignore_comments_and_spacing(self):
        self.assertEqual(
            rules.parse(b"# generated 2026\nDOMAIN-SUFFIX, Example.com\n", "RULE-SET"),
            rules.parse(b"DOMAIN-SUFFIX,example.com // comment\n", "RULE-SET"),
        )

    def test_reject_invalid_download(self):
        for body in (b"# empty", b"<html>error</html>", b"IP-CIDR6,192.0.2.0/24",
                     b"DOMAIN,example.org,Proxy", b"OR,((DOMAIN,example.org),(BAD,foo))"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                rules.parse(body, "RULE-SET")

    def test_update_scope_and_atomic_upstream_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tracked = {"id": "tracked", "mode": "track", "kind": "RULE-SET", "url": "https://example.org/rules"}
            frozen = dict(tracked, id="frozen", mode="manual")
            other = dict(tracked, id="other")
            original = b"DOMAIN,example.org\n"
            candidate = b"DOMAIN-SUFFIX,cn\n"
            sources = [tracked, frozen, other]
            snapshots = {source["id"]: {"sha256": hashlib.sha256(original).hexdigest()} for source in sources}
            report = root / "report.md"
            with patch.object(rules, "ROOT", root):
                for source in sources:
                    path = rules.list_path(source)
                    path.parent.mkdir(exist_ok=True, parents=True)
                    path.write_bytes(original)
                change = rules.summarize(tracked, rules.parse(original, "RULE-SET"), rules.parse(candidate, "RULE-SET"))
                self.assertIn("宽泛匹配", change[3][0])

                def failed_fetch(source):
                    if source["id"] == "other":
                        raise ValueError("empty rule list")
                    return candidate, change

                with patch.object(rules, "retrieve", side_effect=failed_fetch), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(rules.sync(sources, snapshots, report), 1)
                self.assertEqual(rules.list_path(tracked).read_bytes(), original)

                with patch.object(rules, "retrieve", return_value=(original, None)) as fetch:
                    self.assertEqual(rules.sync(sources, snapshots, report), 0)
                    self.assertEqual({call.args[0]["id"] for call in fetch.call_args_list}, {"tracked", "other"})
                self.assertIn("无变化", report.read_text())

                def success(source):
                    return (candidate, change) if source["id"] == "tracked" else (original, None)

                with patch.object(rules, "retrieve", side_effect=success):
                    self.assertEqual(rules.sync(sources, snapshots, report), 0)
                self.assertEqual(rules.list_path(tracked).read_bytes(), candidate)
                self.assertEqual(rules.list_path(frozen).read_bytes(), original)
                self.assertIn("宽泛匹配", report.read_text())


if __name__ == "__main__":
    unittest.main()
