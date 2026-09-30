(() => {
  const $=id=>document.getElementById(id), log=s=>{const p=document.createElement("div");p.textContent=s;$("log").appendChild(p);};
  const check=(n,a,e)=>{if(a!==e)throw new Error("[FAIL] "+n+": got "+a+", expected "+e);log("[PASS] "+n+": "+a);};
  const hex=n=>"0x"+(n>>>0).toString(16).padStart(8,"0");
  async function run(){
    $("log").textContent=""; const rf=$("runtime").files[0],pf=$("payload").files[0];
    if(!rf||!pf){log("Select runtime.wasm and the x87 PE32 fixture first.");return;}
    try{
      const module=await WebAssembly.compile(await rf.arrayBuffer()), env={}; let memory=null;
      for(const imp of WebAssembly.Module.imports(module)){if(imp.module!=="env")continue;if(imp.kind==="memory"){memory=new WebAssembly.Memory({initial:1024,maximum:4096});env[imp.name]=memory;}else if(imp.kind==="function")env[imp.name]=()=>0;}
      const inst=await WebAssembly.instantiate(module,{env}),e=inst.exports;if(!memory)throw new Error("runtime did not import memory");
      const view=()=>new Uint8Array(memory.buffer),payload=new Uint8Array(await pf.arrayBuffer());const addr=0x00100000;view().set(payload,addr);
      log("=== X87 COMPILED C INTEGRATION ===");
      check("runtime version",e.x86_get_runtime_version(),0x00090000);check("init",e.xwasm_init(),0);check("PE load",e.x86_load_pe(addr,payload.length),0);
      check("loaded",e.x86_get_loaded(),1);check("load error",e.x86_get_load_error(),0);
      const result=e.x86_run(10000),eip=e.x86_get_eip()>>>0;
      log("[INFO] CPU run="+result+" steps="+e.x86_get_steps()+" EIP="+hex(eip)+" EAX="+hex(e.x86_get_eax()));
      log("[DEBUG] semantic ID length="+e.x86_get_last_semantic_id_len());
      let semantic="";for(let i=0;i<e.x86_get_last_semantic_id_len();i++)semantic+=String.fromCharCode(e.x86_get_last_semantic_id_char(i));
      log("[DEBUG] semantic ID: "+(semantic||"<none>"));
      check("CPU halted",e.x86_get_halted(),1);check("CPU error",e.x86_get_cpu_error(),0);check("x87 compiled C result",e.x86_get_eax(),1);
      log("=== RESULT ===");log("[PASS] XWASM x87 compiled-C milestone complete");
    }catch(err){log(String(err));}
  }
  $("run").addEventListener("click",run);
})();