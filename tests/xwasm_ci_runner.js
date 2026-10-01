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
  console.log("[INFO] run="+result+" steps="+e.x86_get_steps()+" EIP=0x"+(e.x86_get_eip()>>>0).toString(16)+" EAX=0x"+(e.x86_get_eax()>>>0).toString(16));
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
