#!/usr/bin/env python3
"""Fetch a v86 runtime bundle for local/offline profile testing.

This downloads only the browser runtime pieces. It does not download an OS image.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

API = "https://api.github.com/repos/copy/v86/releases/tags/latest"
BIOS = {
    "seabios.bin": "https://raw.githubusercontent.com/copy/v86/master/bios/seabios.bin",
    "vgabios.bin": "https://raw.githubusercontent.com/copy/v86/master/bios/vgabios.bin",
}


def get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "x86-to-wasm-packager/1.0", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=Path("runtime-v86"))
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)

    release = json.loads(get(API).decode("utf-8"))
    assets = release.get("assets", [])

    def asset_named(name):
        for a in assets:
            if a.get("name") == name:
                return a.get("browser_download_url")
        return None

    wasm_url = next(
        (a.get("browser_download_url") for a in assets
         if a.get("name", "").startswith("v86") and a.get("name", "").endswith(".wasm")
         and "debug" not in a.get("name", "").lower()),
        None,
    )
    js_url = next(
        (a.get("browser_download_url") for a in assets
         if a.get("name", "").startswith("libv86") and a.get("name", "").endswith(".js")
         and "debug" not in a.get("name", "").lower()),
        None,
    )

    if not wasm_url or not js_url:
        raise RuntimeError("Could not find release v86 WASM/libv86.js assets.")

    (out / "runtime.wasm").write_bytes(get(wasm_url))
    (out / "libv86.js").write_bytes(get(js_url))

    for name, url in BIOS.items():
        (out / name).write_bytes(get(url))

    bridge = r'''/* v86 profile-test bridge.
 * This is for testing the x86/WASM profile itself.
 * It boots a supplied disk image using v86; it does NOT turn a PE32
 * executable into a bootable disk image.
 */
(function () {
  "use strict";

  function loadScript(url) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = url;
      s.onload = resolve;
      s.onerror = () => reject(new Error("Failed to load " + url));
      document.head.appendChild(s);
    });
  }

  async function start() {
    const p = window.__X86_WASM_PACKAGE__;
    if (!p) throw new Error("Package is not loaded.");

    await loadScript("./libv86.js");

    if (typeof window.V86 !== "function") {
      throw new Error("libv86.js loaded, but V86 was not exposed.");
    }

    const screen = document.getElementById("x86-screen") ||
      (() => {
        const e = document.createElement("div");
        e.id = "x86-screen";
        e.innerHTML =
          '<div style="white-space:pre;font:14px monospace;line-height:14px"></div>' +
          '<canvas></canvas>';
        document.body.appendChild(e);
        return e;
      })();

    const image = p.manifest.test_image || p.manifest.hda || p.manifest.cdrom;
    if (!image) {
      throw new Error(
        "Profile runtime test is ready, but no test disk image was supplied. " +
        "Add a bootable image and set manifest.test_image."
      );
    }

    const emulator = window.emulator = new V86({
      wasm_path: "./runtime.wasm",
      memory_size: p.manifest.memory_size || 128 * 1024 * 1024,
      vga_memory_size: p.manifest.vga_memory_size || 4 * 1024 * 1024,
      screen_container: screen,
      bios: { url: "./seabios.bin" },
      vga_bios: { url: "./vgabios.bin" },
      hda: { url: "./" + image },
      autostart: true
    });

    return emulator;
  }

  window.X86Runtime = {
    start
  };

  window.X86WasmBridge = {
    start
  };

  window.initializeX86Wasm = start;
})();
'''
    (out / "bridge.js").write_text(bridge, encoding="utf-8")

    (out / "runtime.json").write_text(json.dumps({
        "runtime": "v86",
        "source": "https://github.com/copy/v86",
        "release_tag": release.get("tag_name"),
        "release_name": release.get("name"),
        "files": ["runtime.wasm", "libv86.js", "seabios.bin", "vgabios.bin", "bridge.js"],
        "test_image": "supply-your-own.img",
        "note": "A bootable x86 disk image is still required for an emulator profile test."
    }, indent=2), encoding="utf-8")

    print("v86 runtime bundle created:", out)
    print("Files: runtime.wasm, libv86.js, seabios.bin, vgabios.bin, bridge.js")
    print("A bootable disk image is intentionally not downloaded.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("Runtime fetch failed:", e, file=sys.stderr)
        raise SystemExit(1)
