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
let mem=null, runtimeEx=null, xapiSlotsView=null, xapiById=new Map(), xapiWarnings=new Set();
let inputEvents=[],inputQuit=false;
const queueInput=e=>inputEvents.push(e);
const mouseLParam=(x,y)=>((x&0xffff)|((y&0xffff)<<16))>>>0;
const inputPoll=(ptr,remove)=>{
  if(!mem||!inputEvents.length)return 0;
  const e=remove?inputEvents.shift():inputEvents[0],dv=new DataView(mem.buffer);
  dv.setUint32(ptr>>>0,0,true);dv.setUint32((ptr+4)>>>0,e.msg>>>0,true);
  dv.setUint32((ptr+8)>>>0,e.wparam>>>0,true);dv.setUint32((ptr+12)>>>0,e.lparam>>>0,true);
  dv.setUint32((ptr+16)>>>0,performance.now()>>>0,true);
  dv.setInt32((ptr+20)>>>0,e.x|0,true);dv.setInt32((ptr+24)>>>0,e.y|0,true);return 1;
};
const xapiBridge=(id,argc)=>{
  const fn=xapiById.get(id>>>0);if(!fn||!xapiSlotsView)return 0;
  const a=Array.from(xapiSlotsView.subarray(0,Math.min(argc>>>0,fn.args.length)));let v=0;
  switch(fn.bridge){
    case "xw.math.sin":v=Math.sin(a[0]);break;case "xw.math.cos":v=Math.cos(a[0]);break;
    case "xw.math.tan":v=Math.tan(a[0]);break;case "xw.math.sqrt":v=Math.sqrt(a[0]);break;
    case "xw.math.pow":v=Math.pow(a[0],a[1]);break;case "xw.math.asin":v=Math.asin(a[0]);break;
    case "xw.math.acos":v=Math.acos(a[0]);break;case "xw.math.atan":v=Math.atan(a[0]);break;
    case "xw.math.atan2":v=Math.atan2(a[0],a[1]);break;case "xw.math.exp":v=Math.exp(a[0]);break;
    case "xw.math.log":v=Math.log(a[0]);break;case "xw.math.log10":v=Math.log10(a[0]);break;
    case "xw.math.ceil":v=Math.ceil(a[0]);break;case "xw.math.floor":v=Math.floor(a[0]);break;
    case "xw.math.fabs":v=Math.abs(a[0]);break;case "xw.math.fmod":v=a[0]%a[1];break;
    case "xw.math.ldexp":v=a[0]*Math.pow(2,a[1]);break;
    case "xw.math.roundf":v=Math.fround(Math.round(a[0]));break;
    case "xw.math.copysignf":v=Math.fround(Math.abs(a[0])*(a[1]<0?-1:1));break;
    case "xw.kernel32.Beep":beep(a[0]||440,a[1]||40);v=1;break;
    default:
      if(!xapiWarnings.has(fn.bridge)){xapiWarnings.add(fn.bridge);say("[XAPI] bridge not implemented: "+fn.bridge+" ("+fn.lib+"!"+fn.name+")");}
  }
  if(fn.ret==="f32")xapiSlotsView[15]=Math.fround(v);else if(fn.ret==="f64")xapiSlotsView[15]=v;
  return fn.ret==="void"?0:(v|0);
};
window.addEventListener("keydown",e=>{queueInput({msg:0x100,wparam:e.keyCode>>>0,lparam:0,x:0,y:0});if(["ArrowUp","ArrowDown","ArrowLeft","ArrowRight","Space"].includes(e.code))e.preventDefault();});
window.addEventListener("keyup",e=>queueInput({msg:0x101,wparam:e.keyCode>>>0,lparam:0,x:0,y:0}));
window.addEventListener("mousemove",e=>{const c=e.target.closest?.("canvas");if(!c)return;const r=c.getBoundingClientRect(),x=Math.round((e.clientX-r.left)*c.width/r.width),y=Math.round((e.clientY-r.top)*c.height/r.height);queueInput({msg:0x200,wparam:0,lparam:mouseLParam(x,y),x,y});});
window.addEventListener("mousedown",e=>{const c=e.target.closest?.("canvas");if(!c)return;const msg=e.button===0?0x201:e.button===2?0x204:0x207,x=e.offsetX|0,y=e.offsetY|0;queueInput({msg,wparam:0,lparam:mouseLParam(x,y),x,y});if(e.button===2)e.preventDefault();});
window.addEventListener("mouseup",e=>{const c=e.target.closest?.("canvas");if(!c)return;const msg=e.button===0?0x202:e.button===2?0x205:0x208,x=e.offsetX|0,y=e.offsetY|0;queueInput({msg,wparam:0,lparam:mouseLParam(x,y),x,y});});
window.addEventListener("wheel",e=>{const c=e.target.closest?.("canvas");if(!c)return;const r=c.getBoundingClientRect(),x=Math.round((e.clientX-r.left)*c.width/r.width),y=Math.round((e.clientY-r.top)*c.height/r.height),d=Math.max(-120,Math.min(120,-Math.round(e.deltaY)));queueInput({msg:0x20A,wparam:((d&0xffff)<<16)>>>0,lparam:mouseLParam(x,y),x,y});});

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

    mem=new WebAssembly.Memory({initial:1024,maximum:4096});
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
      xwasm_input_poll:(ptr,remove)=>inputPoll(ptr,remove),
      xwasm_input_quit:()=>{inputQuit=true;},
      xwasm_audio_beep:(frequency,duration)=>beep(frequency,duration),
      xwasm_xapi_call:(id,argc)=>xapiBridge(id,argc),
      
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
    const ex=instance.exports;runtimeEx=ex;
    if(!ex.x86_xapi_slots)throw Error("runtime is missing x86_xapi_slots export");
    xapiSlotsView=new Float64Array(mem.buffer,ex.x86_xapi_slots()>>>0,16);
    say("Runtime WASM instantiated.");

    const XAPI_TYPE={void:0,u32:1,i32:2,ptr:3,f32:4,f64:5};
    const XAPI_ABI={stdcall:0,cdecl:1};
    const registerXapiPool=async poolFile=>{
      if(!poolFile){say("XAPI pool: none (legacy package)");return 0;}
      if(!ex.x86_xapi_reset||!ex.x86_xapi_scratch||!ex.x86_xapi_register||!ex.x86_xapi_register_alias)throw Error("runtime is missing the XAPI registry exports");
      const raw=await unpackXWSC(await poolFile.arrayBuffer(),4,"xapi_pool.xapi"),manifest=JSON.parse(td.decode(raw));
      if(manifest.format!=="xwasm-xapi"||manifest.version!==1)throw Error("invalid xapi_pool.xapi manifest");
      const mem8=new Uint8Array(mem.buffer),scratch=ex.x86_xapi_scratch()>>>0,putAscii=s=>new TextEncoder().encode(s);
      const clearScratch=()=>mem8.fill(0,scratch,scratch+512);ex.x86_xapi_reset();xapiById=new Map();
      let registered=0,aliases=0,duplicates=0;
      for(const [lib,body] of Object.entries(manifest.libraries||{}))for(const [name,fn] of Object.entries(body.functions||{})){
        const id=fn.id>>>0,prior=xapiById.get(id);
        if(prior){if(prior.lib.toLowerCase()===lib.toLowerCase()&&prior.name===name){duplicates++;continue;}throw Error("XAPI duplicate id "+id+": "+prior.lib+"!"+prior.name+" vs "+lib+"!"+name);}
        const args=(fn.args||[]).map(t=>XAPI_TYPE[t]),ret=XAPI_TYPE[fn.return||"void"],abi=XAPI_ABI[fn.abi||"stdcall"];
        if(ret===undefined||args.some(v=>v===undefined)||args.length>16)throw Error("unsupported XAPI type in "+lib+"!"+name);
        if(abi===undefined)throw Error("unsupported XAPI ABI in "+lib+"!"+name);
        clearScratch();let off=0;
        for(const ss of [lib,name]){
          const b=putAscii(ss);
          if(off+b.length+1+args.length>511)throw Error("XAPI scratch overflow in "+lib+"!"+name);
          mem8.set(b,scratch+off);off+=b.length+1;
        }
        for(let i=0;i<args.length;i++)mem8[scratch+off++]=args[i];
        if(ex.x86_xapi_register(id,abi,args.length,ret)===0xFFFFFFFF)throw Error("runtime rejected XAPI "+lib+"!"+name);
        xapiById.set(id,{id,lib,name,args:fn.args||[],ret:fn.return||"void",bridge:fn.bridge});registered++;
      }
      for(const [from,to] of Object.entries(manifest.dll_aliases||{})){
        clearScratch();const a=putAscii(from),b=putAscii(to);
        if(a.length+b.length+2>512)throw Error("XAPI alias scratch overflow");
        mem8.set(a,scratch);mem8.set(b,scratch+a.length+1);
        if(ex.x86_xapi_register_alias()===0xFFFFFFFF)throw Error("runtime rejected XAPI alias "+from);aliases++;
      }
      const rd=ex.x86_get_xapi_duplicate_count?ex.x86_get_xapi_duplicate_count():0;
      say("XAPI pool loaded: "+registered+" functions, "+aliases+" aliases; duplicate entries skipped="+duplicates+" runtime_dedup="+rd);return registered;
    };
    
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
    if(isWindowAudio){
      if(failedCount!==0)throw Error("x86 test expected zero unresolved imports");
      if(resolvedCount!==importCount)throw Error("x86 test expected every imported symbol to resolve ("+resolvedCount+"/"+importCount+")");
    }else if(failedCount!==0){
      say("Import resolution warning: "+resolvedCount+"/"+importCount+" resolved; "+failedCount+" unresolved imports remain.");
    }else{
      say("Import resolution: "+resolvedCount+"/"+importCount+" imported symbols resolved.");
    }
    if(isWindowAudio && resolvedCount!==12) throw Error("v0.7 window/input/audio test expected exactly twelve resolved builtin imports");
    say("Entry EIP: 0x"+ex.x86_get_eip().toString(16));
    const entryBytes=new Uint8Array(mem.buffer,ex.x86_get_eip(),8);
    say("Entry bytes: "+hex(entryBytes,8));

    if(!ex.x86_run||!ex.x86_get_eax||!ex.x86_get_eflags||!ex.x86_get_halted)
      throw Error("x86 v0.3 CPU execution exports are missing");

    say("CPU: 32-bit fetch/decode/execute core + persistent browser frame loop");
    say("Starting guest execution in 20,000-instruction browser slices.");
    let frame=0,lastRun=0,running=true;
    const finishCpu=()=>{
      emitGdrProvenance();const eip=ex.x86_get_eip()>>>0,err=ex.x86_get_cpu_error?ex.x86_get_cpu_error()>>>0:0;
      say("CPU frame="+frame+" result="+lastRun+" EIP=0x"+eip.toString(16).padStart(8,"0")+" steps="+ex.x86_get_steps()+" halted="+ex.x86_get_halted()+" cpu_error=0x"+err.toString(16).padStart(8,"0"));
    };
    const runFrame=()=>{
      if(!running)return;
      try{
        if(inputQuit||ex.x86_get_halted()){running=false;finishCpu();return;}
        lastRun=ex.x86_run(20000);frame++;
        if(frame===1||frame%60===0)finishCpu();
        if(lastRun<0){running=false;finishCpu();say("CPU FAILURE: x86_run rc="+lastRun);return;}
        if(ex.x86_get_halted()){running=false;finishCpu();say("Guest halted/returned; graphics/input bridge stayed active.");return;}
        requestAnimationFrame(runFrame);
      }catch(err){running=false;finishCpu();say("CPU FAILURE: "+err.message);}
    };
    requestAnimationFrame(runFrame);
    
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
