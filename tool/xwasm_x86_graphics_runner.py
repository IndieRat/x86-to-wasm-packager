#!/usr/bin/env python3
"""Generate a standalone browser runner for the XWASM v0.6 graphics fixture."""

from pathlib import Path
import argparse
import json

HTML = r"""<!doctype html>
<meta charset="utf-8">
<title>XWASM X86 Runtime v0.7 — Graphics Compatibility Test</title>
<style>
body{font-family:monospace;background:#111;color:#ddd}
canvas{display:block;width:640px;height:360px;image-rendering:pixelated;border:1px solid #555;background:#101820}
pre{white-space:pre-wrap}
</style>
<canvas id="gfx" width="640" height="360"></canvas>
<pre id="log">XWASM X86 Runtime v0.7 — graphics compatibility test</pre>
<input id="picker" type="file" webkitdirectory directory>
<script>
const log=document.getElementById("log");
const canvas=document.getElementById("gfx");
const gfx=canvas.getContext("2d");
const say=s=>{log.textContent+="\n"+s;};
const rgb=c=>"#"+(c&255).toString(16).padStart(2,"0")+((c>>>8)&255).toString(16).padStart(2,"0")+((c>>>16)&255).toString(16).padStart(2,"0");

picker.onchange=async e=>{
  const files=new Map();
  for(const f of e.target.files) files.set(f.webkitRelativePath.split("/").slice(1).join("/")||f.name,f);
  try{
    const mf=files.get("manifest.xwasm.json");
    if(!mf) throw Error("manifest.xwasm.json is missing");
    const manifest=JSON.parse(await mf.text());
    if(manifest.architecture!=="x86") throw Error("Not an XWASM x86 package");
    say("Package: "+manifest.name);

    const rt=files.get(manifest.runtime||"runtime.wasm");
    const payload=files.get(manifest.payload);
    if(!rt||!payload) throw Error("runtime.wasm or payload.exe is missing");

    const mem=new WebAssembly.Memory({initial:1024,maximum:4096});
    const imports={env:{
      memory:mem,
      xwasm_log:(level,ptr,len)=>say(new TextDecoder().decode(new Uint8Array(mem.buffer,ptr,len))),
      xwasm_gfx_create:(w,h)=>{canvas.width=w;canvas.height=h;},
      xwasm_gfx_clear:(c)=>{gfx.fillStyle=rgb(c);gfx.fillRect(0,0,canvas.width,canvas.height);},
      xwasm_gfx_pixel:(x,y,c)=>{gfx.fillStyle=rgb(c);gfx.fillRect(x,y,1,1);},
      xwasm_gfx_rect:(l,t,r,b,c)=>{gfx.fillStyle=rgb(c);gfx.fillRect(l,t,r-l,b-t);},
      xwasm_gfx_present:()=>{},
      xwasm_input_poll:(ptr,remove)=>0,
      xwasm_input_quit:()=>{},
      xwasm_audio_beep:(frequency,duration)=>{}
    }};
    const {instance}=await WebAssembly.instantiate(await rt.arrayBuffer(),imports);
    const ex=instance.exports;
    say("Runtime WASM instantiated.");
    say("Runtime version: 0x"+ex.x86_get_runtime_version().toString(16));
    ex.xwasm_init?.();

    const buf=new Uint8Array(await payload.arrayBuffer());
    const stage=0x02000000;
    if(stage+buf.length>mem.buffer.byteLength) throw Error("payload staging address exceeds WASM memory");
    new Uint8Array(mem.buffer,stage,buf.length).set(buf);

    if(ex.x86_debug_probe(stage)!==0x5a4d) throw Error("runtime MZ probe failed");
    if(ex.x86_load_pe(stage,buf.length)!==0) throw Error("PE loader rejected graphics fixture");

    say("PE32 graphics fixture loaded.");
    say("Imports resolved: "+ex.x86_get_import_resolved());
    say("Imports unresolved: "+ex.x86_get_import_failed());
    say("USER32/GDI32 -> browser canvas bridge ready.");
    say("Executing window + GDI graphics test...");

    const result=ex.x86_run(64);
    say("CPU run result: "+result);
    say("Instructions executed: "+ex.x86_get_steps());
    say("EAX: 0x"+(ex.x86_get_eax()>>>0).toString(16).padStart(8,"0"));
    say("CPU halted: "+ex.x86_get_halted());

    if(result<0) throw Error("x86 CPU execution failed");
    if(!ex.x86_get_halted()) throw Error("graphics fixture did not reach HLT");
    if(ex.x86_get_import_resolved()!==6) throw Error("expected 6 resolved graphics imports");
    if(ex.x86_get_import_failed()!==0) throw Error("graphics fixture has unresolved imports");

    say("GRAPHICS PASS — x86 -> USER32/GDI32 -> browser Canvas");
    say("READY — v0.6 graphics foundation remains compatible under the v0.7 runtime.");
  }catch(err){say("ERROR: "+err.message);}
};
</script>"""
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("package",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(HTML,encoding="utf-8")
    print(a.output)
if __name__=="__main__":
    main()
