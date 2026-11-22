"""Plantilla HTML5, CSS y JavaScript para la aplicación web PWA móvil de Lyris."""

PAGINA_MOVIL_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>Lyris</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#0a0d14">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<style>
:root{--bg:#0a0d14;--card:#111827;--card-border:#1f2937;--text:#f3f4f6;--text-muted:#9ca3af;--primary:#38bdf8;--user-bg:#1e293b;--mentor:#6366f1;--accent:#10b981;}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);height:100dvh;display:flex;flex-direction:column;overflow:hidden;}
header{padding:10px 14px;background:rgba(10,13,20,0.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;z-index:20;flex-shrink:0;}
.brand{display:flex;align-items:center;gap:10px;}
.avatar-box{width:42px;height:42px;position:relative;display:flex;align-items:center;justify-content:center;}
.avatar-svg{width:38px;height:38px;transition:all 0.3s ease;}
.halo{position:absolute;inset:0;border-radius:50%;border:1.5px solid var(--primary);animation:pulseHalo 3s infinite ease-in-out;}
@keyframes pulseHalo{0%,100%{transform:scale(0.95);opacity:0.4;}50%{transform:scale(1.08);opacity:0.9;}}
.brand-info h1{font-size:15px;font-weight:700;}
.brand-info .status{font-size:11px;color:var(--accent);display:flex;align-items:center;gap:4px;}
.status-dot{width:6px;height:6px;border-radius:50%;background:var(--accent);}
.header-actions{display:flex;gap:6px;}
.btn-badge{padding:6px 10px;border-radius:20px;border:1px solid var(--card-border);background:var(--card);color:var(--text-muted);font-size:11px;font-weight:600;display:flex;align-items:center;cursor:pointer;}
.btn-badge.active-mentor{background:rgba(99,102,241,0.25);border-color:var(--mentor);color:#a5b4fc;}
.btn-badge.active-privado{background:rgba(239,68,68,0.25);border-color:#ef4444;color:#fca5a5;}
#chat{flex:1;overflow-y:auto;padding:14px 12px;display:flex;flex-direction:column;gap:14px;scroll-behavior:smooth;}
.msg{max-width:86%;padding:11px 14px;border-radius:18px;font-size:14.5px;line-height:1.45;word-wrap:break-word;}
.msg.user{align-self:flex-end;background:var(--user-bg);border-bottom-right-radius:4px;color:#fff;}
.msg.lyris{align-self:flex-start;background:var(--card);border:1px solid var(--card-border);border-bottom-left-radius:4px;color:var(--text);}
.msg.lyris pre{background:#0f172a;padding:10px;border-radius:8px;overflow-x:auto;font-family:monospace;font-size:13px;margin:8px 0;border:1px solid #1e293b;color:#38bdf8;}
.msg-time{font-size:10px;color:var(--text-muted);margin-top:4px;text-align:right;}
.speaking-indicator{display:inline-flex;align-items:center;gap:3px;margin-left:6px;vertical-align:middle;}
.sound-bar{width:3px;height:10px;background:var(--primary);animation:wave 1s infinite ease-in-out;}
.sound-bar:nth-child(2){animation-delay:0.2s;height:14px;}
.sound-bar:nth-child(3){animation-delay:0.4s;height:8px;}
@keyframes wave{0%,100%{transform:scaleY(0.4);}50%{transform:scaleY(1);}}
footer{padding:10px 12px;padding-bottom:max(10px,env(safe-area-inset-bottom));background:var(--card);border-top:1px solid var(--card-border);flex-shrink:0;}
.input-bar{display:flex;align-items:center;gap:8px;}
.input-field{flex:1;background:#1f2937;border:1px solid #374151;color:#fff;padding:12px 14px;border-radius:22px;font-size:15px;outline:none;}
.input-field:focus{border-color:var(--primary);}
.btn-action{width:44px;height:44px;border-radius:50%;border:none;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;}
.btn-mic{background:#374151;color:var(--text);}
.btn-mic.recording{background:#ef4444;color:#fff;animation:micPulse 1.2s infinite;}
@keyframes micPulse{0%,100%{transform:scale(1);}50%{transform:scale(1.1);}}
.btn-send{background:var(--primary);color:#0a0d14;}
</style>
</head>
<body>
<header>
  <div class="brand">
    <div class="avatar-box">
      <div class="halo" id="avatarHalo"></div>
      <svg class="avatar-svg" id="avatarFace" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="42" fill="#0f172a" stroke="#38bdf8" stroke-width="2.5" id="faceColor"/>
        <path d="M28 40 Q38 34 46 40" stroke="#38bdf8" stroke-width="3" fill="none" stroke-linecap="round" id="eyebrowL"/>
        <path d="M54 40 Q62 34 72 40" stroke="#38bdf8" stroke-width="3" fill="none" stroke-linecap="round" id="eyebrowR"/>
        <ellipse cx="37" cy="50" rx="5" ry="7" fill="#38bdf8" id="eyeL"/>
        <ellipse cx="63" cy="50" rx="5" ry="7" fill="#38bdf8" id="eyeR"/>
        <path d="M38 68 Q50 78 62 68" stroke="#38bdf8" stroke-width="3" fill="none" stroke-linecap="round" id="mouth"/>
      </svg>
    </div>
    <div class="brand-info">
      <h1>Lyris Mobile</h1>
      <div class="status"><span class="status-dot"></span><span id="txtStatus">Conectada</span></div>
    </div>
  </div>
  <div class="header-actions">
    <button class="btn-badge" id="btnMentor" onclick="toggleMentor()">🎓 Mentora</button>
    <button class="btn-badge" id="btnPrivado" onclick="togglePrivado()">🔒 Privado</button>
  </div>
</header>
<main id="chat">
  <div class="msg lyris">Hola, soy Lyris. Estoy conectada contigo en vivo desde tu celular. ¿En qué trabajamos hoy?<div class="msg-time">Ahora</div></div>
</main>
<footer>
  <div class="input-bar">
    <input type="text" id="txtInput" class="input-field" placeholder="Escribe o mantén el micro..." autocomplete="off">
    <button class="btn-action btn-mic" id="btnMic" title="Hablar"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg></button>
    <button class="btn-action btn-send" id="btnSend" title="Enviar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></button>
  </div>
</footer>
<audio id="audioPlayer" playsinline></audio>
<script>
let token=localStorage.getItem('lyris_device_token')||new URLSearchParams(window.location.search).get('token')||'';
if(token)localStorage.setItem('lyris_device_token',token);
async function asegurarSesion(){
  if(!token){try{const res=await fetch('/api/sesion');const d=await res.json();if(d.ok&&d.token){token=d.token;localStorage.setItem('lyris_device_token',token);}}catch(e){}}
}
asegurarSesion();
function actualizarCara(emocion){
  const halo=document.getElementById('avatarHalo'),mouth=document.getElementById('mouth'),eyebrowL=document.getElementById('eyebrowL'),eyebrowR=document.getElementById('eyebrowR'),face=document.getElementById('faceColor');
  const colores={neutral:'#38bdf8',alegre:'#10b981',concentrada:'#6366f1',orgullosa:'#eab308',firme:'#ef4444',calida:'#f472b6'};
  const c=colores[emocion]||colores.neutral;
  halo.style.borderColor=c;face.setAttribute('stroke',c);
  if(emocion==='alegre'||emocion==='orgullosa'){mouth.setAttribute('d','M35 66 Q50 82 65 66');eyebrowL.setAttribute('d','M28 36 Q38 32 46 36');eyebrowR.setAttribute('d','M54 36 Q62 32 72 36');}
  else if(emocion==='concentrada'){mouth.setAttribute('d','M40 70 L60 70');eyebrowL.setAttribute('d','M28 42 L46 41');eyebrowR.setAttribute('d','M54 41 L72 42');}
  else if(emocion==='firme'){mouth.setAttribute('d','M38 72 Q50 68 62 72');eyebrowL.setAttribute('d','M28 38 L46 44');eyebrowR.setAttribute('d','M54 44 L72 38');}
  else{mouth.setAttribute('d','M38 68 Q50 78 62 68');eyebrowL.setAttribute('d','M28 40 Q38 34 46 40');eyebrowR.setAttribute('d','M54 40 Q62 34 72 40');}
}
function agregarMensaje(texto,remitente,conVoz=false){
  const chat=document.getElementById('chat'),m=document.createElement('div');
  m.className='msg '+remitente;m.innerHTML=texto.replace(/`([^`]+)`/g,'<code>$1</code>');
  if(conVoz)m.innerHTML+='<span class=\"speaking-indicator\"><span class=\"sound-bar\"></span><span class=\"sound-bar\"></span><span class=\"sound-bar\"></span></span>';
  const time=document.createElement('div');time.className='msg-time';time.textContent=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
  m.appendChild(time);chat.appendChild(m);chat.scrollTop=chat.scrollHeight;
}
function reproducirAudio(b64){
  if(!b64)return;const player=document.getElementById('audioPlayer');player.src='data:audio/mp3;base64,'+b64;player.play().catch(e=>{});
}
async function enviarTexto(){
  const input=document.getElementById('txtInput'),txt=input.value.trim();
  if(!txt)return;input.value='';agregarMensaje(txt,'user');
  try{
    const res=await fetch('/api/movil/voz',{method:'POST',headers:{'Content-Type':'application/json','X-Device-Token':token},body:JSON.stringify({texto:txt})});
    const d=await res.json();
    if(d.ok){actualizarCara(d.emocion);agregarMensaje(d.respuesta,'lyris',Boolean(d.audio_base64));if(d.audio_base64)reproducirAudio(d.audio_base64);}
    else{agregarMensaje(d.error||'Error procesando consulta.','lyris');}
  }catch(e){agregarMensaje('Sin conexión con Lyris central.','lyris');}
}
document.getElementById('btnSend').onclick=enviarTexto;
document.getElementById('txtInput').addEventListener('keydown',(e)=>{if(e.key==='Enter')enviarTexto();});
let mediaRecorder=null,audioChunks=[],btnMic=document.getElementById('btnMic');
async function iniciarGrabacion(){
  try{
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    audioChunks=[];mediaRecorder=new MediaRecorder(stream);
    mediaRecorder.ondataavailable=(e)=>{if(e.data.size>0)audioChunks.push(e.data);};
    mediaRecorder.onstop=async()=>{
      btnMic.classList.remove('recording');
      const blob=new Blob(audioChunks,{type:'audio/webm'});
      if(blob.size<500)return;
      const fd=new FormData();fd.append('audio',blob,'nota.webm');
      try{
        const res=await fetch('/api/movil/voz',{method:'POST',headers:{'X-Device-Token':token},body:fd});
        const d=await res.json();
        if(d.ok){if(d.texto_usuario)agregarMensaje(d.texto_usuario,'user');actualizarCara(d.emocion);agregarMensaje(d.respuesta,'lyris',Boolean(d.audio_base64));if(d.audio_base64)reproducirAudio(d.audio_base64);}
        else{agregarMensaje(d.error||'No se capturó audio.','lyris');}
      }catch(err){agregarMensaje('Fallo enviando nota de voz a Lyris.','lyris');}
    };
    mediaRecorder.start();btnMic.classList.add('recording');
  }catch(e){alert('Permiso de micrófono requerido.');}
}
function detenerGrabacion(){if(mediaRecorder&&mediaRecorder.state==='recording')mediaRecorder.stop();}
btnMic.addEventListener('mousedown',iniciarGrabacion);btnMic.addEventListener('mouseup',detenerGrabacion);
btnMic.addEventListener('touchstart',(e)=>{e.preventDefault();iniciarGrabacion();});
btnMic.addEventListener('touchend',(e)=>{e.preventDefault();detenerGrabacion();});
async function toggleMentor(){const btn=document.getElementById('btnMentor'),activo=btn.classList.toggle('active-mentor');document.getElementById('txtInput').value=activo?'activa modo mentora':'desactiva modo mentora';enviarTexto();}
async function togglePrivado(){const btn=document.getElementById('btnPrivado'),activo=btn.classList.toggle('active-privado');document.getElementById('txtInput').value=activo?'activa modo privado':'desactiva modo privado';enviarTexto();}
if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(e=>{});}
</script>
</body>
</html>
"""
