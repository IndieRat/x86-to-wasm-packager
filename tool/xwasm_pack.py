#!/usr/bin/env python3
"""Create a directory or single-file XWASM package from a standard WASM module."""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.container import pack_xwasm_directory  # noqa: E402
from xwasm.format import ABI, META_SECTION, make_manifest, write_manifest  # noqa: E402


def leb_u32(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def add_meta_section(wasm: bytes) -> bytes:
    """Append an xwasm.meta custom section without changing WASM semantics."""
    if wasm[:4] != b"\x00asm":
        raise ValueError("Input is not a WebAssembly binary.")
    name = META_SECTION.encode("utf-8")
    payload = leb_u32(len(name)) + name
    meta = b'{"format":"xwasm-meta","version":1,"abi":"' + ABI.encode("utf-8") + b'"}'
    payload += meta
    return wasm + bytes([0]) + leb_u32(len(payload)) + payload


def build_directory(module: Path, out: Path, name: str | None, resources: Path | None, bridge: Path | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "game.wasm").write_bytes(add_meta_section(module.read_bytes()))

    if resources:
        if not resources.is_dir():
            raise SystemExit(f"Resource directory not found: {resources}")
        shutil.copytree(resources, out / "resources", dirs_exist_ok=True)

    if bridge:
        shutil.copy2(bridge, out / "bridge.js")

    manifest = make_manifest(name or out.name)
    if bridge:
        manifest["bridge"] = "bridge.js"
    manifest["resource_file_count"] = (
        sum(1 for p in (out / "resources").rglob("*") if p.is_file())
        if (out / "resources").is_dir()
        else 0
    )
    write_manifest(out / "manifest.xwasm.json", manifest)


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
    if data[:4] != b"\x00asm":
        raise SystemExit("Input is not a WebAssembly binary.")

    out = args.output.resolve()

    if out.suffix.lower() == ".xwasm":
        if out.exists():
            raise SystemExit(f"XWASM output already exists: {out}")
        with tempfile.TemporaryDirectory(prefix="xwasm-build-") as temp:
            staging = Path(temp) / "package"
            build_directory(module, staging, args.name or out.stem, args.resources, args.bridge)
            pack_xwasm_directory(staging, out)
        print(f"Created XWASM container: {out}")
        return 0

    build_directory(module, out, args.name or out.name, args.resources, args.bridge)
    print(f"Created XWASM package directory: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
