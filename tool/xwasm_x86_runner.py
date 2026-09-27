#!/usr/bin/env python3
"""Generate a standalone browser runner for an XWASM architecture=x86 package."""
from __future__ import annotations
import argparse, json
from pathlib import Path

HTML = r'''<!doctype html>
<meta charset="utf-8">
<title>XWASM X86 Runtime v0.1</title>
<pre id="log">XWASM X86 Runtime v0.1
Select the package directory.</pre>
<input id="files" type="file" webkitdirectory multiple>
<script>
const out=document.querySelector("#log");
const say=s=>{out.textContent+="\n"+s;};
const files=new Map();
const hex=(u8,n=32)=>Array.from(u8.slice(0,n),b=>b.toString(16).padStart(2,"0")).join(" ");
document.querySelector("#files").onchange=async e=>{
  files.clear();
  for(const f of e.target.files) files.set(f.webkitRelativePath.split("/").slice(1).join("/")||f.name,f);
  try{
    const manifest=JSON.parse(await files.get("manifest.xwasm.json").text());
    if(manifest.format!=="xwasm-package"||manifest.architecture!=="x86") throw Error("Not an XWASM x86 package");
    say("Package: "+manifest.name);
    say("Payload: "+manifest.payload);
    say("Bundled DLLs: "+((manifest.bundled_dlls||[]).length));
    const rt=files.get(manifest.runtime||"runtime.wasm");
    if(!rt) throw Error("runtime.wasm is missing");
    const mem=new WebAssembly.Memory({initial:1024,maximum:4096});
    const bytes=await rt.arrayBuffer();
    const pkg={get:p=>files.get(p)||files.get("resources/"+p),readString:(ptr,len)=>new TextDecoder().decode(new Uint8Array(mem.buffer,ptr,len))};
    const imports={env:{
      memory:mem,
      xwasm_log:(level,ptr,len)=>say(new TextDecoder().decode(new Uint8Array(mem.buffer,ptr,len))),
      xwasm_resource_size:(ptr,len)=>{const p=pkg.readString(ptr,len),f=pkg.get(p);return f?f.size:-1;},
      xwasm_resource_read:(ptr,len,dst,dstLen,off)=>{const p=pkg.readString(ptr,len),f=pkg.get(p);if(!f)return -1;return -2;}
    }};
    const {instance}=await WebAssembly.instantiate(bytes,imports);
    const ex=instance.exports;
    say("Runtime WASM instantiated.");
    if(ex.xwasm_init) ex.xwasm_init();
    const payload=files.get(manifest.payload);
    if(!payload) throw Error("payload missing: "+manifest.payload);
    const buf=new Uint8Array(await payload.arrayBuffer());
    say("Payload bytes: "+buf.length);
    say("Payload first 32 bytes: "+hex(buf,32));
    const dv=new DataView(buf.buffer);
    if(dv.getUint16(0,true)!==0x5a4d) throw Error("payload is not MZ");
    const pe=dv.getUint32(0x3c,true);
    say("PE header offset: 0x"+pe.toString(16));
    if(pe+4>buf.length) throw Error("payload PE offset is outside file");
    say("PE signature: "+hex(buf.slice(pe,pe+4),4));
    if(dv.getUint32(pe,true)!==0x4550) throw Error("payload is not PE");
    const stage=0x02000000;
    if(stage+buf.length>mem.buffer.byteLength) throw Error("payload staging address exceeds WASM memory");
    new Uint8Array(mem.buffer,stage,buf.length).set(buf);
    say("Payload staged at 0x"+stage.toString(16));
    say("Staged first 32 bytes: "+hex(new Uint8Array(mem.buffer,stage,32),32));
    const loadResult=ex.x86_load_pe(stage,buf.length);
    if(loadResult!==0){
      const code=ex.x86_get_load_error?ex.x86_get_load_error():0;
      const reasons={
        1:"payload too small for DOS header",
        2:"DOS header missing MZ signature",
        3:"e_lfanew points outside the payload",
        4:"PE header extends outside the payload",
        5:"PE signature is invalid",
        6:"PE machine is not i386 (0x014c)",
        7:"PE optional header is smaller than PE32 minimum",
        8:"optional header extends outside the payload",
        9:"optional header is not PE32 (0x010b)",
        10:"SizeOfImage is invalid",
        11:"SizeOfHeaders exceeds payload size",
        12:"section table extends outside the payload",
        13:"section destination exceeds guest image limit",
        14:"section raw data extends outside the payload"
      };
      say("ERROR: x86_load_pe failed: "+loadResult);
      say("Loader diagnostic "+code+": "+(reasons[code]||"unknown loader error"));
      say("Runtime loaded flag: "+ex.x86_get_loaded());
      throw Error("PE loader rejected payload");
    }
    say("PE32 payload loaded into guest memory.");
    say("Entry EIP: 0x"+ex.x86_get_eip().toString(16));
    say("DLL inventory:");
    for(const d of (manifest.bundled_dlls||[])) say("  "+d);
    say("READY — v0.1 loader foundation reached.");
  }catch(err){say("ERROR: "+err.message);}
};
</script>
'''
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("package",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    m=json.loads((a.package/"manifest.xwasm.json").read_text(encoding="utf-8"))
    if m.get("architecture")!="x86": raise SystemExit("package architecture must be x86")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(HTML,encoding="utf-8")
    print(a.output)
if __name__=="__main__": main()
