#!/usr/bin/env python3
"""Generate a standalone browser runner for an XWASM architecture=x86 package."""
from __future__ import annotations
import argparse, json
from pathlib import Path

HTML = r'''<!doctype html>
<meta charset="utf-8">
<title>XWASM X86 Runtime v0.2</title>
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
  for(const f of e.target.files)
    files.set(f.webkitRelativePath.split("/").slice(1).join("/")||f.name,f);

  try{
    const manifestFile=files.get("manifest.xwasm.json");
    if(!manifestFile) throw Error("manifest.xwasm.json is missing");

    const manifest=JSON.parse(await manifestFile.text());
    if(manifest.format!=="xwasm-package"||manifest.architecture!=="x86")
      throw Error("Not an XWASM x86 package");

    say("Package: "+manifest.name);
    say("Payload: "+manifest.payload);
    say("Bundled DLLs: "+((manifest.bundled_dlls||[]).length));

    const rt=files.get(manifest.runtime||"runtime.wasm");
    if(!rt) throw Error("runtime.wasm is missing");

    const mem=new WebAssembly.Memory({initial:1024,maximum:4096});
    const bytes=await rt.arrayBuffer();
    const pkg={
      get:p=>files.get(p)||files.get("resources/"+p),
      readString:(ptr,len)=>new TextDecoder().decode(new Uint8Array(mem.buffer,ptr,len))
    };

    const imports={env:{
      memory:mem,
      xwasm_log:(level,ptr,len)=>{
        say(new TextDecoder().decode(new Uint8Array(mem.buffer,ptr,len)));
      },
      xwasm_resource_size:(ptr,len)=>{
        const p=pkg.readString(ptr,len),f=pkg.get(p);
        return f?f.size:-1;
      },
      xwasm_resource_read:(ptr,len,dst,dstLen,off)=>{
        const p=pkg.readString(ptr,len),f=pkg.get(p);
        if(!f)return -1;
        return -2;
      }
    }};

    const {instance}=await WebAssembly.instantiate(bytes,imports);
    const ex=instance.exports;
    say("Runtime WASM instantiated.");

    if(!ex.x86_get_runtime_version)
      throw Error("x86_get_runtime_version export missing");

    say("Runtime version: 0x"+ex.x86_get_runtime_version().toString(16));

    if(ex.xwasm_init)
      ex.xwasm_init();

    const payload=files.get(manifest.payload);
    if(!payload) throw Error("payload missing: "+manifest.payload);

    const buf=new Uint8Array(await payload.arrayBuffer());
    say("Payload bytes: "+buf.length);
    say("Payload first 32 bytes: "+hex(buf,32));

    const dv=new DataView(buf.buffer);
    if(buf.length<0x40) throw Error("payload is too small for PE/DOS header");
    if(dv.getUint16(0,true)!==0x5a4d) throw Error("payload is not MZ");

    const pe=dv.getUint32(0x3c,true);
    say("PE header offset: 0x"+pe.toString(16));
    if(pe+24>buf.length) throw Error("payload PE header is outside file");

    say("PE signature: "+hex(buf.slice(pe,pe+4),4));
    if(dv.getUint32(pe,true)!==0x4550) throw Error("payload is not PE");

    const machine=dv.getUint16(pe+4,true);
    const sectionCount=dv.getUint16(pe+6,true);
    const optionalSize=dv.getUint16(pe+20,true);
    const optional=pe+24;

    say("PE machine: 0x"+machine.toString(16).padStart(4,"0"));
    say("PE sections: "+sectionCount);
    say("Optional header size: 0x"+optionalSize.toString(16).padStart(4,"0"));

    if(optional+2>buf.length) throw Error("optional header magic is outside file");

    const optionalMagic=dv.getUint16(optional,true);
    say("Optional header magic: 0x"+optionalMagic.toString(16).padStart(4,"0"));

    if(machine!==0x14c) throw Error("test payload is not i386 PE32");
    if(optionalMagic!==0x10b)
      throw Error("test payload is not PE32 (expected optional-header magic 0x010b)");

    const stage=0x02000000;
    if(stage+buf.length>mem.buffer.byteLength)
      throw Error("payload staging address exceeds WASM memory");

    new Uint8Array(mem.buffer,stage,buf.length).set(buf);

    say("Payload staged at 0x"+stage.toString(16));
    say("Staged first 32 bytes: "+hex(new Uint8Array(mem.buffer,stage,32),32));

    const staged=new DataView(mem.buffer);
    const stagedPe=stage+staged.getUint32(stage+0x3c,true);

    say("Staged MZ: 0x"+staged.getUint16(stage,true).toString(16).padStart(4,"0"));
    say("Staged PE offset: 0x"+(stagedPe-stage).toString(16));
    say("Staged PE signature: "+hex(new Uint8Array(mem.buffer,stagedPe,4),4));
    say("Staged Optional Magic: 0x"+staged.getUint16(stagedPe+24,true).toString(16).padStart(4,"0"));

    if(!ex.x86_debug_probe)
      throw Error("x86_debug_probe export missing");

    const probe=ex.x86_debug_probe(stage);
    say("Runtime probe MZ: 0x"+probe.toString(16).padStart(4,"0"));

    if(probe!==0x5a4d)
      throw Error("runtime imported-memory probe failed");

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

      if(ex.x86_get_load_ptr)
        say("Runtime received ptr: 0x"+ex.x86_get_load_ptr().toString(16));

      if(ex.x86_get_load_size)
        say("Runtime received size: "+ex.x86_get_load_size());

      say("Loader diagnostic "+code+": "+(reasons[code]||"unknown loader error"));
      say("Runtime loaded flag: "+ex.x86_get_loaded());
      throw Error("PE loader rejected payload");
    }

    say("PE32 payload loaded into guest memory.");
    say("Entry EIP: 0x"+ex.x86_get_eip().toString(16));

    if(!ex.x86_run||!ex.x86_get_eax||!ex.x86_get_eflags||!ex.x86_get_halted)
      throw Error("x86 v0.2 CPU execution exports are missing");

    say("CPU: 32-bit fetch/decode/execute core");
    say("Executing deterministic PE entrypoint (budget: 16 instructions)...");
    const runResult=ex.x86_run(16);
    say("CPU run result: "+runResult);
    say("Instructions executed: "+ex.x86_get_steps());
    say("EIP after execution: 0x"+ex.x86_get_eip().toString(16));
    say("EAX: 0x"+ex.x86_get_eax().toString(16).padStart(8,"0"));
    say("EFLAGS: 0x"+ex.x86_get_eflags().toString(16).padStart(8,"0"));
    say("CPU halted: "+ex.x86_get_halted());

    if(runResult<0)
      throw Error("x86 CPU execution failed; opcode/error=0x"+(ex.x86_get_cpu_error?ex.x86_get_cpu_error():0).toString(16));
    if(!ex.x86_get_halted())
      throw Error("x86 CPU did not reach HLT within the instruction budget");
    if(ex.x86_get_eax()!==42)
      throw Error("deterministic CPU test expected EAX=42 after the CALL/RET test");
    if(ex.x86_get_steps()!==3)
      throw Error("deterministic CPU test expected exactly 8 instructions");

    say("CPU test: NOP -> XOR EAX,EAX -> HLT = PASS");
    say("DLL inventory:");

    for(const d of (manifest.bundled_dlls||[]))
      say("  "+d);

    say("READY — v0.2 x86 execution foundation reached.");
  }catch(err){
    say("ERROR: "+err.message);
  }
};
</script>
'''

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("package",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    m=json.loads((a.package/"manifest.xwasm.json").read_text(encoding="utf-8"))
    if m.get("architecture")!="x86":
        raise SystemExit("package architecture must be x86")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(HTML,encoding="utf-8")
    print(a.output)

if __name__=="__main__":
    main()
