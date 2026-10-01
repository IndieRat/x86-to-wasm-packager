const fs = require("fs");

async function main() {
  const runtimePath = process.argv[2], payloadPath = process.argv[3], kind = process.argv[4];
  if (!runtimePath || !payloadPath || !kind) throw new Error("usage: node xwasm_ci_runner.js runtime.wasm payload.exe x87|c5");
  const runtime = fs.readFileSync(runtimePath), payload = fs.readFileSync(payloadPath);
  const mod = await WebAssembly.compile(runtime), env = {};
  let memory = null;
  for (const imp of WebAssembly.Module.imports(mod)) {
    if (imp.module !== "env") continue;
    if (imp.kind === "memory") { memory = new WebAssembly.Memory({initial:1024, maximum:4096}); env[imp.name] = memory; }
    else if (imp.kind === "function") env[imp.name] = () => 0;
  }
  const {instance} = await WebAssembly.instantiate(mod, {env}), e = instance.exports;
  if (!memory) throw new Error("runtime did not import memory");
  new Uint8Array(memory.buffer).set(payload, 0x00100000);
  const check=(n,a,x)=>{if((a>>>0)!==(x>>>0))throw new Error("[FAIL] "+n+": got "+(a>>>0)+", expected "+(x>>>0));console.log("[PASS] "+n+": "+(a>>>0));};
  console.log("=== XWASM CI "+kind+" ===");
  check("runtime version",e.x86_get_runtime_version(),0x90000);
  check("init",e.xwasm_init(),0);
  check("PE load",e.x86_load_pe(0x100000,payload.length),0);
  check("loaded",e.x86_get_loaded(),1); check("load error",e.x86_get_load_error(),0);
  const result=e.x86_run(10000);
  const hex32=n=>(n>>>0).toString(16).padStart(8,"0");
  const hex8=n=>(n&255).toString(16).padStart(2,"0");
  const current=e.x86_get_eip()>>>0;
  console.log("[INFO] run="+result+" steps="+e.x86_get_steps()+" EIP=0x"+hex32(current)+" EAX=0x"+hex32(e.x86_get_eax()));
  if(result<0){
    console.log("=== CPU FAILURE DIAGNOSTICS ===");
    console.log("[FAULT] run result="+result+" cpu_error=0x"+hex32(e.x86_get_cpu_error())+" halted="+e.x86_get_halted());
    console.log("[FAULT] current EIP=0x"+hex32(current));
    console.log("[FAULT] next bytes="+Array.from({length:16},(_,i)=>hex8(e.x86_get_current_byte(i))).join(" "));
    console.log("[FAULT] last opcode=0x"+hex8(e.x86_get_last_decoded_opcode())+
      " map=0x"+hex32(e.x86_get_last_decoded_map())+
      " length="+e.x86_get_last_decoded_length()+
      " dispatch="+e.x86_get_last_dispatch_id()+
      " dispatch_count="+e.x86_get_last_dispatch_count());
    const slen=e.x86_get_last_semantic_id_len();
    let sid="";
    for(let i=0;i<slen;i++)sid+=String.fromCharCode(e.x86_get_last_semantic_id_char(i));
    console.log("[FAULT] last semantic="+(sid||"<none>"));
    console.log("[FAULT] regs EAX=0x"+hex32(e.x86_get_eax())+
      " ECX=0x"+hex32(e.x86_get_ecx())+
      " EDX=0x"+hex32(e.x86_get_edx())+
      " EBX=0x"+hex32(e.x86_get_ebx())+
      " ESP=0x"+hex32(e.x86_get_esp())+
      " EBP=0x"+hex32(e.x86_get_ebp())+
      " ESI=0x"+hex32(e.x86_get_esi())+
      " EDI=0x"+hex32(e.x86_get_edi()));
    console.log("[FAULT] EFLAGS=0x"+hex32(e.x86_get_eflags())+
      " x87_depth="+e.x86_get_x87_count()+
      " memory_faults="+e.x86_get_memory_faults());
    console.log("[FAULT] stack="+Array.from({length:8},(_,i)=>"0x"+hex32(e.x86_get_stack_dword(i))).join(" "));
    const tc=e.x86_get_trace_count();
    console.log("[FAULT] trace_count="+tc+" trace_failure_index="+e.x86_get_trace_failure_index());
    for(let j=0;j<tc;j++){
      const i=e.x86_get_trace_index(j);
      let ts="";
      const tl=e.x86_get_trace_semantic_id_len(i);
      for(let k=0;k<tl;k++)ts+=String.fromCharCode(e.x86_get_trace_semantic_id_char(i,k));
      console.log("[FAULT TRACE "+String(j).padStart(2,"0")+"] EIP=0x"+hex32(e.x86_get_trace_eip(i))+
        " -> 0x"+hex32(e.x86_get_trace_next_eip(i))+
        " OP=0x"+hex8(e.x86_get_trace_opcode(i))+
        " SEM="+(ts||"<none>")+
        " DISPATCH="+e.x86_get_trace_dispatch(i)+
        " EAX=0x"+hex32(e.x86_get_trace_eax(i))+
        " FLAGS=0x"+hex32(e.x86_get_trace_flags(i)));
    }
    console.log("=== END CPU FAILURE DIAGNOSTICS ===");
  }
  check("CPU halted",e.x86_get_halted(),1); check("CPU error",e.x86_get_cpu_error(),0);
  if(kind==="x87"){
    check("x87 compiled C result",e.x86_get_eax(),1);
    let seen=0; for(let j=0;j<e.x86_get_trace_count();j++){const i=e.x86_get_trace_index(j),op=e.x86_get_trace_opcode(i)&255;if(op>=0xD8&&op<=0xDF)seen++;}
    if(!seen)throw new Error("[FAIL] no x87 opcode reached trace");
    console.log("[PASS] x87 trace coverage: "+seen);
  } else if(kind==="c5"){
    check("compiled C return value",e.x86_get_eax(),2);
    const view=()=>new Uint8Array(memory.buffer), dv=()=>new DataView(memory.buffer);
    const write=(p,s)=>view().set(Buffer.from(s+"\0"),p);
    const path=e.x86_crt_malloc(0x40), keyPath=e.x86_crt_malloc(0x80), valueName=e.x86_crt_malloc(0x40);
    const queryData=e.x86_crt_malloc(0x20), queryType=e.x86_crt_malloc(0x20), querySize=e.x86_crt_malloc(0x20);
    write(path,"saves/c5.dat"); check("C5 filesystem state",e.x86_fs_exists(path),1);
    write(keyPath,"Software/C5/Runtime"); write(valueName,"Milestone");
    check("C5 registry open",e.x86_reg_open_key(0x80000001,keyPath,queryData),0);
    const key=dv().getUint32(queryData,true);
    check("C5 registry value state",e.x86_reg_value_exists(key,valueName),1);
    dv().setUint32(querySize,4,true);
    check("C5 registry query",e.x86_reg_query_value(key,valueName,queryType,queryData,querySize),0);
    check("C5 registry type",dv().getUint32(queryType,true),4);
    check("C5 registry value",dv().getUint32(queryData,true),0xC5);
    check("C5 close registry key",e.x86_reg_close_key(key),0);
    for(const p of [path,keyPath,valueName,queryData,queryType,querySize])e.x86_crt_free(p);
  } else throw new Error("unknown test kind: "+kind);
  console.log("[PASS] XWASM "+kind+" CI milestone complete");
}
main().catch(err=>{console.error(err.stack||err);process.exit(1);});
