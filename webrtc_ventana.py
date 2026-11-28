"""Arranque oculto del navegador WebRTC: sin bienvenida ni ventana visible en Windows."""
import json
import os
import time
from typing import List, Optional

SW_HIDE = 0
_STARTF_USESHOWWINDOW = 0x0001
_EX_TOOLWINDOW = 0x00000080
_EX_APPWINDOW = 0x00040000

HTML_PUENTE = """<!doctype html><html><head><meta charset="utf-8"></head>
<body style="background:#0b0f17;color:#94a3b8"><div id="st">Iniciando...</div>
<script>
const st=document.getElementById("st"),wsPort=location.hash.slice(1);
let ws,ctx,nextT=0,sources=[],despierto=true,dormida=false,ultimoHabla=performance.now(),colaPreCtx=[],piso=0.012,framesWake=0,framesVoz=0,pausasVoz=0,preroll=[],colaVoz=0,reconectando=null;
function sendCtrl(o){if(ws&&ws.readyState===1)ws.send(JSON.stringify(o));}
function limpiarAudio(){sources.forEach(s=>{try{s.stop()}catch{}});sources=[];if(ctx)nextT=ctx.currentTime;}
function activarEscucha(){dormida=false;despierto=true;framesWake=0;framesVoz=0;pausasVoz=0;ultimoHabla=performance.now();sendCtrl({type:"estado",v:"escuchando"});if(ws&&ws.readyState===1){preroll.forEach(b=>ws.send(b));preroll=[];}}
function despertar(){if(!dormida){ultimoHabla=performance.now();return;}dormida=false;despierto=true;framesWake=0;framesVoz=3;pausasVoz=0;colaVoz=22;ultimoHabla=performance.now();sendCtrl({type:"wake"});sendCtrl({type:"estado",v:"escuchando"});if(ws&&ws.readyState===1){preroll.forEach(b=>ws.send(b));preroll=[];}}
function playPcm24k(buf){
  if(!ctx){colaPreCtx.push(buf);return;}
  const i16=new Int16Array(buf),f32=new Float32Array(i16.length);
  for(let i=0;i<i16.length;i++)f32[i]=i16[i]/32768;
  const ab=ctx.createBuffer(1,f32.length,24000);ab.getChannelData(0).set(f32);
  const src=ctx.createBufferSource();src.buffer=ab;src.connect(ctx.destination);
  const t=Math.max(ctx.currentTime,nextT);src.start(t);nextT=t+ab.duration;
  sources.push(src);sendCtrl({type:"estado",v:"hablando"});
  const fin=()=>{sources=sources.filter(x=>x!==src);if(!sources.length)activarEscucha();};
  src.onended=fin;setTimeout(fin,Math.round(ab.duration*1000)+1500);
}
function ajustar16k(f32,inRate){
  if(inRate===16000)return f32;
  const r=inRate/16000,len=Math.round(f32.length/r),out=new Float32Array(len);
  for(let i=0;i<len;i++)out[i]=f32[Math.min(f32.length-1,Math.floor(i*r))];
  return out;
}
async function iniciar(){
  const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:false}});
  ctx=new AudioContext({sampleRate:16000});await ctx.resume();
  function conectar(){
    if(reconectando){clearTimeout(reconectando);reconectando=null;}
    if(ws){try{ws.onclose=null;ws.onerror=null;ws.close();}catch{}}
    ws=new WebSocket("ws://127.0.0.1:"+wsPort);ws.binaryType="arraybuffer";
    ws.onopen=()=>{activarEscucha();colaPreCtx.forEach(b=>playPcm24k(b));colaPreCtx=[];};
    ws.onclose=()=>{ws=null;if(!reconectando)reconectando=setTimeout(()=>{reconectando=null;conectar();},1500);};
    ws.onerror=()=>{try{ws.close();}catch{}};
    ws.onmessage=e=>{
      if(e.data instanceof ArrayBuffer){playPcm24k(e.data);return;}
      const m=JSON.parse(e.data);
      if(m.type==="interrupted")limpiarAudio();
      if(m.type==="wake")despertar();
      if(m.type==="escuchando")activarEscucha();
      if(m.type==="reposo"){despierto=false;dormida=true;framesWake=0;framesVoz=0;pausasVoz=0;colaVoz=0;}
    };
  }
  conectar();
  const src=ctx.createMediaStreamSource(stream),proc=ctx.createScriptProcessor(1024,1,1);
  src.connect(proc);proc.connect(ctx.destination);
  st.textContent="WebRTC activo";
  proc.onaudioprocess=ev=>{
    if(ctx&&ctx.state==="suspended"){try{ctx.resume();}catch{}}
    if(!ws||ws.readyState!==1)return;
    const d=ajustar16k(ev.inputBuffer.getChannelData(0),ctx.sampleRate);
    let sum=0;const pcm=new Int16Array(d.length);
    for(let i=0;i<d.length;i++){const v=Math.max(-1,Math.min(1,d[i]));sum+=v*v;pcm[i]=v<0?v*32768:v*32767;}
    const rms=Math.sqrt(sum/d.length),ahora=performance.now();
    if(!dormida&&sources.length===0&&rms<piso*1.15)piso=Math.min(0.007,piso*0.98+rms*0.02);
    const uActivo=Math.max(0.0065,piso*1.65),uWake=Math.max(0.0135,piso*2.1);
    if(dormida){
      preroll.push(pcm.buffer);if(preroll.length>8)preroll.shift();
      if(rms>uWake){framesWake++;}else{framesWake=0;}
    }
    const umbral=dormida?uWake:uActivo;
    if(rms>umbral){
      if(sources.length>0){limpiarAudio();sendCtrl({type:"interrupted"});}
      const estabaMudo=!dormida&&colaVoz===0;
      framesVoz++;pausasVoz=0;colaVoz=22;
      if(!dormida){
        if(framesVoz>=2)ultimoHabla=ahora;sendCtrl({type:"nivel",v:Math.min(1,rms*6)});
        if(estabaMudo){preroll.forEach(b=>ws.send(b));preroll=[];}
      }
    }else{
      if(framesVoz>0&&pausasVoz<1)pausasVoz++;else{framesVoz=0;pausasVoz=0;}
      if(colaVoz>0)colaVoz--;
    }
    if(sources.length>0)ultimoHabla=ahora;
    if(!dormida&&ahora-ultimoHabla>9000){
      despierto=false;dormida=true;framesWake=0;framesVoz=0;pausasVoz=0;colaVoz=0;
      sendCtrl({type:"sleep"});sendCtrl({type:"estado",v:"reposo"});
      return;
    }
    if(!dormida){ws.send(colaVoz>0?pcm.buffer:new Int16Array(pcm.length).buffer);}else if(framesWake>=3&&rms>uWake){despertar();ws.send(pcm.buffer);}
  };
}
iniciar().catch(e=>{st.textContent="Error: "+e;sendCtrl({type:"error",msg:String(e)});});
</script></body></html>"""


