#!/usr/bin/env python3
"""Create a tiny deterministic XWASM reference package.

This package contains a minimal WASM module that exports the XWASM lifecycle.
It is intended to test the package/boot protocol before a real game runtime
is introduced.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MAGIC = b"\x00asm\x01\x00\x00\x00"


def u32(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def vec(items: list[bytes]) -> bytes:
    return u32(len(items)) + b"".join(items)


def name(s: str) -> bytes:
    b = s.encode()
    return u32(len(b)) + b


def section(section_id: int, payload: bytes) -> bytes:
    return bytes([section_id]) + u32(len(payload)) + payload


def make_module() -> bytes:
    # Types:
    # 0: () -> ()
    # 1: (i32, i32) -> ()
    types = vec([
        b"\x60\x00\x00",
        b"\x60\x02\x7f\x7f\x00",
    ])

    # Import xwasm.host.log(level, ptr, len).
    imports = vec([
        name("xwasm.host") + name("log") + b"\x00" + u32(1)
    ])

    # Three local functions: init, tick, shutdown.
    functions = vec([u32(0), u32(0), u32(0)])

    # Exports: lifecycle functions and memory.
    exports = vec([
        name("xwasm_init") + b"\x00" + u32(1),
        name("xwasm_tick") + b"\x00" + u32(2),
        name("xwasm_shutdown") + b"\x00" + u32(3),
        name("memory") + b"\x02" + u32(0),
    ])

    # Function bodies:
    # init: nop/end
    # tick: nop/end
    # shutdown: nop/end
    code = vec([
        u32(2) + b"\x00\x01\x0b",
        u32(2) + b"\x00\x01\x0b",
        u32(2) + b"\x00\x01\x0b",
    ])

    memory = vec([b"\x00\x01"])

    meta = json.dumps({
        "format": "xwasm-meta",
        "version": 1,
        "abi": "xwasm.host/1",
        "reference": True,
    }, separators=(",", ":")).encode()
    custom = name("xwasm.meta") + meta

    return MAGIC + section(1, types) + section(2, imports) + section(3, functions) + section(5, memory) + section(7, exports) + section(10, code) + section(0, custom)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "resources").mkdir(exist_ok=True)
    (root / "game.wasm").write_bytes(make_module())
    manifest = {
        "format": "xwasm-package",
        "format_version": 1,
        "name": "XWASM Reference Test",
        "architecture": "wasm32",
        "module": "game.wasm",
        "bridge": None,
        "resource_root": "resources/",
        "abi": "xwasm.host/1",
        "entry": {
            "init": "xwasm_init",
            "tick": "xwasm_tick",
            "shutdown": "xwasm_shutdown",
        },
        "reference": True,
    }
    (root / "manifest.xwasm.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Created reference XWASM package: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
