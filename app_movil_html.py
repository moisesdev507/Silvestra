"""Plantilla HTML5 y CSS para la aplicación web PWA móvil de Lyris."""
from app_movil_js import SCRIPT_MOVIL_JS

_HTML_ESTRUCTURA = """<!DOCTYPE html>
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
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);height:100dvh;display:flex;flex-direction:column;overflow:hidden;}
header{padding:10px 14px;background:rgba(10,13,20,0.92);border-bottom:1px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;z-index:20;flex-shrink:0;}
.brand{display:flex;align-items:center;gap:10px;}
.avatar-box{width:42px;height:42px;position:relative;display:flex;align-items:center;justify-content:center;}.avatar-svg{width:38px;height:38px;}
.halo{position:absolute;inset:0;border-radius:50%;border:1.5px solid var(--primary);animation:pulseHalo 3s infinite;}
@keyframes pulseHalo{0%,100%{transform:scale(0.95);opacity:0.4;}50%{transform:scale(1.08);opacity:0.9;}}
.brand-info h1{font-size:15px;font-weight:700;}
.brand-info .status{font-size:11px;color:var(--accent);display:flex;align-items:center;gap:4px;}.status-dot{width:6px;height:6px;border-radius:50%;background:var(--accent);}
.header-actions{display:flex;gap:5px;align-items:center;}
.btn-badge{padding:6px 9px;border-radius:18px;border:1px solid var(--card-border);background:var(--card);color:var(--text-muted);font-size:11px;font-weight:600;display:flex;align-items:center;cursor:pointer;text-decoration:none;}
.btn-badge.active-voz{background:rgba(56,189,248,0.25);border-color:var(--primary);color:#7dd3fc;}
.btn-badge.active-mentor{background:rgba(99,102,241,0.25);border-color:var(--mentor);color:#a5b4fc;}
.btn-badge.active-privado{background:rgba(239,68,68,0.25);border-color:#ef4444;color:#fca5a5;}
#chat{flex:1;overflow-y:auto;padding:14px 12px;display:flex;flex-direction:column;gap:14px;}
.msg{max-width:86%;padding:11px 14px;border-radius:18px;font-size:14.5px;line-height:1.45;word-wrap:break-word;}
.msg.user{align-self:flex-end;background:var(--user-bg);border-bottom-right-radius:4px;color:#fff;}
.msg.lyris{align-self:flex-start;background:var(--card);border:1px solid var(--card-border);border-bottom-left-radius:4px;}
.msg pre{background:#0f172a;padding:8px;border-radius:6px;overflow-x:auto;font-size:12px;color:#38bdf8;}
.msg.thinking{font-style:italic;color:var(--text-muted);display:flex;align-items:center;gap:6px;}.msg-time{font-size:10px;color:var(--text-muted);margin-top:4px;text-align:right;}
.btn-tts{background:transparent;border:none;color:var(--text-muted);cursor:pointer;font-size:13px;margin-left:6px;padding:2px 4px;border-radius:4px;vertical-align:middle;}
.speaking-indicator{display:inline-flex;gap:3px;margin-left:6px;vertical-align:middle;}
.sound-bar{width:3px;height:10px;background:var(--primary);animation:wave 1s infinite;}
.sound-bar:nth-child(2){animation-delay:.2s;height:14px;}.sound-bar:nth-child(3){animation-delay:.4s;height:8px;}
@keyframes wave{0%,100%{transform:scaleY(0.4);}50%{transform:scaleY(1);}}
footer{padding:10px 12px;padding-bottom:max(10px,env(safe-area-inset-bottom));background:var(--card);border-top:1px solid var(--card-border);flex-shrink:0;}
.input-bar{display:flex;align-items:center;gap:8px;}
.input-field{flex:1;background:#1f2937;border:1px solid #374151;color:#fff;padding:12px 14px;border-radius:22px;font-size:15px;outline:none;}.input-field:focus{border-color:var(--primary);}
.btn-action{width:44px;height:44px;border-radius:50%;border:none;display:flex;align-items:center;justify-content:center;cursor:pointer;}
.btn-mic{background:#374151;color:var(--text);}.btn-mic.recording{background:#ef4444;color:#fff;animation:micPulse 1.2s infinite;}
@keyframes micPulse{0%,100%{transform:scale(1);}50%{transform:scale(1.1);}}
.btn-send{background:var(--primary);color:#0a0d14;}
</style>
</head>
<body>
<header>
  <div class="brand">
    <div class="avatar-box"><div class="halo" id="avatarHalo"></div>
      <svg class="avatar-svg" id="avatarFace" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="42" fill="#0f172a" stroke="#38bdf8" stroke-width="2.5" id="faceColor"/>
        <path d="M28 40 Q38 34 46 40" stroke="#38bdf8" stroke-width="3" fill="none" stroke-linecap="round" id="eyebrowL"/>
        <path d="M54 40 Q62 34 72 40" stroke="#38bdf8" stroke-width="3" fill="none" stroke-linecap="round" id="eyebrowR"/>
        <ellipse cx="37" cy="50" rx="5" ry="7" fill="#38bdf8" id="eyeL"/><ellipse cx="63" cy="50" rx="5" ry="7" fill="#38bdf8" id="eyeR"/>
        <path d="M38 68 Q50 78 62 68" stroke="#38bdf8" stroke-width="3" fill="none" stroke-linecap="round" id="mouth"/>
      </svg>
    </div>
    <div class="brand-info"><h1>Lyris Mobile</h1><div class="status"><span class="status-dot"></span><span id="txtStatus">Conectada</span></div></div>
  </div>
  <div class="header-actions">
    <button class="btn-badge active-voz" id="btnVoz" onclick="toggleVoz()" title="Voz automática">🔊 Voz</button>
    <button class="btn-badge" id="btnMentor" onclick="toggleMentor()">🎓 Mentora</button>
    <button class="btn-badge" id="btnPrivado" onclick="togglePrivado()">🔒 Privado</button>
    <button class="btn-badge" id="btnLimpiar" onclick="limpiarChat()" title="Limpiar conversación">🗑️ Limpiar</button>
  </div>
</header>
<main id="chat">
  <div class="msg lyris">Hola, soy Lyris. ¿En qué trabajamos hoy?<button class="btn-tts" onclick="pedirVoz(this,'Hola, soy Lyris. ¿En qué trabajamos hoy?','alegre')" title="Escuchar">🔊</button><div class="msg-time">Ahora</div></div>
</main>
<footer>
  <div class="input-bar">
    <input type="text" id="txtInput" class="input-field" placeholder="Escribe o mantén el micro..." autocomplete="off">
    <button class="btn-action btn-mic" id="btnMic" title="Hablar"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg></button>
    <button class="btn-action btn-send" id="btnSend" title="Enviar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></button>
  </div>
</footer>
<audio id="lyrisAudio" preload="auto" playsinline></audio>
<script>
""" + SCRIPT_MOVIL_JS + """
</script>
</body>
</html>
"""

PAGINA_MOVIL_HTML = _HTML_ESTRUCTURA
