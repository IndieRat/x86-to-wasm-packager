import json
import tempfile
import unittest
from pathlib import Path

from xwasm.format import ABI, META_SECTION, custom_sections, metadata, validate_manifest


class XwasmFormatTests(unittest.TestCase):
    def test_manifest_signature(self):
        manifest = {
            "format": "xwasm-package",
            "format_version": 1,
            "name": "test",
            "architecture": "wasm32",
            "module": "game.wasm",
            "bridge": None,
            "resource_root": "resources/",
            "abi": ABI,
            "entry": {"init": "xwasm_init", "tick": "xwasm_tick", "shutdown": "xwasm_shutdown"},
        }
        self.assertEqual(validate_manifest(manifest), [])

    def test_custom_metadata(self):
        meta = json.dumps({
            "format": "xwasm-meta",
            "version": 1,
            "abi": ABI,
            }).encode()
        name = META_SECTION.encode()
        section_payload = bytes([len(name)]) + name + meta
        wasm = b"\\x00asm\\x01\\x00\\x00\\x00" + bytes([0, len(section_payload)]) + section_payload
        self.assertEqual(len(custom_sections(wasm, META_SECTION)), 1)
        self.assertEqual(metadata(wasm)[0]["abi"], ABI)


if __name__ == "__main__":
    unittest.main()
