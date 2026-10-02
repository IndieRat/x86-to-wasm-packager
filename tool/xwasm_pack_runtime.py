#!/usr/bin/env python3
"""Build the final-stage XWASM runtime container from a standard runtime.wasm."""
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
    ap = argparse.ArgumentParser(description="Package runtime.wasm as runtime.xwasm.")
    ap.add_argument("runtime", type=Path, help="standard WebAssembly runtime module")
    ap.add_argument("--output", type=Path, required=True, help="output .xwasm container")
    ap.add_argument("--compression", choices=("stored", "zlib", "auto"), default="auto")
    ap.add_argument("--metadata", type=Path, help="optional JSON metadata file")
    args = ap.parse_args()

    runtime = args.runtime.resolve()
    if not runtime.is_file():
        raise SystemExit(f"runtime not found: {runtime}")
    raw = runtime.read_bytes()
    if raw[:4] != b"\x00asm":
        raise SystemExit("runtime is not a WebAssembly binary")

    info = pack_file(runtime, args.output.resolve(), "xwasm", compression=args.compression)
    metadata = {
        "format": "xwasm-runtime",
        "version": 1,
        "container": "XWASM",
        "kind": "runtime",
        "wasm_sha256": hashlib.sha256(raw).hexdigest(),
        "wasm_bytes": len(raw),
        "compression": "zlib" if info.compression else "stored",
    }
    if args.metadata:
        metadata.update(json.loads(args.metadata.read_text(encoding="utf-8")))
    sidecar = args.output.with_suffix(args.output.suffix + ".json")
    sidecar.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"Created runtime container: {args.output.resolve()}")
    print(f"Kind: {info.kind_name}")
    print(f"Compression: {metadata['compression']}")
    print(f"WASM bytes: {len(raw)}")
    print(f"Container bytes: {args.output.stat().st_size}")
    print(f"WASM SHA-256: {metadata['wasm_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