def preparar_perfil(perfil: str) -> bool:
    """Crea First Run y preferencias que suprimen la pantalla de bienvenida."""
    try:
        os.makedirs(perfil, exist_ok=True)
        with open(os.path.join(perfil, "First Run"), "a", encoding="utf-8"):
            pass
        prefs = os.path.join(perfil, "Default")
        os.makedirs(prefs, exist_ok=True)
        ruta_prefs = os.path.join(prefs, "Preferences")
        if not os.path.isfile(ruta_prefs):
            with open(ruta_prefs, "w", encoding="utf-8") as f:
                json.dump({
                    "browser": {"has_seen_welcome_page": True, "check_default_browser": False},
                    "profile": {"exit_type": "Normal"},
                }, f)
        return True
    except Exception:
        return False


def comando_edge(navegador: str, perfil: str, url: str) -> List[str]:
    """Argumentos para Chromium/Edge sin UI, sin barra de tareas ni prompts."""
    return [
        navegador,
        f"--user-data-dir={perfil}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-extensions",
        "--disable-features=Translate,OptimizationHints,MediaRouter",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
        "--window-size=200,160",
        "--window-position=-32000,-32000",
        f"--app={url}",
    ]


def startupinfo_oculto():
    """STARTUPINFO con wShowWindow=SW_HIDE en Windows."""
    try:
        import subprocess
        si = subprocess.STARTUPINFO()
        si.dwFlags |= _STARTF_USESHOWWINDOW
        si.wShowWindow = SW_HIDE
        return si
    except Exception:
        return None


def ocultar_ventana_pid(pid: int, titulo: Optional[str] = "Kaya Audio Bridge",
                        intentos: int = 15, espera: float = 0.2) -> bool:
    """Aplica WS_EX_TOOLWINDOW y SW_HIDE a cualquier ventana del PID."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False

    user32 = ctypes.windll.user32
    tipo_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    encontradas = []

    def _visitar(hwnd, _lparam):
        proceso = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proceso))
        if proceso.value != int(pid):
            return True
        if titulo:
            longitud = user32.GetWindowTextLengthW(hwnd)
            texto = ctypes.create_unicode_buffer(longitud + 1)
            user32.GetWindowTextW(hwnd, texto, longitud + 1)
            if titulo.lower() not in texto.value.lower():
                return True
        encontradas.append(hwnd)
        return True

    callback = tipo_callback(_visitar)
    for _ in range(intentos):
        encontradas.clear()
        user32.EnumWindows(callback, 0)
        for hwnd in encontradas:
            ex = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, (ex | _EX_TOOLWINDOW) & ~_EX_APPWINDOW)
            user32.ShowWindow(hwnd, SW_HIDE)
        if encontradas:
            return True
        time.sleep(espera)
    return False


__all__ = [
    "HTML_PUENTE", "preparar_perfil", "comando_edge", "startupinfo_oculto",
    "ocultar_ventana_pid", "SW_HIDE",
]
