#!/usr/bin/env python3
"""Generate a standalone browser runner for an XWASM architecture=x86 package."""
from __future__ import annotations
import argparse, json
from pathlib import Path

HTML = r'''<!doctype html>
<meta charset="utf-8">
<title>XWASM X86 Runtime v0.7</title>
<pre id="log">XWASM X86 Runtime v0.7
Select the package directory.</pre>
<input id="files" type="file" webkitdirectory multiple>
<script>
const out=document.querySelector("#log");
const say=s=>{out.textContent+="\n"+s;};
const files=new Map();
const hex=(u8,n=32)=>Array.from(u8.slice(0,n),b=>b.toString(16).padStart(2,"0")).join(" ");
const td=new TextDecoder();
let gdrProvenance=null;
const readGuestAscii=(ptr,max=512)=>{
  ptr=ptr>>>0;
  const u8=new Uint8Array(mem.buffer);
  if(ptr>=u8.length)return "<OOB>";
  let end=ptr;
  const limit=Math.min(u8.length,ptr+max);
  while(end<limit&&u8[end]!==0)end++;
  return new TextDecoder().decode(u8.slice(ptr,end));
};
async function unpackXWSC(file,expectedKind,label){
  const b=new Uint8Array(file),v=new DataView(file);
  if(b.length<62||td.decode(b.slice(0,6))!=="XWSC01") throw Error(label+" is not an XWSC01 container");
  if(v.getUint16(6,true)!==1||v.getUint8(8)!==expectedKind) throw Error(label+" has the wrong XWASM container kind/version");
  const comp=v.getUint8(9),rawSize=Number(v.getBigUint64(14,true)),dataSize=Number(v.getBigUint64(22,true));
  if(62+dataSize!==b.length) throw Error(label+" has an invalid container size");
  const stored=b.slice(62,62+dataSize);
  let raw;
  if(comp===0) raw=stored;
  else if(comp===1){
    if(typeof DecompressionStream==="undefined") throw Error("browser lacks DecompressionStream for "+label);
    raw=new Uint8Array(await new Response(new Blob([stored]).stream().pipeThrough(new DecompressionStream("deflate"))).arrayBuffer());
  } else throw Error(label+" uses unsupported XWASM compression "+comp);
  if(raw.length!==rawSize) throw Error(label+" raw size mismatch");
  const hash=new Uint8Array(await crypto.subtle.digest("SHA-256",raw));
  for(let i=0;i<32;i++) if(hash[i]!==b[30+i]) throw Error(label+" SHA-256 mismatch");
  return raw;
}

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
    const isWindowAudio = manifest.name==="XWASM-X86-Window-Input-Audio-Test" || manifest.execution_status==="v0.7_window_input_audio_fixture";
    say("Bundled DLLs: "+((manifest.bundled_dlls||[]).length));
    say("Test profile: "+(isWindowAudio?"v0.7 window/input/audio":"generic x86"));

    const rt=files.get(manifest.runtime||"runtime.xwasm");
    if(!rt) throw Error("runtime.xwasm is missing");

    const mem=new WebAssembly.Memory({initial:1024,maximum:4096});
    const bytes=await unpackXWSC(await rt.arrayBuffer(),1,"runtime.xwasm");
    const pkg={
      get:p=>files.get(p)||files.get("resources/"+p),
      readString:(ptr,len)=>new TextDecoder().decode(new Uint8Array(mem.buffer,ptr,len))
    };

    const canvas=document.createElement("canvas");
    canvas.width=640; canvas.height=360; canvas.style.imageRendering="pixelated"; canvas.style.border="1px solid #555";
    document.body.insertBefore(canvas,document.getElementById("log"));
    const gfx=canvas.getContext("2d");
    const rgb=c=>"#"+(c&0xff).toString(16).padStart(2,"0")+((c>>>8)&0xff).toString(16).padStart(2,"0")+((c>>>16)&0xff).toString(16).padStart(2,"0");
    const imports={env:{
      memory:mem,
      xwasm_log:(level,ptr,len)=>{
        say(new TextDecoder().decode(new Uint8Array(mem.buffer,ptr,len)));
      },
      xwasm_gfx_create:(w,h)=>{canvas.width=w;canvas.height=h;},
      xwasm_gfx_clear:(c)=>{gfx.fillStyle=rgb(c);gfx.fillRect(0,0,canvas.width,canvas.height);},
      xwasm_gfx_pixel:(x,y,c)=>{gfx.fillStyle=rgb(c);gfx.fillRect(x,y,1,1);},
      xwasm_gfx_rect:(l,t,r,b,c)=>{gfx.fillStyle=rgb(c);gfx.fillRect(l,t,r-l,b-t);},
      xwasm_gfx_present:()=>{},
      xwasm_input_poll:(ptr,remove)=>0,
      xwasm_input_quit:()=>{},
      xwasm_audio_beep:(frequency,duration)=>{},
      
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

    const XAPI_TYPE={void:0,u32:1,i32:2,ptr:3,f32:4,f64:5};
    const XAPI_ABI={stdcall:0,cdecl:1};
    const registerXapiPool=async poolFile=>{
      if(!poolFile){say("XAPI pool: none (legacy package)");return 0;}
      if(!ex.x86_xapi_reset||!ex.x86_xapi_scratch||!ex.x86_xapi_register||!ex.x86_xapi_register_alias)
        throw Error("runtime is missing the XAPI registry exports");
      const raw=await unpackXWSC(await poolFile.arrayBuffer(),4,"xapi_pool.xapi");
      const manifest=JSON.parse(td.decode(raw));
      if(manifest.format!=="xwasm-xapi"||manifest.version!==1)
        throw Error("invalid xapi_pool.xapi manifest");
      const mem8=new Uint8Array(mem.buffer);
      const scratch=ex.x86_xapi_scratch()>>>0;
      const putAscii=s=>{
        const bytes=new TextEncoder().encode(s);
        return bytes;
      };
      const clearScratch=()=>{mem8.fill(0,scratch,scratch+512);};
      ex.x86_xapi_reset();
      let registered=0,aliases=0;
      for(const [lib,body] of Object.entries(manifest.libraries||{})){
        for(const [name,fn] of Object.entries(body.functions||{})){
          const args=(fn.args||[]).map(t=>XAPI_TYPE[t]);
          const ret=XAPI_TYPE[fn.return||"void"];
          if(ret===undefined||args.some(v=>v===undefined)||args.length>16)
            throw Error("unsupported XAPI type in "+lib+"!"+name);
          const abi=XAPI_ABI[fn.abi||"stdcall"];
          if(abi===undefined) throw Error("unsupported XAPI ABI in "+lib+"!"+name);
          clearScratch();
          let off=0;
          for(const s of [lib,name]){
            const b=putAscii(s);
            if(off+b.length+1+args.length>511) throw Error("XAPI scratch overflow in "+lib+"!"+name);
            mem8.set(b,scratch+off);off+=b.length+1;
          }
          for(let i=0;i<args.length;i++)mem8[scratch+off++]=args[i];
          const idx=ex.x86_xapi_register(fn.id>>>0,abi,args.length,ret);
          if(idx===0xFFFFFFFF) throw Error("runtime rejected XAPI "+lib+"!"+name);
          registered++;
        }
      }
      for(const [from,to] of Object.entries(manifest.dll_aliases||{})){
        clearScratch();
        const a=putAscii(from),b=putAscii(to);
        if(a.length+b.length+2>512) throw Error("XAPI alias scratch overflow");
        mem8.set(a,scratch);mem8.set(b,scratch+a.length+1);
        if(ex.x86_xapi_register_alias()===0xFFFFFFFF) throw Error("runtime rejected XAPI alias "+from);
        aliases++;
      }
      say("XAPI pool loaded: "+registered+" functions, "+aliases+" aliases");
      return registered;
    };

    const xapiPoolFile=manifest.xapi_pool?files.get(manifest.xapi_pool):null;
    await registerXapiPool(xapiPoolFile);

    const emitGdrProvenance=()=>{
      if(!ex.x86_get_gdr_count){
        say("=== GDR PROVENANCE ===");
        say("Runtime does not expose GDR provenance exports.");
        return;
      }

      const base=(ex.x86_get_image_base?ex.x86_get_image_base():0)>>>0;
      const count=ex.x86_get_gdr_count()>>>0;
      const imports=[];
      const unique=new Map();

      for(let i=0;i<count;i++){
        const dllRva=ex.x86_get_gdr_dll_rva(i)>>>0;
        const funcRva=ex.x86_get_gdr_func_rva(i)>>>0;
        const iatRva=ex.x86_get_gdr_iat_rva(i)>>>0;
        const target=ex.x86_get_gdr_target(i)>>>0;
        const status=ex.x86_get_gdr_status(i)>>>0;
        const calls=ex.x86_get_gdr_call_count(i)>>>0;
        const dll=readGuestAscii(base+dllRva);
        const name=funcRva?readGuestAscii(base+funcRva):"<ordinal>";
        const key=dll.toLowerCase()+"!"+name;
        const row={index:i,dll,name,dll_rva:dllRva,func_rva:funcRva,iat_rva:iatRva,
          iat_address:(base+iatRva)>>>0,target,status,resolved:status===1,call_count:calls};
        imports.push(row);

        let u=unique.get(key);
        if(!u){
          u={dll,name,slots:0,resolved:false,targets:new Set(),calls:0};
          unique.set(key,u);
        }
        u.slots++;
        u.resolved ||= row.resolved;
        if(row.target)u.targets.add("0x"+row.target.toString(16).padStart(8,"0"));
        u.calls+=calls;
      }

      const required=[...unique.values()].map(u=>({
        dll:u.dll,name:u.name,slots:u.slots,resolved:u.resolved,
        targets:[...u.targets].sort(),calls:u.calls
      })).sort((a,b)=>{
        if(a.resolved!==b.resolved)return a.resolved?1:-1;
        return (a.dll+"!"+a.name).localeCompare(b.dll+"!"+b.name);
      });

      const resolved=imports.filter(x=>x.resolved).length;
      const missing=imports.length-resolved;
      const executed=imports.filter(x=>x.call_count>0);
      const lastSlot=ex.x86_get_last_indirect_slot?ex.x86_get_last_indirect_slot()>>>0:0;
      const lastTarget=ex.x86_get_last_indirect_target?ex.x86_get_last_indirect_target()>>>0:0;
      const lastImport=imports.find(x=>x.iat_address===lastSlot);

      say("=== GDR PROVENANCE ===");
      say("Static import slots: "+imports.length);
      say("Runtime-resolved slots: "+resolved);
      say("Runtime-missing slots: "+missing);
      say("Unique DLL!export requirements: "+required.length);
      say("Actually executed imported slots: "+executed.length);
      say("Last indirect slot: 0x"+lastSlot.toString(16).padStart(8,"0")+
          " -> 0x"+lastTarget.toString(16).padStart(8,"0"));
      say("Last indirect provenance: "+(
        lastImport
          ? lastImport.dll+"!"+lastImport.name+
            " | resolved="+lastImport.resolved+
            " | calls="+lastImport.call_count
          : "NOT AN IMPORT IAT SLOT"
      ));

      say("GDR REQUIRED EXPORTS:");
      for(const u of required){
        const state=u.resolved?"RESOLVED":"MISSING";
        const target=u.targets.length?u.targets.join(","):"-";
        say("  ["+state+"] "+u.dll+"!"+u.name+
            " | slots="+u.slots+
            " | calls="+u.calls+
            " | target="+target);
      }

      gdrProvenance={
        format:"xwasm-gdr-provenance",
        version:1,
        image_base:base,
        static_import_slots:imports.length,
        runtime_resolved_slots:resolved,
        runtime_missing_slots:missing,
        actually_executed_import_slots:executed.length,
        last_indirect_slot:lastSlot,
        last_indirect_target:lastTarget,
        last_indirect_provenance:lastImport||null,
        required_exports:required,
        imports
      };
    };

    if(!ex.x86_get_runtime_version)
      throw Error("x86_get_runtime_version export missing");

    say("Runtime version: 0x"+ex.x86_get_runtime_version().toString(16));

    if(ex.xwasm_init)
      ex.xwasm_init();

    const payload=files.get(manifest.payload);
    if(!payload) throw Error("payload missing: "+manifest.payload);

    const buf=manifest.payload_format==="XPL" ? await unpackXWSC(await payload.arrayBuffer(),2,"payload.xpl") : new Uint8Array(await payload.arrayBuffer());
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
        14:"section raw data extends outside the payload",
        15:"entry point RVA is outside the mapped image"
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
    if(ex.x86_get_requested_image_base) say("Requested image base: 0x"+ex.x86_get_requested_image_base().toString(16));
    if(ex.x86_get_image_base) say("Mapped image base: 0x"+ex.x86_get_image_base().toString(16));
    if(ex.x86_get_image_size) say("Mapped image size: 0x"+ex.x86_get_image_size().toString(16));
    if(ex.x86_get_relocation_rva) say("Relocation directory: RVA=0x"+ex.x86_get_relocation_rva().toString(16)+" size=0x"+(ex.x86_get_relocation_size?ex.x86_get_relocation_size():0).toString(16));
    if(ex.x86_get_relocation_needed) say("Relocation required: "+ex.x86_get_relocation_needed());
    if(ex.x86_get_import_rva) say("Import directory: RVA=0x"+ex.x86_get_import_rva().toString(16)+" size=0x"+(ex.x86_get_import_size?ex.x86_get_import_size():0).toString(16));
    if(ex.x86_get_dll_count) say("PE import DLLs: "+ex.x86_get_dll_count());
    if(ex.x86_get_import_count) say("PE imported symbols: "+ex.x86_get_import_count());
    if(ex.x86_get_import_resolved) say("Resolved imports: "+ex.x86_get_import_resolved());
    if(ex.x86_get_import_failed) say("Unresolved imports: "+ex.x86_get_import_failed());
    if(ex.x86_get_last_import_target) say("Last resolved API during import scan: 0x"+ex.x86_get_last_import_target().toString(16));
    if(ex.x86_alloc){
      const probeAlloc=ex.x86_alloc(64);
      say("Guest allocation probe: 64 bytes at 0x"+probeAlloc.toString(16));
      if(probeAlloc<0x00800000||probeAlloc>=0x01F00000)
        throw Error("guest memory allocator returned an address outside its v0.5 arena");
    }
    if(ex.x86_get_last_virtual_alloc){
      say("Virtual allocation state: base=0x"+ex.x86_get_last_virtual_alloc().toString(16)+
          " size=0x"+(ex.x86_get_last_virtual_alloc_size?ex.x86_get_last_virtual_alloc_size():0).toString(16));
    }
    const importCount=ex.x86_get_import_count?ex.x86_get_import_count():0;
    const resolvedCount=ex.x86_get_import_resolved?ex.x86_get_import_resolved():0;
    const failedCount=ex.x86_get_import_failed?ex.x86_get_import_failed():0;
    if(failedCount!==0) throw Error("x86 test expected zero unresolved imports");
    if(resolvedCount!==importCount) throw Error("x86 test expected every imported symbol to resolve ("+resolvedCount+"/"+importCount+")");
    say("Import resolution: "+resolvedCount+"/"+importCount+" imported symbols resolved.");
    if(isWindowAudio && resolvedCount!==12) throw Error("v0.7 window/input/audio test expected exactly twelve resolved builtin imports");
    say("Entry EIP: 0x"+ex.x86_get_eip().toString(16));
    const entryBytes=new Uint8Array(mem.buffer,ex.x86_get_eip(),8);
    say("Entry bytes: "+hex(entryBytes,8));

    if(!ex.x86_run||!ex.x86_get_eax||!ex.x86_get_eflags||!ex.x86_get_halted)
      throw Error("x86 v0.3 CPU execution exports are missing");

    say("CPU: 32-bit fetch/decode/execute core + ModRM addressing + imported CALL");
    say("Executing v0.7 window/input/audio PE entrypoint (budget: 64 instructions)...");
    const runResult=ex.x86_run(64);
    say("CPU run result: "+runResult);
    say("Instructions executed: "+ex.x86_get_steps());

    const eip=ex.x86_get_eip()>>>0;
    say("EIP after execution: 0x"+eip.toString(16).padStart(8,"0"));
    say("EAX: 0x"+(ex.x86_get_eax()>>>0).toString(16).padStart(8,"0"));
    say("EFLAGS: 0x"+(ex.x86_get_eflags()>>>0).toString(16).padStart(8,"0"));
    say("CPU halted: "+ex.x86_get_halted());

    /* Emit GDR after execution so call_count and last-indirect provenance
     * describe the actual failing/successful run rather than a pre-run zero state. */
    emitGdrProvenance();

    if(runResult<0){
      const opcode=ex.x86_get_current_opcode?(ex.x86_get_current_opcode()>>>0):0xFFFFFFFF;
      const imm32=ex.x86_get_current_imm32?(ex.x86_get_current_imm32()>>>0):0xFFFFFFFF;
      const cpuError=ex.x86_get_cpu_error?(ex.x86_get_cpu_error()>>>0):0;
      console.error(
        "CPU FAILURE: "+
        "EIP=0x"+eip.toString(16).padStart(8,"0")+
        " opcode=0x"+opcode.toString(16).padStart(2,"0")+
        " imm32=0x"+imm32.toString(16).padStart(8,"0")+
        " cpu_error=0x"+cpuError.toString(16).padStart(8,"0")
      );
      say(
        "CPU FAILURE: "+
        "EIP=0x"+eip.toString(16).padStart(8,"0")+
        " opcode=0x"+opcode.toString(16).padStart(2,"0")+
        " imm32=0x"+imm32.toString(16).padStart(8,"0")+
        " cpu_error=0x"+cpuError.toString(16).padStart(8,"0")
      );
      throw Error("x86 CPU execution failed");
    }
    if(!ex.x86_get_halted())
      throw Error("x86 CPU did not reach HLT within the instruction budget");
    if(ex.x86_get_steps() < 38)
      throw Error("v0.7 window/input/audio test did not execute the complete PE entrypoint");

    say("CPU/import/window/input/audio test: PE32 -> USER32/GDI32/KERNEL32 browser bridges -> HLT = PASS");
    say("DLL inventory:");

    for(const d of (manifest.bundled_dlls||[]))
      say("  "+d);

    say("READY — v0.7 Win32 window/input/audio foundation reached.");
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
