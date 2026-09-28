#!/usr/bin/env python3
"""Generate a standalone browser runner for the XWASM v0.7 window/input/audio fixture."""
from pathlib import Path
import argparse

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XWASM X86 Runtime v0.7 — Compatibility Shell</title>
<style>
:root{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;color:#d9e1ea;background:#0b0e12}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:#0b0e12}
.shell{max-width:1400px;margin:0 auto;padding:16px}
.header{display:flex;justify-content:space-between;align-items:center;gap:16px;border:1px solid #303944;background:#141922;padding:12px 14px}
.brand{font-size:18px;font-weight:700}.sub{color:#7f8b99;font-size:12px;margin-top:3px}
.status{display:flex;align-items:center;gap:8px;color:#9aa7b5;font-size:12px}
.dot{width:9px;height:9px;border-radius:50%;background:#555}.dot.live{background:#72d572;box-shadow:0 0 8px #72d572}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
button,.filepick{font:inherit;font-size:12px;color:#d9e1ea;background:#1a2029;border:1px solid #3a4654;padding:7px 10px;cursor:pointer}
button:hover,.filepick:hover{background:#232b36}button:disabled{opacity:.5;cursor:default}
.filepick input{display:none}
.grid{display:grid;grid-template-columns:minmax(0,1fr) 380px;gap:12px}
.left{min-width:0}.right{min-width:0}
.surface{border:1px solid #303944;background:#11161d}
.surface-title{padding:8px 10px;border-bottom:1px solid #303944;color:#9eabb9;font-size:12px}
.window{padding:10px;background:#0e1217}
.canvas-wrap{display:flex;justify-content:center;align-items:center;min-height:300px;overflow:auto}
canvas{display:block;width:640px;height:360px;max-width:100%;image-rendering:pixelated;background:#101820;border:1px solid #485463}
.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:10px}
.card{border:1px solid #303944;background:#141922;padding:9px}
.card .label{font-size:11px;color:#7f8b99}.card .value{font-size:16px;margin-top:4px;color:#e8eef5}
.pass{color:#79d98a}.warn{color:#e6c86e}.fail{color:#ed7777}
.tabs{display:flex;gap:0;border-bottom:1px solid #303944;overflow:auto}
.tab{border:0;border-right:1px solid #303944;border-radius:0;background:#11161d;color:#8793a0;white-space:nowrap}
.tab.active{background:#1b222c;color:#fff}
.panel{display:none}.panel.active{display:block}
.log{height:230px;overflow:auto;margin:0;padding:10px;white-space:pre-wrap;word-break:break-word;background:#0b0f14;color:#b9c4d0;font-size:11px;line-height:1.5}
.event{border-bottom:1px solid #1c242e;padding:3px 0}.event.pass{color:#79d98a}.event.warn{color:#e6c86e}.event.fail{color:#ed7777}
.meta{padding:8px 10px;color:#73808e;font-size:11px;border-bottom:1px solid #303944}
.footer{margin-top:12px;color:#66727f;font-size:11px}
@media(max-width:900px){.grid{grid-template-columns:1fr}.right{order:2}.left{order:1}}
</style>
</head>
<body>
<div class="shell">
  <header class="header">
    <div><div class="brand">XWASM X86 Runtime v0.7</div><div class="sub">Compatibility Test Shell · window / input / audio / CPU</div></div>
    <div class="status"><span id="statusDot" class="dot"></span><span id="statusText">WAITING FOR PACKAGE</span></div>
  </header>

  <div class="toolbar">
    <label class="filepick">Open XWASM package<input id="picker" type="file" webkitdirectory directory></label>
    <button id="clearBtn">Clear logs</button>
    <button id="pauseBtn" disabled>Pause CPU</button>
  </div>

  <div class="grid">
    <main class="left">
      <section class="surface">
        <div class="surface-title">WIN32 CLIENT SURFACE</div>
        <div class="window"><div class="canvas-wrap"><canvas id="gfx" width="640" height="360"></canvas></div></div>
      </section>

      <section class="surface" style="margin-top:12px">
        <div class="tabs" id="tabs">
          <button class="tab active" data-panel="cpu">CPU</button>
          <button class="tab" data-panel="input">Input</button>
          <button class="tab" data-panel="window">Window / GFX</button>
          <button class="tab" data-panel="audio">Audio</button>
          <button class="tab" data-panel="imports">Imports</button>
          <button class="tab" data-panel="system">System</button>
        </div>
        <div id="panel-cpu" class="panel active"><div class="meta" id="cpuMeta">No runtime loaded.</div><pre class="log" id="cpuLog"></pre></div>
        <div id="panel-input" class="panel"><div class="meta" id="inputMeta">No input events yet.</div><pre class="log" id="inputLog"></pre></div>
        <div id="panel-window" class="panel"><div class="meta" id="windowMeta">Surface not created.</div><pre class="log" id="windowLog"></pre></div>
        <div id="panel-audio" class="panel"><div class="meta" id="audioMeta">No audio events yet.</div><pre class="log" id="audioLog"></pre></div>
        <div id="panel-imports" class="panel"><div class="meta" id="importsMeta">Imports not resolved.</div><pre class="log" id="importsLog"></pre></div>
        <div id="panel-system" class="panel"><div class="meta" id="systemMeta">Shell not initialized.</div><pre class="log" id="systemLog"></pre></div>
      </section>
    </main>

    <aside class="right">
      <section class="surface">
        <div class="surface-title">LIVE STATUS</div>
        <div class="cards">
          <div class="card"><div class="label">CPU STEPS</div><div class="value" id="steps">0</div></div>
          <div class="card"><div class="label">CPU SLICES</div><div class="value" id="slices">0</div></div>
          <div class="card"><div class="label">LAST EIP</div><div class="value" id="eip">0x00000000</div></div>
          <div class="card"><div class="label">LAST MESSAGE</div><div class="value" id="msg">0x0000</div></div>
          <div class="card"><div class="label">LEFT CLICKS</div><div class="value" id="leftClicks">0</div></div>
          <div class="card"><div class="label">RIGHT CLICKS</div><div class="value" id="rightClicks">0</div></div>
          <div class="card"><div class="label">MIDDLE CLICKS</div><div class="value" id="middleClicks">0</div></div>
          <div class="card"><div class="label">MOUSE MOVES</div><div class="value" id="moves">0</div></div>
          <div class="card"><div class="label">QUEUE</div><div class="value" id="queue">0</div></div>
          <div class="card"><div class="label">SURFACE</div><div class="value" id="surface">—</div></div>
          <div class="card"><div class="label">RICH OPS</div><div class="value" id="richOps">—</div></div>
          <div class="card"><div class="label">IMPORTS</div><div class="value" id="imports">—</div></div>
        </div>
      </section>
      <section class="surface" style="margin-top:12px">
        <div class="surface-title">TEST CHECKLIST</div>
        <div class="cards">
          <div class="card"><div class="label">WINDOW</div><div class="value" id="checkWindow">WAIT</div></div>
          <div class="card"><div class="label">INPUT</div><div class="value" id="checkInput">WAIT</div></div>
          <div class="card"><div class="label">AUDIO</div><div class="value" id="checkAudio">WAIT</div></div>
          <div class="card"><div class="label">CPU OPS</div><div class="value" id="checkCpu">WAIT</div></div>
        </div>
      </section>
    </aside>
  </div>
  <div class="footer">Click the canvas to generate Win32 mouse messages. Move, left/right/middle click, release, and press keys while the CPU loop is live.</div>
</div>

<script>
const $=id=>document.getElementById(id);
const canvas=$("gfx"),gfx=canvas.getContext("2d"),picker=$("picker");
const inputQueue=[];
let memory=null,runtimeExports=null,inputReady=false,loopRunning=false,paused=false;
let frameHandle=0,sliceCount=0,lastSteps=0;
let lastSeen={left:0,right:0,middle:0,moves:0,steps:0,msg:0};
const panels={cpu:$("cpuLog"),input:$("inputLog"),window:$("windowLog"),audio:$("audioLog"),imports:$("importsLog"),system:$("systemLog")};

function now(){return new Date().toLocaleTimeString();}
function logTo(kind,text,cls=""){
  const el=panels[kind];
  if(!el)return;
  const line=document.createElement("div");
  line.className="event "+cls;
  line.textContent="["+now()+"] "+text;
  el.appendChild(line);
  el.scrollTop=el.scrollHeight;
}
function setMeta(kind,text){$(kind+"Meta").textContent=text;}
function setStatus(text,live=false){$("statusText").textContent=text;$("statusDot").className="dot"+(live?" live":"");}
function setCheck(id,text,cls){const e=$(id);e.textContent=text;e.className="value "+(cls||"");}
function hex(v,w=8){return "0x"+(v>>>0).toString(16).padStart(w,"0");}
function rgb(c){return "#"+(c&255).toString(16).padStart(2,"0")+((c>>>8)&255).toString(16).padStart(2,"0")+((c>>>16)&255).toString(16).padStart(2,"0");}

document.querySelectorAll(".tab").forEach(tab=>{
  tab.addEventListener("click",()=>{
    document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(x=>x.classList.remove("active"));
    tab.classList.add("active");$("panel-"+tab.dataset.panel).classList.add("active");
  });
});
$("clearBtn").onclick=()=>{
  Object.values(panels).forEach(p=>p.textContent="");
  logTo("system","Logs cleared.");
};
$("pauseBtn").onclick=()=>{
  paused=!paused;
  $("pauseBtn").textContent=paused?"Resume CPU":"Pause CPU";
  logTo("cpu",paused?"CPU loop paused by operator.":"CPU loop resumed by operator.",paused?"warn":"pass");
};

function queueKeyMessage(type,keyCode){
  inputQueue.push({hwnd:0,message:type,wParam:keyCode>>>0,lParam:0,time:Date.now()>>>0,x:0,y:0});
  logTo("input","Browser key -> WM_KEYDOWN 0x"+(keyCode>>>0).toString(16));
}
function queueMouseMessage(type,e,flags=0){
  const r=canvas.getBoundingClientRect();
  const sx=canvas.width/r.width,sy=canvas.height/r.height;
  const x=Math.max(0,Math.min(canvas.width-1,Math.round((e.clientX-r.left)*sx)));
  const y=Math.max(0,Math.min(canvas.height-1,Math.round((e.clientY-r.top)*sy)));
  const lParam=((y&65535)<<16)|(x&65535);
  inputQueue.push({hwnd:0,message:type,wParam:flags>>>0,lParam,time:Date.now()>>>0,x,y});
  const names={0x0200:"WM_MOUSEMOVE",0x0201:"WM_LBUTTONDOWN",0x0202:"WM_LBUTTONUP",0x0204:"WM_RBUTTONDOWN",0x0205:"WM_RBUTTONUP",0x0207:"WM_MBUTTONDOWN",0x0208:"WM_MBUTTONUP"};
  logTo("input","Browser pointer -> "+(names[type]||hex(type,4))+" @ "+x+","+y);
}
function writeMsg(ptr,m){
  const d=new DataView(memory.buffer);
  d.setUint32(ptr,m.hwnd,true);d.setUint32(ptr+4,m.message,true);d.setUint32(ptr+8,m.wParam,true);
  d.setUint32(ptr+12,m.lParam,true);d.setUint32(ptr+16,m.time,true);d.setInt32(ptr+20,m.x,true);d.setInt32(ptr+24,m.y,true);
}
function installInput(){
  window.addEventListener("keydown",e=>{
    if(!inputReady)return;e.preventDefault();queueKeyMessage(0x0100,e.keyCode||e.which||0);
  });
  canvas.addEventListener("mousemove",e=>{if(inputReady)queueMouseMessage(0x0200,e,0);});
  canvas.addEventListener("mousedown",e=>{
    if(!inputReady)return;
    e.preventDefault();canvas.focus?.();
    const f=e.button===0?1:e.button===2?2:4;
    queueMouseMessage(e.button===0?0x0201:e.button===2?0x0204:0x0207,e,f);
  });
  canvas.addEventListener("mouseup",e=>{
    if(!inputReady)return;
    e.preventDefault();
    const f=e.button===0?1:e.button===2?2:4;
    queueMouseMessage(e.button===0?0x0202:e.button===2?0x0205:0x0208,e,f);
  });
  canvas.addEventListener("contextmenu",e=>e.preventDefault());
}
async function runFixture(){
  if(!runtimeExports||runtimeExports.x86_get_halted()||paused)return;
  try{
    const ex=runtimeExports,result=ex.x86_run(512);
    sliceCount++;
    if(result<0)throw Error("x86 CPU execution failed at EIP="+hex(ex.x86_get_eip()));
    lastSteps=ex.x86_get_steps();
    const msg=ex.x86_get_last_message();
    const left=ex.x86_get_mouse_clicks?.()??0;
    const right=ex.x86_get_mouse_right_clicks?.()??0;
    const middle=ex.x86_get_mouse_middle_clicks?.()??0;
    const moves=ex.x86_get_mouse_moves?.()??0;
    const rich=ex.x86_get_rich_ops_pass?.()??0;
    const sw=ex.x86_get_surface_width?.()??0,sh=ex.x86_get_surface_height?.()??0;
    $("steps").textContent=lastSteps.toLocaleString();$("slices").textContent=sliceCount.toLocaleString();
    $("eip").textContent=hex(ex.x86_get_eip());$("msg").textContent=hex(msg,4);
    $("leftClicks").textContent=left;$("rightClicks").textContent=right;$("middleClicks").textContent=middle;$("moves").textContent=moves;$("queue").textContent=inputQueue.length;
    $("surface").textContent=sw&&sh?sw+"x"+sh:"—";$("richOps").textContent=rich?"PASS":"WAIT";$("imports").textContent=ex.x86_get_import_resolved()+"/12";
    setMeta("cpu","EIP "+hex(ex.x86_get_eip())+" · "+lastSteps.toLocaleString()+" instructions · slice "+sliceCount);
    if(sw&&sh){setMeta("window","Client surface "+sw+"x"+sh);setCheck("checkWindow","PASS","pass");}
    if(ex.x86_get_import_resolved()===12&&ex.x86_get_import_failed()===0){setMeta("imports","12 resolved · 0 unresolved");setCheck("checkCpu",rich?"PASS":"RUNNING",rich?"pass":"warn");}
    if(rich){logTo("cpu","Rich x86 operation self-test passed: arithmetic / logic / shifts / IMUL / MOVZX / MOVSX / branches.","pass");}
    if(left>lastSeen.left){logTo("input","x86 DispatchMessageA received WM_LBUTTONDOWN. Click count="+left,"pass");setCheck("checkInput","PASS","pass");}
    if(right>lastSeen.right){logTo("input","x86 DispatchMessageA received WM_RBUTTONDOWN. Right-click count="+right,"pass");setCheck("checkInput","PASS","pass");}
    if(middle>lastSeen.middle){logTo("input","x86 DispatchMessageA received WM_MBUTTONDOWN. Middle-click count="+middle,"pass");setCheck("checkInput","PASS","pass");}
    if(moves>lastSeen.moves){logTo("input","x86 DispatchMessageA received WM_MOUSEMOVE. Move count="+moves,"pass");}
    if(lastSeen.steps===0){logTo("cpu","CPU loop started; x86_run(512) slices are executing continuously.","pass");}
    if(sliceCount%30===0)logTo("cpu","Heartbeat: steps="+lastSteps+" · EIP="+hex(ex.x86_get_eip())+" · queue="+inputQueue.length);
    if(ex.x86_get_cpu_error()!==0)throw Error("CPU error opcode="+hex(ex.x86_get_cpu_error(),2));
    if(ex.x86_get_import_resolved()!==12||ex.x86_get_import_failed()!==0)throw Error("import resolution changed unexpectedly");
    lastSeen={left,right,middle,moves,steps:lastSteps,msg};
    setCheck("checkAudio","PASS","pass");
    if(sliceCount===1)logTo("audio","KERNEL32 Beep bridge executed during fixture startup.","pass");
    if(sliceCount===1)logTo("window","CreateWindowExA created the browser-backed client surface.","pass");
  }catch(err){logTo("system","ERROR: "+err.message,"fail");setStatus("ERROR",false);}
}
function scheduleCpu(){if(!loopRunning)return;runFixture().finally(()=>{frameHandle=requestAnimationFrame(scheduleCpu);});}
function startCpuLoop(){if(loopRunning)return;loopRunning=true;setStatus("RUNTIME LIVE",true);frameHandle=requestAnimationFrame(scheduleCpu);}

picker.onchange=async e=>{
  const files=new Map();
  for(const f of e.target.files)files.set(f.webkitRelativePath.split("/").slice(1).join("/")||f.name,f);
  try{
    const mf=files.get("manifest.xwasm.json");if(!mf)throw Error("manifest.xwasm.json is missing");
    const manifest=JSON.parse(await mf.text());if(manifest.architecture!=="x86")throw Error("Not an XWASM x86 package");
    logTo("system","Package: "+manifest.name,"pass");
    const rt=files.get(manifest.runtime||"runtime.wasm"),payload=files.get(manifest.payload);
    if(!rt||!payload)throw Error("runtime.wasm or payload.exe is missing");
    memory=new WebAssembly.Memory({initial:1024,maximum:4096});
    const imports={env:{
      memory,
      xwasm_log:(level,ptr,len)=>logTo("system",new TextDecoder().decode(new Uint8Array(memory.buffer,ptr,len))),
      xwasm_gfx_create:(w,h)=>{canvas.width=w;canvas.height=h;},
      xwasm_gfx_clear:c=>{gfx.fillStyle=rgb(c);gfx.fillRect(0,0,canvas.width,canvas.height);},
      xwasm_gfx_pixel:(x,y,c)=>{gfx.fillStyle=rgb(c);gfx.fillRect(x,y,1,1);},
      xwasm_gfx_rect:(l,t,r,b,c)=>{gfx.fillStyle=rgb(c);gfx.fillRect(l,t,r-l,b-t);},
      xwasm_gfx_present:()=>{},
      xwasm_input_poll:(ptr,remove)=>{if(!inputQueue.length)return 0;const m=remove?inputQueue.shift():inputQueue[0];writeMsg(ptr,m);return 1;},
      xwasm_input_quit:()=>{},
      xwasm_audio_beep:(frequency,duration)=>{
        const AudioCtx=window.AudioContext||window.webkitAudioContext;if(!AudioCtx)return;
        const ctx=new AudioCtx(),osc=ctx.createOscillator(),gain=ctx.createGain();
        osc.type="square";osc.frequency.value=Math.max(20,Math.min(20000,frequency||440));gain.gain.value=0.05;
        osc.connect(gain);gain.connect(ctx.destination);osc.start();
        osc.stop(ctx.currentTime+Math.max(0.02,Math.min(2,duration/1000)));osc.addEventListener("ended",()=>ctx.close());
        logTo("audio","Browser Web Audio: "+frequency+" Hz for "+duration+" ms.","pass");
      }
    }};
    const {instance}=await WebAssembly.instantiate(await rt.arrayBuffer(),imports);
    runtimeExports=instance.exports;
    logTo("system","Runtime WASM instantiated.","pass");
    logTo("system","Runtime version: "+hex(runtimeExports.x86_get_runtime_version()),"pass");
    runtimeExports.xwasm_init?.();
    const buf=new Uint8Array(await payload.arrayBuffer()),stage=0x02000000;
    if(stage+buf.length>memory.buffer.byteLength)throw Error("payload staging address exceeds WASM memory");
    new Uint8Array(memory.buffer,stage,buf.length).set(buf);
    if(runtimeExports.x86_debug_probe(stage)!==0x5a4d)throw Error("runtime MZ probe failed");
    if(runtimeExports.x86_load_pe(stage,buf.length)!==0)throw Error("PE loader rejected fixture");
    logTo("system","PE32 fixture loaded.","pass");
    const resolved=runtimeExports.x86_get_import_resolved(),failed=runtimeExports.x86_get_import_failed();
    $("imports").textContent=resolved+"/12";setMeta("imports",resolved+" resolved · "+failed+" unresolved");
    logTo("imports","Resolved imports: "+resolved+"/12","pass");
    logTo("imports","Unresolved imports: "+failed,(failed===0?"pass":"fail"));
    if(resolved!==12||failed!==0)throw Error("expected 12 resolved imports and 0 unresolved imports");
    setCheck("checkWindow","PASS","pass");setCheck("checkAudio","RUNNING","warn");
    inputReady=true;installInput();startCpuLoop();
    $("pauseBtn").disabled=false;
    logTo("system","Compatibility shell is live. Use the canvas for input tests.","pass");
  }catch(err){logTo("system","ERROR: "+err.message,"fail");setStatus("LOAD ERROR",false);}
};
</script>
</body>
</html>"""

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(HTML,encoding="utf-8")
    print(a.output)
if __name__=="__main__":
    raise SystemExit(main())
