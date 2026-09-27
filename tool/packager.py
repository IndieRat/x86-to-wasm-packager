#!/usr/bin/env python3
"""Package or update a 32-bit x86 Windows game for a browser x86/WASM runtime."""

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

from guest_builder import build_guest

I386 = 0x014C


def pe32_info(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("Input is not an MZ executable.")
    pe = int.from_bytes(data[0x3C:0x40], "little")
    if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Input does not contain a valid PE header.")
    machine = int.from_bytes(data[pe + 4:pe + 6], "little")
    if machine != I386:
        raise ValueError(
            f"Unsupported machine 0x{machine:04X}; expected PE32/i386 (0x014C)."
        )
    section_count = int.from_bytes(data[pe + 6:pe + 8], "little")
    optional_size = int.from_bytes(data[pe + 20:pe + 22], "little")
    optional = pe + 24
    if optional + optional_size > len(data):
        raise ValueError("PE optional header is truncated.")
    entry = int.from_bytes(data[optional + 16:optional + 20], "little")
    sections = []
    table = optional + optional_size
    for i in range(section_count):
        off = table + i * 40
        if off + 40 > len(data):
            raise ValueError("PE section table is truncated.")
        name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        sections.append({
            "name": name,
            "virtual_address": int.from_bytes(data[off + 12:off + 16], "little"),
            "virtual_size": int.from_bytes(data[off + 8:off + 12], "little"),
            "raw_size": int.from_bytes(data[off + 16:off + 20], "little"),
        })
    return {"file_size": len(data), "entry_point": entry, "sections": sections}


def download_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "x86-to-wasm-packager/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_exe(game: Path, requested: str | None) -> Path:
    if requested:
        p = (game / requested).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Executable not found: {requested}")
        return p
    exes = sorted(p for p in game.rglob("*.exe") if p.is_file())
    if not exes:
        raise FileNotFoundError("No .exe was found. Use --exe PATH to select one.")
    root = [p for p in exes if p.parent == game]
    pool = root or exes
    preferred = {"game.exe", f"{game.name.lower()}.exe"}
    return next((p for p in pool if p.name.lower() in preferred), pool[0])


def copy_resources(game: Path, out: Path, exe: Path) -> int:
    root = out / "resources"
    count = 0
    for src in game.rglob("*"):
        if not src.is_file() or src.resolve() == exe.resolve():
            continue
        dst = root / src.relative_to(game)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        count += 1
    return count


def generated_bridge() -> str:
    # This is a package/runtime adapter, not an x86 emulator. The actual runtime
    # must expose the small API documented here or a supplied custom bridge can
    # replace this file.
    return r'''/* Generated package bridge.
 * The actual x86 execution/translation engine is runtime.wasm.
 *
 * Expected runtime contract:
 *   window.X86Runtime.start({
 *     payload: Uint8Array,
 *     manifest: object,
 *     readResource(path): Promise<Uint8Array>
 *   })
 *
 * A runtime may install X86Runtime before this bridge is loaded.
 */
(function () {
  "use strict";

  async function loadBytes(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error("Failed to load " + url);
    return new Uint8Array(await response.arrayBuffer());
  }

  async function startX86Package() {
    const pkg = window.__X86_WASM_PACKAGE__;
    if (!pkg) throw new Error("X86 WASM package has not been loaded.");

    if (!window.X86Runtime || typeof window.X86Runtime.start !== "function") {
      throw new Error(
        "No compatible X86Runtime was supplied. runtime.wasm must be paired " +
        "with a bridge/runtime implementation that supports the package ABI."
      );
    }

    return window.X86Runtime.start({
      payload: pkg.payload,
      manifest: pkg.manifest,
      readResource: pkg.readResource
    });
  }

  window.X86WasmBridge = {
    start: startX86Package,
    loadBytes
  };
  window.initializeX86Wasm = startX86Package;
})();
'''


def resolve_runtime(runtime_wasm: Path | None, bridge: Path | None,
                    runtime_dir: Path | None) -> tuple[Path | None, Path | None]:
    if runtime_dir:
        runtime_dir = runtime_dir.resolve()
        if not runtime_dir.is_dir():
            raise FileNotFoundError(f"Runtime directory not found: {runtime_dir}")
        runtime_wasm = runtime_wasm or (runtime_dir / "runtime.wasm")
        bridge = bridge or (runtime_dir / "bridge.js")

    if runtime_wasm and not runtime_wasm.is_file():
        raise FileNotFoundError(f"Runtime WASM not found: {runtime_wasm}")
    if bridge and not bridge.is_file():
        raise FileNotFoundError(f"Bridge not found: {bridge}")

    return runtime_wasm, bridge


def copy_runtime_bundle(runtime_dir: Path | None, out: Path) -> list[str]:
    """Copy supporting runtime files from a runtime bundle directory."""
    if not runtime_dir:
        return []
    runtime_dir = runtime_dir.resolve()
    copied = []
    for src in runtime_dir.iterdir():
        if not src.is_file() or src.name in {"runtime.wasm", "bridge.js"}:
            continue
        dst = out / src.name
        shutil.copy2(src, dst)
        copied.append(src.name)
    return sorted(copied)


def write_loader(out: Path) -> None:
    (out / "loader.js").write_text(r'''async function loadX86Package() {
  const manifest = await fetch("./manifest.json").then(r => {
    if (!r.ok) throw new Error("manifest.json could not be loaded");
    return r.json();
  });

  const payload = manifest.payload
    ? new Uint8Array(await fetch("./" + manifest.payload).then(r => r.arrayBuffer()))
    : null;

  const runtime = manifest.runtime
    ? new Uint8Array(await fetch("./" + manifest.runtime).then(r => r.arrayBuffer()))
    : null;

  const bridge = manifest.bridge
    ? "./" + manifest.bridge
    : null;

  const resourceUrl = path =>
    "./resources/" + String(path).replace(/^\/+/, "")
      .split("/").map(encodeURIComponent).join("/");

  window.__X86_WASM_PACKAGE__ = {
    manifest,
    payload,
    runtime,
    bridge,
    resourceUrl,
    readResource: async path =>
      new Uint8Array(await fetch(resourceUrl(path)).then(r => r.arrayBuffer()))
  };

  if (bridge) {
    await new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = bridge;
      script.onload = resolve;
      script.onerror = () => reject(new Error("Failed to load " + bridge));
      document.head.appendChild(script);
    });
  }

  return window.__X86_WASM_PACKAGE__;
}

window.loadX86Package = loadX86Package;
''', encoding="utf-8")

    (out / "index.html").write_text(r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>x86 WASM Port</title>
</head>
<body style="font-family:system-ui;background:#0b1020;color:#e5e7eb;padding:24px">
<h2 id="title">Loading package…</h2>
<pre id="status"></pre>
<script src="./loader.js"></script>
<script>
(async () => {
  try {
    const p = await loadX86Package();
    document.getElementById("title").textContent = p.manifest.name;

    if (window.X86WasmBridge &&
        typeof window.X86WasmBridge.start === "function" &&
        p.manifest.runtime) {
      await window.X86WasmBridge.start();
      document.getElementById("status").textContent = "Runtime started.";
    } else {
      document.getElementById("status").textContent =
        "Package loaded.\n" +
        "Executable: " + p.manifest.executable + "\n" +
        "Resources: " + p.manifest.resource_file_count + "\n" +
        "Runtime: " + (p.manifest.runtime || "none") + "\n" +
        "Bridge: " + (p.manifest.bridge || "none") + "\n\n" +
        "A compatible x86 execution runtime is required to execute the Windows EXE.";
    }
  } catch (e) {
    document.getElementById("status").textContent = "Load failed: " + e.message;
    console.error(e);
  }
})();
</script>
</body>
</html>
''', encoding="utf-8")


def build_manifest(out: Path, executable: str, info: dict,
                   resource_count: int, name: str | None,
                   runtime: bool, bridge: bool,
                   runtime_files: list[str] | None = None) -> dict:
    test_image = None
    runtime_json = out / "runtime.json"
    if runtime_json.is_file():
        try:
            runtime_meta = json.loads(runtime_json.read_text(encoding="utf-8"))
            candidate = runtime_meta.get("test_image")
            if candidate and (out / candidate).is_file():
                test_image = candidate
        except (OSError, json.JSONDecodeError):
            pass

    manifest = {
        "bundle_version": "2.1",
        "format": "x86-wasm-package",
        "name": name or out.name,
        "architecture": "x86",
        "machine": "i386",
        "source_type": "game-folder",
        "executable": executable,
        "payload": "payload.bin",
        "runtime": "runtime.wasm" if runtime else None,
        "bridge": "bridge.js" if bridge else None,
        "runtime_required": True,
        "test_image": test_image,
        "resource_root": "resources/",
        "resource_file_count": resource_count,
        "entry": "x86_run",
        "entry_point": info["entry_point"],
        "file_size": info["file_size"],
        "sections": info["sections"],
        "sha256": sha256(out / "payload.bin"),
        "execution_note": (
            "The package contains the x86 PE payload and resources. "
            "runtime.wasm must provide actual x86 execution/translation; "
            "bridge.js must implement the runtime package ABI."
        )
    }
    return manifest


def write_manifest(out: Path, manifest: dict) -> None:
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def package(game: Path, out: Path, exe_name: str | None,
            runtime: Path | None, bridge: Path | None,
            runtime_dir: Path | None, name: str | None,
            guest_hda: Path | None = None, guest_hdb: Path | None = None,
            guest_hda_url: str | None = None, guest_auto: bool = False,
            guest_size: str = "2G") -> dict:
    game = game.resolve()
    out = out.resolve()
    if not game.is_dir():
        raise ValueError("Input must be a game folder.")
    if out == game or game in out.parents:
        raise ValueError("Output must not be inside the source game folder.")

    runtime, bridge = resolve_runtime(runtime, bridge, runtime_dir)

    exe = find_exe(game, exe_name)
    info = pe32_info(exe)
    out.mkdir(parents=True, exist_ok=True)

    shutil.copy2(exe, out / "payload.bin")
    count = copy_resources(game, out, exe)

    if runtime:
        shutil.copy2(runtime, out / "runtime.wasm")
    if bridge:
        shutil.copy2(bridge, out / "bridge.js")
    runtime_files = copy_runtime_bundle(runtime_dir, out)

    # Optional user-supplied guest disks. The packager never downloads or creates
    # a Windows guest; it only carries an existing guest image into the package.
    guest_hda_name = None
    guest_hdb_name = None
    if sum(bool(x) for x in (guest_hda, guest_hda_url, guest_auto)) > 1:
        raise ValueError("Use only one of --guest-hda, --guest-hda-url, or --guest-auto.")
    if guest_hda_url:
        (out / "guest.hda").write_bytes(download_bytes(guest_hda_url))
        guest_hda_name = "guest.hda"
    if guest_hda:
        if not guest_hda.is_file():
            raise FileNotFoundError(f"Guest HDA not found: {guest_hda}")
        shutil.copy2(guest_hda, out / "guest.hda")
        guest_hda_name = "guest.hda"
    if guest_hdb:
        if not guest_hdb.is_file():
            raise FileNotFoundError(f"Guest HDB not found: {guest_hdb}")
        shutil.copy2(guest_hdb, out / "guest.hdb")
        guest_hdb_name = "guest.hdb"
    if guest_auto:
        build_guest(out / "guest.hda", guest_size, None)
        guest_hda_name = "guest.hda"

    write_loader(out)
    manifest = build_manifest(
        out, exe.name, info, count, name,
        runtime is not None, bridge is not None,
        runtime_files
    )
    manifest["runtime_files"] = runtime_files
    if guest_hda_name:
        manifest["guest_hda"] = guest_hda_name
        manifest["guest_hda_type"] = "blank-raw-image" if guest_auto else "provided"
        manifest["guest_requires_os_install"] = True
    if guest_hdb_name:
        manifest["guest_hdb"] = guest_hdb_name
    write_manifest(out, manifest)
    return manifest


def update_port(out: Path, runtime: Path | None, bridge: Path | None,
                runtime_dir: Path | None) -> dict:
    out = out.resolve()
    if not out.is_dir():
        raise ValueError(f"Existing port folder not found: {out}")

    runtime, bridge = resolve_runtime(runtime, bridge, runtime_dir)

    if runtime:
        shutil.copy2(runtime, out / "runtime.wasm")
    if bridge:
        shutil.copy2(bridge, out / "bridge.js")
    runtime_files = copy_runtime_bundle(runtime_dir, out)

    manifest_path = out / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Existing port has no manifest.json.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if runtime:
        manifest["runtime"] = "runtime.wasm"
        manifest["runtime_required"] = True
    if bridge:
        manifest["bridge"] = "bridge.js"

    manifest["bundle_version"] = "2.1"
    manifest["updated_runtime"] = bool(runtime)
    manifest["updated_bridge"] = bool(bridge)
    if runtime_files:
        manifest["runtime_files"] = runtime_files
        runtime_json = out / "runtime.json"
        if runtime_json.is_file():
            try:
                runtime_meta = json.loads(runtime_json.read_text(encoding="utf-8"))
                candidate = runtime_meta.get("test_image")
                if candidate and (out / candidate).is_file():
                    manifest["test_image"] = candidate
            except (OSError, json.JSONDecodeError):
                pass

    write_manifest(out, manifest)
    write_loader(out)

    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build or update an x86/WASM game package."
    )

    ap.add_argument("game_folder", nargs="?", type=Path,
                    help="Game folder for a new package.")
    ap.add_argument("--output", type=Path, default=Path("dist/game"))
    ap.add_argument("--exe",
                    help="Executable path relative to the game folder.")
    ap.add_argument("--runtime-wasm", type=Path,
                    help="Actual compatible x86 execution/translation runtime.")
    ap.add_argument("--bridge", type=Path,
                    help="JavaScript bridge matching the runtime ABI.")
    ap.add_argument("--runtime-dir", type=Path,
                    help="Directory containing runtime.wasm and bridge.js.")
    ap.add_argument("--name")
    ap.add_argument("--guest-hda", type=Path,
                    help="Optional existing bootable guest disk image to carry as guest.hda.")
    ap.add_argument("--guest-hdb", type=Path,
                    help="Optional existing second guest disk image to carry as guest.hdb.")
    ap.add_argument("--guest-hda-url",
                    help="Download a bootable guest disk from a direct URL and package it as guest.hda.")
    ap.add_argument("--guest-auto", action="store_true",
                    help="Create a blank raw guest.hda automatically; no QEMU required.")
    ap.add_argument("--guest-size", default="2G",
                    help="Size for --guest-auto, e.g. 256M, 1G, 2G (default: 2G).")
    ap.add_argument("--update-port", type=Path,
                    help="Update an existing port folder in place with runtime files.")

    args = ap.parse_args()

    try:
        if args.update_port:
            m = update_port(
                args.update_port,
                args.runtime_wasm,
                args.bridge,
                args.runtime_dir
            )
            print(f"Updated port: {args.update_port}")
        else:
            if not args.game_folder:
                ap.error("game_folder is required unless --update-port is used.")
            m = package(
                args.game_folder,
                args.output,
                args.exe,
                args.runtime_wasm,
                args.bridge,
                args.runtime_dir,
                args.name,
                args.guest_hda,
                args.guest_hdb,
                args.guest_hda_url,
                args.guest_auto,
                args.guest_size
            )
            print(f"Package: {args.output}")

        print(f"Runtime: {m.get('runtime') or 'none'}")
        print(f"Bridge: {m.get('bridge') or 'none'}")
        if m.get("guest_hda_type") == "blank-raw-image":
            print("Guest: blank guest.hda created; install a guest OS before it can boot.")
        print("Note: the runtime must actually execute/translate x86; the packager does not generate an emulator.")
        return 0

    except Exception as e:
        print(f"Operation failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
