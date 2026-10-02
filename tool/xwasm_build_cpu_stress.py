#!/usr/bin/env python3
"""Build the standalone XWASM CPU + guest-memory stress-test package."""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the XWASM CPU + guest-memory stress package.")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--clang", default=None)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)

    build_test = root / "tool" / "xwasm_build_x86_test.py"
    cmd = ["python", str(build_test), "--output", str(out)]
    if args.clang:
        cmd += ["--clang", args.clang]
    subprocess.run(cmd, check=True)

    tests = root / "tests"
    shutil.copy2(tests / "xwasm_cpu_stress.html", out / "index.html")
    shutil.copy2(tests / "xwasm_cpu_stress_runner.js", out / "xwasm_cpu_stress_runner.js")

    runtime = out / "runtime.xwasm"
    payload = out / "payload.xpl"
    if not runtime.is_file():
        raise SystemExit(f"stress package runtime missing: {runtime}")
    if not payload.is_file():
        raise SystemExit(f"stress package payload missing: {payload}")
    if (out / "runtime.wasm").exists():
        raise SystemExit("stress package leaked legacy runtime.wasm")
    if (out / "payload.exe").exists() or (out / "resources" / "__x86__" / "payload.exe").exists():
        raise SystemExit("stress package leaked legacy payload.exe")

    print(f"Created XWASM CPU + guest-memory stress package: {out}")
    print("Open index.html and select:")
    print(f"  runtime: {runtime.name}")
    print(f"  payload: {payload.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
