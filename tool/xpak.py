#!/usr/bin/env python3
"""Create or inspect an XPAK component archive."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.xpak import XPAKError, list_xpak, make_xpak, read_xpak_manifest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Create or inspect an XPAK archive.")
    sub = ap.add_subparsers(dest="command", required=True)

    pack = sub.add_parser("pack", help="pack a directory into .xpak")
    pack.add_argument("source", type=Path)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--name", default=None)
    pack.add_argument("--kind", default="data")

    inspect = sub.add_parser("inspect", help="inspect an XPAK archive")
    inspect.add_argument("archive", type=Path)

    args = ap.parse_args()

    try:
        if args.command == "pack":
            output = make_xpak(args.source, args.output, name=args.name, kind=args.kind)
            print(f"Created XPAK: {output}")
            return 0

        manifest = read_xpak_manifest(args.archive)
        members = list_xpak(args.archive)
        print(json.dumps(manifest, indent=2))
        print(f"Members: {len(members)}")
        for member in members:
            print(f"  {member}")
        return 0
    except XPAKError as exc:
        print(f"XPAK error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
