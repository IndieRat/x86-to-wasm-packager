#!/usr/bin/env python3
"""Create a raw v86 guest hard-disk image without requiring QEMU."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def parse_size(value: str) -> int:
    text = value.strip().upper()
    units = {"K": 1024, "M": 1024**2, "G": 1024**3}
    multiplier = 1
    if text[-1:] in units:
        multiplier = units[text[-1]]
        text = text[:-1]
    size = int(float(text) * multiplier)
    if size < 1024 * 1024:
        raise ValueError("Guest disk must be at least 1 MiB.")
    return size


def create_blank(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(size)


def build_guest(output: Path, size: str, source: Path | None) -> dict:
    output = output.resolve()
    if source:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Guest source image not found: {source}")
        if source == output:
            raise ValueError("Guest source and output cannot be the same file.")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        return {
            "path": str(output),
            "size_bytes": output.stat().st_size,
            "type": "copied-raw-image",
            "bootable": "unknown",
            "requires_os_install": True,
        }

    size_bytes = parse_size(size)
    create_blank(output, size_bytes)
    return {
        "path": str(output),
        "size_bytes": size_bytes,
        "type": "blank-raw-image",
        "bootable": False,
        "requires_os_install": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create a raw guest.hda for the x86/v86 package."
    )
    ap.add_argument("--output", type=Path, default=Path("guest.hda"))
    ap.add_argument("--size", default="2G",
                    help="Blank disk size, e.g. 256M, 1G, 2G (default: 2G).")
    ap.add_argument("--from-image", type=Path,
                    help="Copy an existing raw guest disk instead of creating a blank one.")
    args = ap.parse_args()

    try:
        info = build_guest(args.output, args.size, args.from_image)
    except Exception as exc:
        print(f"Guest builder failed: {exc}")
        return 1

    print(f"Created: {info['path']}")
    print(f"Size: {info['size_bytes']} bytes")
    print(f"Type: {info['type']}")
    print("Bootable: no/unknown until an operating system is installed.")
    print("")
    print("This command does not install Windows or another operating system.")
    print("v86 can consume the resulting raw image, but a usable guest OS must")
    print("already be installed or installed from legitimate installation media.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
