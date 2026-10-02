from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from xwasm.xpak import XPAKError, extract_xpak, list_xpak, make_xpak, read_xpak_manifest, read_xpak_member


class XPAKTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "data").mkdir()
            (source / "data" / "hello.txt").write_text("hello xpak\n", encoding="utf-8")

            archive = root / "sample.xpak"
            make_xpak(source, archive, name="sample", kind="resources")

            self.assertEqual(read_xpak_manifest(archive)["name"], "sample")
            self.assertEqual(read_xpak_manifest(archive)["kind"], "resources")
            self.assertEqual(list_xpak(archive), ["data/hello.txt"])
            self.assertEqual(read_xpak_member(archive, "data/hello.txt"), b"hello xpak\n")

            extracted = root / "extracted"
            extract_xpak(archive, extracted)
            self.assertEqual((extracted / "data" / "hello.txt").read_text(encoding="utf-8"), "hello xpak\n")

    def test_rejects_traversal(self) -> None:
        with self.assertRaises(XPAKError):
            read_xpak_member(Path("sample.xpak"), "../outside.txt")


if __name__ == "__main__":
    unittest.main()
