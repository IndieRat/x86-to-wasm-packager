#!/usr/bin/env python3
"""Convert a supported PE32 DLL into a declarative XWASM .xapi compatibility manifest."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.dll import convert_dll  # noqa: E402
from xwasm.xapi import validate_manifest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert a PE32 DLL into an XWASM XAPI manifest.")
    ap.add_argument("dll", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--strict", action="store_true", help="fail if the seed contains an export absent from the DLL")
    args = ap.parse_args()
    dll = args.dll.resolve()
    if not dll.is_file():
        raise SystemExit(f"DLL not found: {dll}")
    manifest, unmapped = convert_dll(dll, args.output.resolve(), strict=args.strict)
    errors = validate_manifest(manifest)
    if errors:
        raise SystemExit("generated XAPI failed validation: " + "; ".join(errors))
    source = manifest["source"]
    print(f"Converted DLL: {dll}")
    print(f"XAPI: {args.output}")
    print(f"Exports: {source['export_count']}")
    print(f"Mapped: {source['mapped_export_count']}")
    print(f"Unmapped: {source['unmapped_export_count']}")
    if unmapped:
        print("Unmapped exports are intentionally not assigned arbitrary host callbacks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
