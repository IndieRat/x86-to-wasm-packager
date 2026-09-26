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
