# -*- coding: utf-8 -*-
"""zidon 最小测试集（标准库 unittest，零依赖）。

跑法：
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from promoter import store  # noqa: E402
from promoter import release as rel  # noqa: E402


class TestStore(unittest.TestCase):
    def test_slugify_normalizes(self):
        self.assertEqual(store.slugify("Hello World"), "hello-world")
        self.assertEqual(store.slugify("v0.2.1"), "v0-2-1")
        # 连续的非字母数字会被压成单个连字符
        self.assertEqual(store.slugify("  a__b  "), "a-b")
        self.assertEqual(store.slugify("A  B"), "a-b")

    def test_safe_name_strips_separators(self):
        got = store.safe_name("release/v0.2.1")
        self.assertNotIn("/", got)
        self.assertNotIn("\\", got)

    def test_repo_root_is_project_root(self):
        self.assertTrue((store.repo_root() / "config" / "promoter.json").exists())

    def test_detect_repo_parses_github_remote(self):
        # 该仓库 origin 应为 github.com 且能解析出 owner/repo
        repo = store.detect_repo(store.repo_root())
        self.assertRegex(repo, r"^[\w.-]+/[\w.-]+$")
        self.assertIn("/", repo)


class TestRelease(unittest.TestCase):
    def test_changelog_guard_passes_for_recorded_version(self):
        ok, msg = rel.changelog_guard(store.repo_root(), "v0.2.1")
        self.assertTrue(ok, msg)

    def test_changelog_guard_blocks_missing_version(self):
        ok, msg = rel.changelog_guard(store.repo_root(), "v9.9.9")
        self.assertFalse(ok)
        self.assertIn("9.9.9", msg)

    def test_find_notes_prefers_tag_then_without_v(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "content" / "approved" / "release"
            base.mkdir(parents=True)
            (base / "v1.2.3.md").write_text("notes", encoding="utf-8")
            self.assertEqual(rel.find_notes(root, "v1.2.3"), base / "v1.2.3.md")
            self.assertIsNone(rel.find_notes(root, "v9.9.9"))

    def test_build_tarball_excludes_dist_and_pycache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("hi", encoding="utf-8")
            (root / "dist").mkdir()
            (root / "dist" / "big.bin").write_bytes(b"x" * 100)
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "a.pyc").write_bytes(b"x")
            tar = rel.build_tarball(root, "v0.0.1")
            names = []
            with tarfile.open(tar, "r:gz") as tf:
                names = tf.getnames()
            self.assertTrue(any(n.endswith("a.txt") for n in names), names)
            self.assertFalse(any("dist/" in n for n in names), names)
            self.assertFalse(any("__pycache__" in n for n in names), names)


class TestCli(unittest.TestCase):
    """CLI 冒烟：能跑起来、能给出帮助、doctor 不崩。"""

    def _run(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-m", "promoter", *args],
                              cwd=str(cwd or ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)

    def test_help_lists_release_command(self):
        r = self._run("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("release", r.stdout)

    def test_doctor_runs(self):
        r = self._run("doctor")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("环境自检", r.stdout)

    def test_release_requires_version(self):
        r = self._run("release")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--version", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
