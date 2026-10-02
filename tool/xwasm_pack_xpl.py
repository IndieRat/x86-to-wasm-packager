#!/usr/bin/env python3
"""Package a PE32 executable as a basic XWASM XPL container."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xwasm.container import pack_file  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Package a PE32 executable as an .xpl container.")
    ap.add_argument("executable", type=Path, help="PE32 executable to package")
    ap.add_argument("--output", type=Path, required=True, help="output .xpl container")
    ap.add_argument("--compression", choices=("stored", "zlib", "auto"), default="auto")
    args = ap.parse_args()

    source = args.executable.resolve()
    if not source.is_file():
        raise SystemExit(f"executable not found: {source}")

    raw = source.read_bytes()
    if raw[:2] != b"MZ":
        raise SystemExit("executable is not a PE file (missing MZ header)")

    info = pack_file(source, args.output.resolve(), "xpl", compression=args.compression)
    metadata = {
        "format": "xwasm-xpl",
        "version": 1,
        "container": "XPL",
        "payload_format": "PE32",
        "source_name": source.name,
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
        "payload_bytes": len(raw),
        "compression": "zlib" if info.compression else "stored",
    }
    sidecar = args.output.with_suffix(args.output.suffix + ".json")
    sidecar.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"Created XPL: {args.output.resolve()}")
    print(f"Payload bytes: {len(raw)}")
    print(f"Container bytes: {args.output.stat().st_size}")
    print(f"PE SHA-256: {metadata['payload_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
