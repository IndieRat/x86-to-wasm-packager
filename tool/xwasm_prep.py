#!/usr/bin/env python3
"""Prepare the XWASM x86 ISA database and generated decoder artifacts."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_tool(name: str, *args: str) -> None:
    path = ROOT / "tool" / name
    print(f"[XWASM PREP] {name}")
    subprocess.run([sys.executable, str(path), *args], cwd=ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prepare XWASM x86 ISA/import/generated decoder artifacts."
    )
    ap.add_argument(
        "--xed-input",
        type=Path,
        help="offline xed-isa.txt snapshot; skips the network fetch",
    )
    ap.add_argument(
        "--xed-url",
        help="override the Intel XED ISA source URL",
    )
    ap.add_argument(
        "--legacy-i386",
        action="store_true",
        help="keep only XED patterns applicable to legacy i386 mode",
    )
    args = ap.parse_args()

    import_args = []
    if args.xed_input:
        import_args += ["--input", str(args.xed_input)]
    if args.xed_url:
        import_args += ["--url", args.xed_url]
    if args.legacy_i386:
        import_args.append("--legacy-i386")

    run_tool("xwasm_import_xed_isa.py", *import_args)
    run_tool("xwasm_generate_x86_opcode_map.py")
    run_tool("xwasm_generate_x86_decode_table.py")
    run_tool("xwasm_validate_instruction_db.py")

    print("[XWASM PREP] READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
