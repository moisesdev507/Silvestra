"""Puente de audio WebRTC (Edge/Chromium) para Gemini Live sin ruido ni bloqueos PortAudio."""
import asyncio
import http.server
import json
import os
import queue
import socket
import socketserver
import subprocess
import threading
import time
from typing import Callable, Optional
import websockets

import webrtc_ventana as wv

SENAL_SLEEP = b"__WEBRTC_SLEEP__"

HTML_PUENTE = """<!doctype html><html><head><meta charset="utf-8"><title>Kaya Audio Bridge</title></head>
<body style="background:#0b0f17;color:#94a3b8;font-family:sans-serif;font-size:12px">
<div id="st">Iniciando puente WebRTC...</div>
<script>
const st=document.getElementById("st"),wsPort=location.hash.slice(1);
let ws,ctx,nextT=0,sources=[],despierto=true,dormida=false,ultimoHabla=performance.now(),colaPreCtx=[],piso=0.012,framesWake=0,framesVoz=0,pausasVoz=0,preroll=[],colaVoz=0;
function sendCtrl(o){if(ws&&ws.readyState===1)ws.send(JSON.stringify(o));}
function limpiarAudio(){sources.forEach(s=>{try{s.stop()}catch{}});sources=[];if(ctx)nextT=ctx.currentTime;}
function activarEscucha(){
  dormida=false;despierto=true;framesWake=0;framesVoz=0;pausasVoz=0;ultimoHabla=performance.now();
  sendCtrl({type:"estado",v:"escuchando"});
  if(ws&&ws.readyState===1){preroll.forEach(b=>ws.send(b));preroll=[];}
}
function despertar(){
  if(!dormida){ultimoHabla=performance.now();return;}
  dormida=false;despierto=true;framesWake=0;framesVoz=3;pausasVoz=0;colaVoz=22;ultimoHabla=performance.now();
  sendCtrl({type:"wake"});sendCtrl({type:"estado",v:"escuchando"});
  if(ws&&ws.readyState===1){preroll.forEach(b=>ws.send(b));preroll=[];}
}
function playPcm24k(buf){
  if(!ctx){colaPreCtx.push(buf);return;}
  const i16=new Int16Array(buf),f32=new Float32Array(i16.length);
  for(let i=0;i<i16.length;i++)f32[i]=i16[i]/32768;
  const ab=ctx.createBuffer(1,f32.length,24000);ab.getChannelData(0).set(f32);
  const src=ctx.createBufferSource();src.buffer=ab;src.connect(ctx.destination);
  const t=Math.max(ctx.currentTime,nextT);src.start(t);nextT=t+ab.duration;
  sources.push(src);sendCtrl({type:"estado",v:"hablando"});
  src.onended=()=>{sources=sources.filter(x=>x!==src);if(!sources.length){activarEscucha();}};
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
  ws=new WebSocket("ws://127.0.0.1:"+wsPort);ws.binaryType="arraybuffer";
  ws.onopen=()=>{activarEscucha();colaPreCtx.forEach(b=>playPcm24k(b));colaPreCtx=[];};
  ws.onmessage=e=>{
    if(e.data instanceof ArrayBuffer){playPcm24k(e.data);return;}
    const m=JSON.parse(e.data);
    if(m.type==="interrupted")limpiarAudio();
    if(m.type==="wake")despertar();
    if(m.type==="escuchando")activarEscucha();
    if(m.type==="reposo"){despierto=false;dormida=true;framesWake=0;framesVoz=0;pausasVoz=0;colaVoz=0;}
  };
  const src=ctx.createMediaStreamSource(stream),proc=ctx.createScriptProcessor(1024,1,1);
  src.connect(proc);proc.connect(ctx.destination);
  st.textContent="WebRTC activo";
  proc.onaudioprocess=ev=>{
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


def buscar_navegador_webrtc() -> Optional[str]:
    candidatos = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for ruta in candidatos:
        if ruta and os.path.isfile(ruta):
            return ruta
    return None


def webrtc_disponible() -> bool:
    return buscar_navegador_webrtc() is not None


def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _HTTPReutilizable(socketserver.TCPServer):
    allow_reuse_address = True


class PuenteWebRTC:
    """Gestiona el proceso navegador oculto y las colas PCM bidireccionales."""

    def __init__(
        self,
        on_estado: Optional[Callable[[str], None]] = None,
        on_nivel: Optional[Callable[[float], None]] = None,
    ):
        self.on_estado = on_estado
        self.on_nivel = on_nivel
        self.cola_entrada: queue.Queue = queue.Queue(maxsize=600)
        self.cola_salida: queue.Queue = queue.Queue()
        self.activo = False
        self.dormida = False
        self._ultimo_habla = time.time()
        self._httpd = None
        self._proc = None
        self._loop = None
        self._ws_cliente = None
        self._hilo_ws = None

    def _emitir_estado(self, est: str):
        self.dormida = est == "reposo"
        if est == "escuchando":
            self._ultimo_habla = time.time()
        if callable(self.on_estado):
            try:
                self.on_estado(est)
            except Exception:
                pass

    def _emitir_nivel(self, niv: float):
        if niv > 0.05:
            self._ultimo_habla = time.time()
        if callable(self.on_nivel):
            try:
                self.on_nivel(niv)
            except Exception:
                pass

    def _encolar_entrada(self, item: bytes):
        if self.cola_entrada.full():
            try:
                self.cola_entrada.get_nowait()
            except queue.Empty:
                pass
        try:
            self.cola_entrada.put_nowait(item)
        except queue.Full:
            pass

    def iniciar(self) -> bool:
        navegador = buscar_navegador_webrtc()
        if not navegador:
            return False
        self.activo = True
        puerto_http = _puerto_libre()
        puerto_ws = _puerto_libre()

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(HTML_PUENTE.encode("utf-8"))

            def log_message(self, *a):
                pass

        self._httpd = _HTTPReutilizable(("127.0.0.1", puerto_http), _Handler)
        threading.Thread(target=self._httpd.serve_forever, daemon=True, name="webrtc-http").start()

        def _correr_ws():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def _handler_ws(ws):
                self._ws_cliente = ws
                print("[LIVE][WEBRTC] Puente de audio limpio conectado (16kHz).", flush=True)
                self.activar_escucha()

                async def _vigilante_inactividad():
                    while self.activo:
                        await asyncio.sleep(0.5)
                        if not self.dormida and (time.time() - self._ultimo_habla > 9.8):
                            self.dormida = True
                            print("[LIVE][WEBRTC] 9s en silencio -> Reposo Azul (0 tokens).", flush=True)
                            self._encolar_entrada(SENAL_SLEEP)
                            self._emitir_estado("reposo")
                            try:
                                if self._ws_cliente is not None:
                                    await self._ws_cliente.send(json.dumps({"type": "reposo"}))
                            except Exception:
                                pass

                t_vigilante = asyncio.create_task(_vigilante_inactividad())
                async def _enviar_salida():
                    while self.activo:
                        try:
                            item = await asyncio.to_thread(self.cola_salida.get, timeout=0.08)
                            if isinstance(item, str):
                                await ws.send(item)
                            elif item:
                                await ws.send(item)
                        except queue.Empty:
                            continue
                        except Exception:
                            break

                t_out = asyncio.create_task(_enviar_salida())
                try:
                    async for msg in ws:
                        if not self.activo:
                            break
                        if isinstance(msg, bytes):
                            self._encolar_entrada(msg)
                        else:
                            data = json.loads(msg)
                            tipo = data.get("type")
                            if tipo == "estado":
                                self._emitir_estado(str(data.get("v", "escuchando")))
                            elif tipo == "nivel":
                                self._emitir_nivel(float(data.get("v", 0.0)))
                            elif tipo == "wake":
                                if self.dormida:
                                    self.dormida = False
                                    print("[LIVE][WEBRTC] Voz detectada -> Despertando a Amarillo.", flush=True)
                                self._ultimo_habla = time.time()
                                self._emitir_estado("escuchando")
                            elif tipo == "sleep":
                                if not self.dormida:
                                    self.dormida = True
                                    print("[LIVE][WEBRTC] 9s en silencio -> Reposo Azul (0 tokens).", flush=True)
                                    self._encolar_entrada(SENAL_SLEEP)
                                    self._emitir_estado("reposo")
                            elif tipo == "error":
                                print(f"[LIVE][WEBRTC] Aviso navegador: {data.get('msg')}", flush=True)
                except websockets.ConnectionClosed:
                    pass
                finally:
                    t_vigilante.cancel()
                    t_out.cancel()
                    if self._ws_cliente is ws:
                        self._ws_cliente = None

            async def _main_ws():
                async with websockets.serve(_handler_ws, "127.0.0.1", puerto_ws):
                    while self.activo:
                        await asyncio.sleep(0.15)

            try:
                self._loop.run_until_complete(_main_ws())
            except Exception:
                pass
            finally:
                try:
                    self._loop.close()
                except Exception:
                    pass

        self._hilo_ws = threading.Thread(target=_correr_ws, daemon=True, name="webrtc-ws")
        self._hilo_ws.start()

        perfil = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".kaya_webrtc_perfil")
        wv.preparar_perfil(perfil)
        url = f"http://127.0.0.1:{puerto_http}/#{puerto_ws}"
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self._proc = subprocess.Popen(
                wv.comando_edge(navegador, perfil, url),
                creationflags=flags,
                startupinfo=wv.startupinfo_oculto(),
            )
            threading.Thread(
                target=wv.ocultar_ventana_pid, args=(self._proc.pid,), daemon=True
            ).start()
            return True
        except Exception as e:
            print(f"[LIVE][WEBRTC] No se pudo iniciar navegador oculto: {e}", flush=True)
            self.detener()
            return False

    def enviar_audio_salida(self, pcm24k: bytes):
        if self.activo and pcm24k:
            self._ultimo_habla = time.time()
            self.cola_salida.put(pcm24k)

    def interrumpir_salida(self):
        if not self.activo:
            return
        with self.cola_salida.mutex:
            self.cola_salida.queue.clear()
        self.cola_salida.put(json.dumps({"type": "interrupted"}))

    def activar_escucha(self):
        """Reinicia el temporizador de 9s y pone el puente en 'escuchando'."""
        self.dormida = False
        self._ultimo_habla = time.time()
        self._emitir_estado("escuchando")
        if self.activo:
            self.cola_salida.put(json.dumps({"type": "escuchando"}))

    def despertar(self):
        self.activar_escucha()

    def detener(self):
        self.activo = False
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
