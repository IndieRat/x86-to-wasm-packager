#!/usr/bin/env python3
"""Validate and summarize the XWASM v0.8 x86 instruction database."""

from __future__ import annotations
import argparse
import json
from pathlib import Path

REQUIRED_GROUPS = {
    "integer_core", "data_move", "control_flow", "bit_and_shift",
    "string", "x87", "mmx_sse", "system",
}
VALID_STATUS = {"EXECUTE", "DECODE", "PLANNED", "SYSTEM"}

def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != "xwasm-x86-instruction-db":
        raise ValueError("unexpected instruction database format")
    if data.get("architecture") != "i386":
        raise ValueError("instruction database must target i386")
    groups = data.get("instruction_sets")
    if not isinstance(groups, dict):
        raise ValueError("missing instruction_sets")
    missing = REQUIRED_GROUPS - set(groups)
    if missing:
        raise ValueError("missing groups: " + ", ".join(sorted(missing)))
    for group, entries in groups.items():
        if not isinstance(entries, list):
            raise ValueError(f"{group}: expected a list")
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("mnemonic"):
                raise ValueError(f"{group}: entry missing mnemonic")
            if entry.get("status") not in VALID_STATUS:
                raise ValueError(f"{group}/{entry.get('mnemonic')}: invalid status")
    return data

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", type=Path,
                    default=Path("runtime/x86/instructions.json"))
    ap.add_argument("--strict", action="store_true",
                    help="fail if any instruction is not EXECUTE")
    args = ap.parse_args()

    data = load(args.path)
    counts = {status: 0 for status in sorted(VALID_STATUS)}
    total = 0
    for entries in data["instruction_sets"].values():
        for entry in entries:
            counts[entry["status"]] += 1
            total += 1

    print("XWASM x86 instruction database")
    print(f"architecture: {data['architecture']}")
    print(f"version:      {data['version']}")
    print(f"instructions: {total}")
    for status in sorted(counts):
        print(f"{status:9}: {counts[status]}")

    if args.strict and counts["EXECUTE"] != total:
        print("STRICT: instruction database still contains non-executing entries")
        return 2

    print("VALID")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
