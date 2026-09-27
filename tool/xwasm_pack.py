#!/usr/bin/env python3
"""Create a directory-style XWASM package from an existing WASM module."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.format import make_manifest, write_manifest, META_SECTION, ABI  # noqa: E402


def leb_u32(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7f
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def add_meta_section(wasm: bytes) -> bytes:
    """Append an xwasm.meta custom section without changing WASM semantics."""
    if wasm[:4] != b"\\x00asm":
        raise ValueError("Input is not a WebAssembly binary.")
    name = META_SECTION.encode("utf-8")
    payload = leb_u32(len(name)) + name
    meta = b'{"format":"xwasm-meta","version":1,"abi":"' + ABI.encode("utf-8") + b'"}'
    payload += meta
    return wasm + bytes([0]) + leb_u32(len(payload)) + payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Package a standard WASM module as XWASM.")
    ap.add_argument("module", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--resources", type=Path)
    ap.add_argument("--bridge", type=Path)
    args = ap.parse_args()
    module = args.module.resolve()
    if not module.is_file():
        raise SystemExit(f"WASM module not found: {module}")
    data = module.read_bytes()
    if data[:4] != b"\\x00asm":
        raise SystemExit("Input is not a WebAssembly binary.")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "game.wasm").write_bytes(add_meta_section(data))
    if args.resources:
        if not args.resources.is_dir():
            raise SystemExit(f"Resource directory not found: {args.resources}")
        shutil.copytree(args.resources, out / "resources", dirs_exist_ok=True)
    if args.bridge:
        shutil.copy2(args.bridge, out / "bridge.js")
    manifest = make_manifest(args.name or out.name)
    if args.bridge:
        manifest["bridge"] = "bridge.js"
    manifest["resource_file_count"] = sum(1 for p in (out / "resources").rglob("*") if p.is_file()) if (out / "resources").is_dir() else 0
    write_manifest(out / "manifest.xwasm.json", manifest)
    print(f"Created XWASM package: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
