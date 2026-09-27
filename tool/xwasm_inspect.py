#!/usr/bin/env python3
"""Inspect and validate an XWASM package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.format import custom_sections, metadata  # noqa: E402
from xwasm.validator import validate_package  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect an XWASM package.")
    ap.add_argument("package", type=Path)
    args = ap.parse_args()
    result = validate_package(args.package)
    print(json.dumps({k: v for k, v in result.items() if k != "module_bytes"}, indent=2))
    if result.get("manifest"):
        print(f"Module bytes: {result['module_bytes']}")
        module = args.package / result["manifest"]["module"]
        print(f"xwasm.meta sections: {len(metadata(module.read_bytes()))}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
