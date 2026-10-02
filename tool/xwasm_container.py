#!/usr/bin/env python3
"""Inspect, verify, pack, and unpack XWASM final-stage containers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.container import inspect_bytes, pack_file, unpack_file  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="XWASM container utility.")
    sub = ap.add_subparsers(dest="command", required=True)

    pack = sub.add_parser("pack")
    pack.add_argument("input", type=Path)
    pack.add_argument("output", type=Path)
    pack.add_argument("--kind", choices=("xwasm", "xpl", "xpak", "xapi"), required=True)
    pack.add_argument("--compression", choices=("stored", "zlib", "auto"), default="auto")

    unpack = sub.add_parser("unpack")
    unpack.add_argument("input", type=Path)
    unpack.add_argument("output", type=Path)
    unpack.add_argument("--kind", choices=("xwasm", "xpl", "xpak", "xapi"))

    inspect = sub.add_parser("inspect")
    inspect.add_argument("input", type=Path)

    args = ap.parse_args()

    if args.command == "pack":
        info = pack_file(args.input, args.output, args.kind, compression=args.compression)
        print(json.dumps(info.__dict__ | {"kind_name": info.kind_name}, indent=2))
        return 0

    if args.command == "unpack":
        info = unpack_file(args.input, args.output, expected_kind=args.kind)
        print(json.dumps(info.__dict__ | {"kind_name": info.kind_name}, indent=2))
        return 0

    info = inspect_bytes(args.input.read_bytes())
    print(json.dumps(info.__dict__ | {"kind_name": info.kind_name}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
