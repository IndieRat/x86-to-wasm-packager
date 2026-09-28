#!/usr/bin/env python3
"""Generate the browser runner for the v0.8 x86 CPU foundation stress test."""
from __future__ import annotations
import argparse, json
from pathlib import Path

HTML = r'''<!doctype html>
<meta charset="utf-8">
<title>XWASM X86 Runtime v0.8 — CPU Foundation Stress Test</title>
<pre id="log">XWASM X86 Runtime v0.8
CPU Foundation Stress Test
Select the generated package directory.</pre>
<input id="files" type="file" webkitdirectory multiple>
<script>
const out=document.querySelector("#log");
const say=s=>{out.textContent+="\n"+s;};
const files=new Map();
const hex=n=>"0x"+(n>>>0).toString(16).padStart(8,"0");

document.querySelector("#files").onchange=async e=>{
  files.clear();
  for(const f of e.target.files)
    files.set(f.webkitRelativePath.split("/").slice(1).join("/")||f.name,f);
  try{
    const mf=files.get("manifest.xwasm.json");
    if(!mf) throw Error("manifest.xwasm.json is missing");
    const manifest=JSON.parse(await mf.text());
    if(manifest.architecture!=="x86") throw Error("Not an XWASM x86 package");
    if(!/CPU-Foundation-Stress/i.test(manifest.name||""))
      say("WARNING: package name does not look like the CPU foundation stress package.");

    const rt=files.get(manifest.runtime||"runtime.wasm");
    const payload=files.get(manifest.payload);
    if(!rt) throw Error("runtime.wasm is missing");
    if(!payload) throw Error("payload is missing: "+manifest.payload);

    const mem=new WebAssembly.Memory({initial:1024,maximum:4096});
    const bytes=await rt.arrayBuffer();
    const imports={env:{
      memory:mem,
      xwasm_log:(level,ptr,len)=>{
        const s=new TextDecoder().decode(new Uint8Array(mem.buffer,ptr,len));
        say("[RUNTIME] "+s);
      },
      xwasm_gfx_create:()=>{},
      xwasm_gfx_clear:()=>{},
      xwasm_gfx_pixel:()=>{},
      xwasm_gfx_rect:()=>{},
      xwasm_gfx_present:()=>{},
      xwasm_input_poll:()=>0,
      xwasm_input_quit:()=>{},
      xwasm_audio_beep:()=>{}
    }};
    const {instance}=await WebAssembly.instantiate(bytes,imports);
    const ex=instance.exports;
    say("Runtime WASM instantiated.");
    say("Runtime version: "+hex(ex.x86_get_runtime_version()));
    if(ex.xwasm_init) ex.xwasm_init();

    const buf=new Uint8Array(await payload.arrayBuffer());
    say("Payload bytes: "+buf.length);

    const stage=0x02000000;
    new Uint8Array(mem.buffer,stage,buf.length).set(buf);
    say("Payload staged at "+hex(stage));

    const load=ex.x86_load_pe(stage,buf.length);
    if(load!==0){
      say("CPU STRESS LOAD FAIL: x86_load_pe returned "+load);
      say("Loader error: "+(ex.x86_get_load_error?ex.x86_get_load_error():0));
      throw Error("PE32 stress fixture failed to load");
    }

    say("PE32 stress fixture loaded.");
    say("Entry EIP: "+hex(ex.x86_get_eip()));

    const budget=2000;
    const result=ex.x86_run(budget);
    const steps=ex.x86_get_steps();
    const eax=ex.x86_get_eax()>>>0;
    const eflags=ex.x86_get_eflags()>>>0;
    const halted=ex.x86_get_halted();
    const err=ex.x86_get_cpu_error?ex.x86_get_cpu_error()>>>0:0;

    say("CPU run result: "+result);
    say("Instructions executed: "+steps);
    say("EAX: "+hex(eax));
    say("EFLAGS: "+hex(eflags));
    say("CPU halted: "+halted);
    if(result<0){
      say("CPU UNSUPPORTED/FAULT");
      say("EIP: "+hex(ex.x86_get_eip()));
      say("Opcode: "+hex(ex.x86_get_current_opcode?ex.x86_get_current_opcode():0));
      say("CPU error: "+hex(err));
      throw Error("CPU execution failed");
    }
    if(!halted) throw Error("stress program exceeded "+budget+" instructions");
    if(eax===0xC0DEF00D){
      say("");
      say("========================================");
      say("CPU FOUNDATION STRESS TEST: PASS");
      say("All encoded foundation checks reached SUCCESS.");
      say("========================================");
    }else if(eax===0xDEADC0DE){
      say("");
      say("CPU FOUNDATION STRESS TEST: FAIL");
      say("A self-check branch reached the failure marker.");
      throw Error("one or more CPU instruction checks failed");
    }else{
      say("CPU FOUNDATION STRESS TEST: FAIL");
      say("Unexpected EAX marker: "+hex(eax));
      throw Error("stress fixture stopped without a recognized marker");
    }
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
    args=ap.parse_args()
    manifest=json.loads((args.package/"manifest.xwasm.json").read_text(encoding="utf-8"))
    if manifest.get("architecture")!="x86":
        raise SystemExit("package architecture must be x86")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(HTML,encoding="utf-8")
    print(args.output)

if __name__=="__main__":
    main()
