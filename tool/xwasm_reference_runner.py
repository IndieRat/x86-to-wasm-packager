#!/usr/bin/env python3
"""Generate a self-contained HTML XWASM native-WASM reference runner.

The reference runner intentionally supports only architecture=wasm32.
An x86 XWASM package contains a PE payload, not a browser-native WASM module;
it must be run by a separate x86 compatibility runtime.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    root = args.package.resolve()
    manifest = json.loads((root / "manifest.xwasm.json").read_text(encoding="utf-8"))
    architecture = manifest.get("architecture")
    if architecture != "wasm32":
        raise SystemExit(
            "xwasm_reference_runner only runs native wasm32 packages. "
            f"This package is architecture={architecture!r}; use an x86 XWASM runtime/runner instead."
        )

    module_name = manifest.get("module")
    if not isinstance(module_name, str) or not module_name:
        raise SystemExit("Native wasm32 package is missing manifest.module.")

    module_path = root / module_name
    if not module_path.is_file():
        raise SystemExit(f"Native wasm32 module not found: {module_name}")

    wasm = base64.b64encode(module_path.read_bytes()).decode()
    manifest_json = json.dumps(manifest)

    html = r'''<!doctype html>
<meta charset="utf-8">
<title>XWASM Reference Runner</title>
<style>
body{font:14px system-ui;margin:0;background:#111;color:#eee}
header{padding:12px 16px;background:#1b1b1b;border-bottom:1px solid #333}
#status{padding:12px 16px}
#log{margin:0;padding:12px 16px;white-space:pre-wrap;font:13px ui-monospace,monospace;max-height:70vh;overflow:auto}
.ok{color:#8f8}.bad{color:#f88}
</style>
<header><b>XWASM Reference Runner</b></header>
<div id="status">Starting...</div>
<pre id="log"></pre>
<script>
"use strict";
const MANIFEST = __MANIFEST__;
const WASM_B64 = "__WASM__";
const ABI = "xwasm.host/1";
const logEl = document.querySelector("#log");
const statusEl = document.querySelector("#status");

function log(s){ logEl.textContent += s + "\n"; console.log("[XWASM]", s); }
function fail(e){ statusEl.textContent="BOOT FAILED"; statusEl.className="bad"; log("ERROR: "+(e?.stack||e)); }
function bytes(){
  const raw=atob(WASM_B64), out=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++) out[i]=raw.charCodeAt(i);
  return out;
}
async function boot(){
  log("Package signature: "+MANIFEST.format);
  if(MANIFEST.format!=="xwasm-package") throw new Error("Not an XWASM package");
  if(MANIFEST.format_version!==1) throw new Error("Unsupported XWASM format version");
  log("Format version: "+MANIFEST.format_version);
  log("Architecture: "+MANIFEST.architecture);
  if(MANIFEST.architecture!=="wasm32") throw new Error("Reference runner only supports wasm32 packages");
  log("ABI: "+MANIFEST.abi);
  if(MANIFEST.abi!==ABI) throw new Error("Unsupported ABI: "+MANIFEST.abi);

  const wasmBytes=bytes();
  if(!WebAssembly.validate(wasmBytes)) throw new Error("WebAssembly.validate() rejected module");
  log("WASM validation: OK");

  const module=await WebAssembly.compile(wasmBytes);
  const imports=WebAssembly.Module.imports(module);
  const exports=WebAssembly.Module.exports(module);
  log("Imports: "+imports.map(x=>x.module+"."+x.name).join(", ") || "(none)");
  log("Exports: "+exports.map(x=>x.name).join(", ") || "(none)");

  let instance=null;
  const host={
    log(level,ptr,len){
      if(!instance?.exports?.memory) return;
      const text=new TextDecoder().decode(new Uint8Array(instance.exports.memory.buffer,ptr,len));
      log("WASM["+level+"]: "+text);
    },
    time_ms(){ return Math.floor(performance.now()); },
    resource_size(){ return -1; },
    resource_open_async(){ return -1; },
    resource_read(){ return -1; },
    resource_close(){},
    exit(code){ log("WASM requested exit("+code+")"); }
  };

  const result=await WebAssembly.instantiate(module,{"xwasm.host":host});
  instance=result;
  log("Instantiation: OK");

  const init=instance.exports[MANIFEST.entry?.init||"xwasm_init"];
  const tick=instance.exports[MANIFEST.entry?.tick||"xwasm_tick"];
  const shutdown=instance.exports[MANIFEST.entry?.shutdown||"xwasm_shutdown"];

  if(typeof init!=="function") throw new Error("Missing XWASM init export");
  init();
  log("Lifecycle: xwasm_init() OK");
  if(typeof tick==="function"){ tick(0); log("Lifecycle: xwasm_tick(0) OK"); }
  if(typeof shutdown==="function"){ shutdown(); log("Lifecycle: xwasm_shutdown() OK"); }

  statusEl.textContent="BOOT OK — XWASM reference package executed";
  statusEl.className="ok";
}
boot().catch(fail);
</script>
'''
    html = html.replace("__MANIFEST__", manifest_json).replace("__WASM__", wasm)
    args.output.resolve().write_text(html, encoding="utf-8")
    print(f"Created runner: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
