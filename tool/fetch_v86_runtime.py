#!/usr/bin/env python3
"""Fetch a v86 runtime bundle for local/offline profile testing.

This downloads the browser runtime pieces plus a small FreeDOS guest image
used only to verify that the v86 runtime can boot a real x86 guest. The generated
bridge uses v86's in-memory wasm_fn/buffer APIs so packages can be consumed from
an offline file:// page without URL-based ROM/disk fetches.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

API = "https://api.github.com/repos/copy/v86/releases/tags/latest"
GUEST_IMAGES = {
    "freedos722.img": "https://i.copy.sh/freedos722.img",
}

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
    ap.add_argument("--no-guest-image", action="store_true",
                    help="Do not include any guest image.")
    ap.add_argument("--guest-hda", type=Path,
                    help="Copy an existing bootable disk image into the runtime bundle as guest.hda.")
    ap.add_argument("--guest-hda-url",
                    help="Download a bootable disk image from a direct URL and save it as guest.hda.")
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

    guest_image = None
    if args.guest_hda and args.guest_hda_url:
        raise ValueError("Use either --guest-hda or --guest-hda-url, not both.")
    if args.guest_hda:
        if not args.guest_hda.is_file():
            raise FileNotFoundError(f"Guest HDA not found: {args.guest_hda}")
        (out / "guest.hda").write_bytes(args.guest_hda.read_bytes())
        guest_image = "guest.hda"
    elif args.guest_hda_url:
        (out / "guest.hda").write_bytes(get(args.guest_hda_url))
        guest_image = "guest.hda"
    elif not args.no_guest_image:
        name, url = next(iter(GUEST_IMAGES.items()))
        (out / name).write_bytes(get(url))
        guest_image = name

    bridge = r'''/* v86 profile-test bridge.
 * This is for testing the x86/WASM profile itself.
 * It boots a supplied guest disk using v86. The bundled FreeDOS image is only
 * a smoke test; a PE32 payload is not automatically installed into that guest.
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

    // A real guest disk is required for this v86 profile.
    const image = p.manifest.guest_hda || p.manifest.hda || p.manifest.cdrom;
    if (!image) {
      throw new Error(
        "No guest disk image is supplied. The x86 runtime is loaded, but a PE payload " +
        "cannot run by itself; provide a bootable guest disk as guest.hda."
      );
    }
    if (p.manifest.guest_hda) {
      console.log("[X86] Booting guest disk:", p.manifest.guest_hda);
    }

    const emulator = window.emulator = new V86({
      wasm_fn: async (imports) =>
        (await WebAssembly.instantiate(await p.read("runtime.wasm"), imports)).instance.exports,
      memory_size: p.manifest.memory_size || 128 * 1024 * 1024,
      vga_memory_size: p.manifest.vga_memory_size || 4 * 1024 * 1024,
      screen_container: screen,
      bios: { buffer: await p.read("seabios.bin") },
      vga_bios: { buffer: await p.read("vgabios.bin") },
      hda: { buffer: await p.read(image) },
      ...(p.manifest.guest_hdb ? { hdb: { buffer: await p.read(p.manifest.guest_hdb) } } : {}),
      autostart: true,
      disable_speaker: true
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
        "files": ["runtime.wasm", "libv86.js", "seabios.bin", "vgabios.bin", "bridge.js"] + ([guest_image] if guest_image else []),
        "guest_hda": guest_image,
        "note": "Guest disk is optional. When present, it is booted as guest.hda; the packager does not create a Windows installation or install the PE payload into the guest."
    }, indent=2), encoding="utf-8")

    print("v86 runtime bundle created:", out)
    print("Files: runtime.wasm, libv86.js, seabios.bin, vgabios.bin, bridge.js")
    if guest_image:
        print("Guest disk:", guest_image)
    else:
        print("Guest disk: none (supply --guest-hda or --guest-hda-url)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("Runtime fetch failed:", e, file=sys.stderr)
        raise SystemExit(1)
