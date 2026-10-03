#!/usr/bin/env python3
"""Build the XWASM x86 compatibility runtime and emit a .xwasm container."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.container import pack_file  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the XWASM x86 compatibility runtime.")
    ap.add_argument("--output", type=Path, default=Path("dist/x86-runtime-v0.9/runtime.xwasm"))
    ap.add_argument("--clang", default=shutil.which("clang"))
    ap.add_argument("--compression", choices=("stored", "zlib", "auto"), default="auto")
    args = ap.parse_args()

    if not args.clang:
        raise SystemExit("clang is required (install LLVM/Clang or pass --clang PATH).")

    root = Path(__file__).resolve().parents[1]
    src = root / "runtime/x86/runtime.c"
    opcode_generator = root / "tool/xwasm_generate_x86_opcode_map.py"
    decode_generator = root / "tool/xwasm_generate_x86_decode_table.py"

    subprocess.run([sys.executable, str(opcode_generator)], check=True, cwd=root)
    subprocess.run([sys.executable, str(decode_generator)], check=True, cwd=root)

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="xwasm-runtime-") as temp:
        raw_wasm = Path(temp) / "runtime.wasm"
        cmd = [
            args.clang, "--target=wasm32", "-O1", "-nostdlib", "-fno-builtin",
            str(src), "-o", str(raw_wasm),
            "-Wl,--no-entry", "-Wl,--export-all", "-Wl,--import-memory",
            # Keep the guest address space below the 128 MiB initial WASM
            # backing store, while retaining room for runtime growth.
            "-Wl,--initial-memory=134217728", "-Wl,--max-memory=268435456",
            "-Wl,--allow-undefined",
        ]
        print("Compiling XWASM runtime WASM:")
        print(" ".join(map(str, cmd)))
        subprocess.run(cmd, check=True)

        data = raw_wasm.read_bytes()
        if data[:4] != b"\x00asm":
            raise SystemExit("clang produced an invalid WebAssembly module")

        info = pack_file(raw_wasm, output, "xwasm", compression=args.compression)
        digest = hashlib.sha256(data).hexdigest()

    print(f"Created XWASM runtime: {output}")
    print(f"Kind: {info.kind_name}")
    print(f"WASM bytes: {len(data)}")
    print(f"XWASM bytes: {output.stat().st_size}")
    print(f"Compression: {'zlib' if info.compression else 'stored'}")
    print(f"WASM SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
