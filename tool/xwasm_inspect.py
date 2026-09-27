#!/usr/bin/env python3
"""Inspect and validate an XWASM package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.format import metadata  # noqa: E402
from xwasm.validator import validate_package  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect and validate an XWASM package.")
    ap.add_argument("package", type=Path)
    args = ap.parse_args()

    result = validate_package(args.package)
    print(json.dumps({k: v for k, v in result.items() if k not in {"module_bytes"}}, indent=2))

    manifest = result.get("manifest") or {}
    architecture = manifest.get("architecture")

    if architecture == "wasm32" and result.get("valid"):
        module = args.package / manifest["module"]
        print(f"Module bytes: {module.stat().st_size}")
        print(f"xwasm.meta sections: {len(metadata(module.read_bytes()))}")
    elif architecture == "x86":
        payload = args.package / manifest["payload"] if manifest.get("payload") else None
        if payload and payload.is_file():
            print(f"Payload bytes: {payload.stat().st_size}")
        runtime = manifest.get("runtime")
        if runtime:
            runtime_path = args.package / runtime
            print(f"Runtime: {runtime} ({runtime_path.stat().st_size if runtime_path.is_file() else 'MISSING'} bytes)")
        else:
            print("Runtime: external/host supplied (none embedded)")

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
