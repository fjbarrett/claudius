"""Offline unit tests for the parts that don't need a model: output truncation,
the single-command parser, and the local environment. Run with:

    python3 -m unittest discover -s tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claudius.agent import parse_action, render, _FormatError  # noqa: E402
from claudius.environment import LocalEnvironment, truncate_output  # noqa: E402


class TestTruncate(unittest.TestCase):
    def test_short_output_untouched(self):
        self.assertEqual(truncate_output("hello", 10000, 5000), "hello")

    def test_long_output_keeps_both_ends(self):
        text = "A" * 4000 + "B" * 4000 + "C" * 4000  # 12k > 10k cap
        out = truncate_output(text, 10000, 5000)
        self.assertTrue(out.startswith("A" * 4000))
        self.assertTrue(out.endswith("C" * 4000))
        self.assertIn("characters elided", out)
        self.assertLess(len(out), len(text))


class TestParseAction(unittest.TestCase):
    def test_exactly_one_block(self):
        self.assertEqual(parse_action("thinking\n```bash\nls -la\n```"), "ls -la")

    def test_sh_fence_accepted(self):
        self.assertEqual(parse_action("```sh\necho hi\n```"), "echo hi")

    def test_zero_blocks_raises(self):
        with self.assertRaises(_FormatError):
            parse_action("no command here")

    def test_two_blocks_raises(self):
        with self.assertRaises(_FormatError):
            parse_action("```bash\nls\n```\n```bash\npwd\n```")


class TestRender(unittest.TestCase):
    def test_substitution(self):
        self.assertEqual(render("{{a}}-{{b}}", a=1, b="x"), "1-x")


class TestLocalEnvironment(unittest.TestCase):
    def test_run_and_returncode(self):
        with tempfile.TemporaryDirectory() as d:
            env = LocalEnvironment(d, timeout=10, output_char_limit=10000, output_keep_each_side=5000)
            ok = env.execute("echo hello")
            self.assertEqual(ok["returncode"], 0)
            self.assertIn("hello", ok["output"])
            bad = env.execute("exit 3")
            self.assertEqual(bad["returncode"], 3)

    def test_fixed_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            env = LocalEnvironment(d, timeout=10, output_char_limit=10000, output_keep_each_side=5000)
            env.execute("touch marker.txt")
            self.assertTrue((Path(d) / "marker.txt").exists())

    def test_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            env = LocalEnvironment(d, timeout=1, output_char_limit=10000, output_keep_each_side=5000)
            res = env.execute("sleep 5")
            self.assertEqual(res["returncode"], 124)
            self.assertIn("timed out", res["output"])


if __name__ == "__main__":
    unittest.main()
