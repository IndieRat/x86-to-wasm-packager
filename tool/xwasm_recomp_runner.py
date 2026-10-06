#!/usr/bin/env python3
"""Generate an offline browser shell for an XWASM recompiled package."""
from __future__ import annotations
import argparse
from pathlib import Path

HTML=r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>XWASM Recompiled Game</title>
<style>html,body{margin:0;width:100%;height:100%;background:#111;color:#ddd;font-family:system-ui}
#status{position:fixed;left:12px;top:12px;z-index:10;white-space:pre-wrap;background:#000b;padding:10px;border-radius:6px}</style>
</head><body><pre id="status">Loading XWASM package…</pre><script>
(async()=>{
const status=document.getElementById("status"),say=x=>status.textContent=String(x);
async function bytes(p){const r=await fetch(p);if(!r.ok)throw Error("HTTP "+r.status+" for "+p);return new Uint8Array(await r.arrayBuffer())}
try{
 const r=await fetch("./manifest.xwasm.json");if(!r.ok)throw Error("manifest load failed: "+r.status);
 const m=await r.json();
 if(m.format!=="xwasm-package"||m.format_version!==1||m.architecture!=="x86-recompiled")throw Error("not an XWASM static-recompilation package");
 const wasm=await bytes("./"+m.module),image=await bytes("./"+m.image);
 if(m.bridge)await new Promise((ok,no)=>{const s=document.createElement("script");s.src="./"+m.bridge;s.onload=ok;s.onerror=()=>no(Error("bridge load failed"));document.head.appendChild(s)});
 const imports=WebAssembly.Module.imports(wasm);
 say("Package: "+m.name+"\\nModule: "+wasm.length.toLocaleString()+" bytes\\nGuest image: "+image.length.toLocaleString()+" bytes\\nImports: "+imports.length+"\\n\\nPackage ready.");
 if(window.XWASMRecompiledHost&&typeof window.XWASMRecompiledHost.start==="function"){
   await window.XWASMRecompiledHost.start({manifest:m,wasm,image,readResource:p=>bytes("./"+m.resource_root+String(p).replace(/^\\/+/, "").split("/").map(encodeURIComponent).join("/"))});
   say("XWASM recompiled host started.");
 }
}catch(e){say("XWASM boot failed: "+e.message);console.error(e)}
})();
</script></body></html>"""

def main()->int:
    ap=argparse.ArgumentParser(description="Generate an offline shell for a recompiled XWASM package.")
    ap.add_argument("package",type=Path)
    ap.add_argument("--output",type=Path)
    a=ap.parse_args()
    package=a.package.resolve()
    if not (package/"manifest.xwasm.json").is_file(): raise SystemExit("package has no manifest.xwasm.json")
    output=(a.output or package/"index.html").resolve()
    output.write_text(HTML,encoding="utf-8")
    print(f"Wrote offline shell: {output}")
    print("Serve the package directory locally; browser WASM/fetch security rules still apply.")
    return 0
if __name__=="__main__": raise SystemExit(main())
