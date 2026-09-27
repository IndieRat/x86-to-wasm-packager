#!/usr/bin/env python3
"""Package a 32-bit PE game as an XWASM x86-runtime package.

This is a packaging step only. It does not translate x86 instructions into
WebAssembly and does not make a Windows executable directly browser-runnable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import shutil
from pathlib import Path


def pe32_info(path: Path) -> dict:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError(f"{path.name} is not a PE file (missing MZ header).")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{path.name} has an invalid PE signature.")
    machine = struct.unpack_from("<H", data, pe + 4)[0]
    magic = struct.unpack_from("<H", data, pe + 24)[0]
    if machine != 0x014C or magic != 0x10B:
        raise ValueError(
            f"{path.name} is not a PE32/i386 executable: machine=0x{machine:04x}, optional_magic=0x{magic:04x}"
        )
    return {"machine": "i386", "machine_id": machine, "pe_type": "PE32", "size": len(data)}


def copy_tree(source: Path, dest: Path, exe: Path) -> int:
    count = 0
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        if item.resolve() == exe.resolve():
            continue
        rel = item.relative_to(source)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description="Package a 32-bit PE game as XWASM x86-runtime input.")
    ap.add_argument("game_folder", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--exe", type=Path, default=None,
                    help="Executable path relative to game_folder; otherwise auto-detect a root EXE.")
    ap.add_argument("--runtime", default=None,
                    help="Optional XWASM x86 runtime path, relative to the package.")
    args = ap.parse_args()

    game = args.game_folder.resolve()
    out = args.output.resolve()
    if not game.is_dir():
        raise SystemExit("Input game_folder must be a directory.")
    out.mkdir(parents=True, exist_ok=True)
    resources = out / "resources"
    resources.mkdir(exist_ok=True)

    if args.exe:
        exe = (game / args.exe).resolve()
    else:
        candidates = sorted(game.glob("*.exe"))
        if not candidates:
            candidates = sorted(game.rglob("*.exe"))
        if not candidates:
            raise SystemExit("No EXE found.")
        exe = candidates[0]

    info = pe32_info(exe)
    payload = out / "resources" / "__x86__" / "payload.exe"
    payload.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, payload)
    count = copy_tree(game, resources, exe)

    runtime = args.runtime
    manifest = {
        "format": "xwasm-package",
        "format_version": 1,
        "name": game.name,
        "architecture": "x86",
        "runtime_kind": "x86-compatibility",
        "runtime": runtime,
        "abi": "xwasm.host/1",
        "resource_root": "resources/",
        "payload": "resources/__x86__/payload.exe",
        "payload_format": "PE32",
        "payload_architecture": "i386",
        "entry": {
            "init": "xwasm_init",
            "tick": "xwasm_tick",
            "shutdown": "xwasm_shutdown",
        },
        "pe": info,
        "resource_file_count": count,
        "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "execution_status": "requires_x86_runtime",
    }
    if runtime:
        runtime_path = game / runtime
        if not runtime_path.is_file():
            raise SystemExit(f"Runtime path does not exist inside game folder: {runtime}")
        shutil.copy2(runtime_path, out / "runtime.wasm")

    (out / "manifest.xwasm.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Created XWASM x86 package: {out}")
    print(f"Payload: {payload.relative_to(out)}")
    print(f"Resources: {count}")
    print("Status: package is ready for an x86 XWASM runtime; it is not executable by the native-WASM reference runner.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
