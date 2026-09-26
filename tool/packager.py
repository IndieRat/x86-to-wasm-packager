#!/usr/bin/env python3
"""Package a 32-bit x86 Windows game folder for a browser x86/WASM runtime."""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


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
        raise ValueError(f"Unsupported machine 0x{machine:04X}; expected PE32/i386 (0x014C).")
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
  const resourceUrl = path =>
    "./resources/" + String(path).replace(/^\/+/, "").split("/").map(encodeURIComponent).join("/");
  window.__X86_WASM_PACKAGE__ = {
    manifest, payload, runtime, resourceUrl,
    readResource: async path => new Uint8Array(await fetch(resourceUrl(path)).then(r => r.arrayBuffer()))
  };
  return window.__X86_WASM_PACKAGE__;
}
window.loadX86Package = loadX86Package;
''', encoding="utf-8")

    (out / "index.html").write_text(r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>x86 WASM Port</title></head>
<body style="font-family:system-ui;background:#0b1020;color:#e5e7eb;padding:24px">
<h2 id="title">Loading package…</h2><pre id="status"></pre>
<script src="./loader.js"></script><script>
(async()=>{try{
 const p=await loadX86Package();
 document.getElementById("title").textContent=p.manifest.name;
 document.getElementById("status").textContent=
 "Package loaded.\\nExecutable: "+p.manifest.executable+
 "\\nResources: "+p.manifest.resource_file_count+
 "\\nRuntime: "+(p.manifest.runtime||"none")+
 "\\n\\nA runtime.wasm must actually execute/translate x86; packaging alone does not run a Windows EXE.";
}catch(e){document.getElementById("status").textContent="Load failed: "+e.message;console.error(e)}})();
</script></body></html>
''', encoding="utf-8")


def package(game: Path, out: Path, exe_name: str | None,
            runtime: Path | None, bridge: Path | None, name: str | None) -> dict:
    game = game.resolve()
    out = out.resolve()
    if not game.is_dir():
        raise ValueError("Input must be a game folder.")
    if out == game or game in out.parents:
        raise ValueError("Output must not be inside the source game folder.")

    exe = find_exe(game, exe_name)
    info = pe32_info(exe)
    out.mkdir(parents=True, exist_ok=True)

    shutil.copy2(exe, out / "payload.bin")
    count = copy_resources(game, out, exe)

    if runtime:
        if not runtime.is_file():
            raise FileNotFoundError(f"Runtime not found: {runtime}")
        shutil.copy2(runtime, out / "runtime.wasm")
    if bridge:
        if not bridge.is_file():
            raise FileNotFoundError(f"Bridge not found: {bridge}")
        shutil.copy2(bridge, out / "bridge.js")

    write_loader(out)
    manifest = {
        "bundle_version": "2.0",
        "format": "x86-wasm-package",
        "name": name or game.name,
        "architecture": "x86",
        "machine": "i386",
        "source_type": "game-folder",
        "executable": exe.name,
        "payload": "payload.bin",
        "runtime": "runtime.wasm" if runtime else None,
        "bridge": "bridge.js" if bridge else None,
        "runtime_required": bool(runtime),
        "resource_root": "resources/",
        "resource_file_count": count,
        "entry": "x86_run",
        "entry_point": info["entry_point"],
        "file_size": info["file_size"],
        "sections": info["sections"],
        "sha256": sha256(exe),
        "execution_note": "runtime.wasm must provide the actual x86 execution/translation layer; this tool only packages the PE32 and its resources."
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Turn an x86 Windows game folder into an x86/WASM package.")
    ap.add_argument("game_folder", type=Path)
    ap.add_argument("--output", type=Path, default=Path("dist/game"))
    ap.add_argument("--exe", help="Executable path relative to the game folder when auto-detection is not desired.")
    ap.add_argument("--runtime-wasm", type=Path, help="Compatible x86 execution/translation runtime.")
    ap.add_argument("--bridge", type=Path, help="Optional JavaScript bridge.")
    ap.add_argument("--name")
    args = ap.parse_args()
    try:
        m = package(args.game_folder, args.output, args.exe, args.runtime_wasm, args.bridge, args.name)
    except Exception as e:
        print(f"Packaging failed: {e}", file=sys.stderr)
        return 1
    print(f"Package: {args.output}")
    print(f"Executable: {m['executable']}")
    print(f"Resources: {m['resource_file_count']} files")
    print(f"Runtime: {m['runtime'] or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
