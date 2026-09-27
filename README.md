# x86-to-wasm-packager

Packages a 32-bit x86 Windows game folder into a browser-ready x86/WASM package.

## Folder -> package

Given:

```text
MyGame/
├── Game.exe
├── data/
├── textures/
├── sounds/
└── config/
```

Run:

```bash
python3 tool/packager.py ./MyGame --output ./dist/MyGame
```

The tool validates the selected PE32 executable, copies it to `payload.bin`, and copies the rest of the game folder under `resources/`.

If you have a real x86 execution/translation runtime:

```bash
python3 tool/packager.py ./MyGame \
  --output ./dist/MyGame \
  --runtime-wasm ./runtime.wasm \
  --bridge ./bridge.js
```

The output is:

```text
dist/MyGame/
├── index.html
├── loader.js
├── manifest.json
├── payload.bin
├── runtime.wasm
├── bridge.js
└── resources/
    ├── data/
    ├── textures/
    ├── sounds/
    └── config/
```

## Multiple executables

Use `--exe` when the folder contains several executables:

```bash
python3 tool/packager.py ./MyGame \
  --exe bin/GameLauncher.exe \
  --output ./dist/MyGame
```

## Test

The generated shell uses `fetch()`, so serve the output:

```bash
cd dist/MyGame
python3 -m http.server 8000
```

Then open `http://localhost:8000/index.html`.

## Important limitation

This repository is a **packaging layer**, not a universal Windows emulator. A random Windows EXE is not converted into WebAssembly by this Python script.

For actual execution, `runtime.wasm` must contain the x86 execution/translation layer and support the Windows APIs, filesystem, graphics, audio, input, and other facilities required by the game. The generated `loader.js` exposes the package data so that a compatible runtime or bridge can consume it.

The package format is intentionally simple so the browser side can be matched to the actual runtime ABI.

## Runtime bundle and existing-port updates

The packager does not generate an x86 CPU emulator/translator. `runtime.wasm` is an actual execution/translation engine supplied separately. A compatible `bridge.js` connects that runtime to the package.

Put a compatible pair in one directory:

```text
runtime/
├── runtime.wasm
└── bridge.js
```

Build a package with that pair:

```bash
python3 tool/packager.py ./MyGame --output ./dist/MyGame --runtime-dir ./runtime
```

Or supply the files individually with `--runtime-wasm` and `--bridge`.

### Update an existing port

You can add the runtime later without rebuilding the game files:

```bash
python3 tool/packager.py --update-port ./dist/MyGame --runtime-dir ./runtime
```

This preserves `payload.bin` and `resources/`, copies/replaces `runtime.wasm` and `bridge.js`, updates `manifest.json`, and refreshes `loader.js`.

The generated bridge expects the real runtime to expose:

```js
window.X86Runtime.start({ payload, manifest, readResource })
```

If a runtime uses another ABI, provide its matching bridge with `--bridge`.

Important: a package containing a PE32 executable is not itself a browser-native WASM executable. The runtime must actually implement x86 execution/translation and the compatibility facilities required by the target game.

## Built-in guest disk builder

The packager can now create a raw `guest.hda` without requiring QEMU to be installed:

```bash
python3 tool/packager.py ./MyGame \
  --output ./dist/MyGame \
  --runtime-dir ./runtime \
  --guest-auto \
  --guest-size 2G
```

This creates a real raw `guest.hda` alongside the package files.

`guest.hda` is initially **blank**. The builder intentionally does not bundle or install an operating system. A guest OS must be installed before v86 can boot it. v86 supports hard-disk images directly, including images supplied as buffers.

You can also use the standalone builder:

```bash
python3 tool/guest_builder.py --output ./guest.hda --size 2G
```

Or copy an existing raw guest image:

```bash
python3 tool/guest_builder.py \
  --output ./guest.hda \
  --from-image ./existing.img
```

This removes the need to use `qemu-img` merely to create an empty disk. It does not turn a blank disk into a Windows installation, and it does not automatically install a game into the guest OS.
