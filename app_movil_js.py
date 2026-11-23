"""Código JavaScript para la aplicación web PWA móvil de Lyris."""

SCRIPT_MOVIL_JS = r"""
let token = localStorage.getItem('lyris_device_token') || '';
const _uP = new URLSearchParams(window.location.search);
if (_uP.has('token')) {
  token = _uP.get('token') || '';
  if (token) localStorage.setItem('lyris_device_token', token);
  _uP.delete('token');
  const _nu = window.location.pathname + (_uP.toString() ? '?' + _uP.toString() : '');
  window.history.replaceState({}, document.title, _nu);
}

let vozActiva = true, audioInit = false, _audioBlobUrl = null;
const SILENT_WAV = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';

function toggleVoz() {
  vozActiva = document.getElementById('btnVoz').classList.toggle('active-voz');
}

function initAudio() {
  if (audioInit) return;
  const p = document.getElementById('lyrisAudio');
  if (!p) return;
  p.src = SILENT_WAV;
  p.play().then(() => { audioInit = true; }).catch(() => {});
}
document.addEventListener('click', initAudio, { once: true });
document.addEventListener('touchstart', initAudio, { once: true });

async function asegurarSesion() {
  if (!token) {
    try {
      const r = await fetch('/api/sesion');
      const d = await r.json();
      if (d.ok && d.token) {
        token = d.token;
        localStorage.setItem('lyris_device_token', token);
      }
    } catch (e) {}
  }
}
asegurarSesion();

function pedirTokenPrompt() {
  const t = prompt('Ingresa el token de dispositivo de Lyris:');
  if (t && t.trim()) {
    token = t.trim();
    localStorage.setItem('lyris_device_token', token);
    return true;
  }
  return false;
}

async function fetchConToken(url, opt = {}, reintento = true) {
  opt.headers = opt.headers || {};
  if (token) opt.headers['X-Device-Token'] = token;
  const r = await fetch(url, opt);
  if (r.status === 401 && reintento) {
    if (pedirTokenPrompt()) return fetchConToken(url, opt, false);
  }
  return r;
}

function actualizarCara(emocion) {
  const cols = { neutral: '#38bdf8', alegre: '#10b981', concentrada: '#6366f1', orgullosa: '#eab308', firme: '#ef4444', calida: '#f472b6' };
  const c = cols[emocion] || cols.neutral;
  const halo = document.getElementById('avatarHalo');
  const face = document.getElementById('faceColor');
  if (halo) halo.style.borderColor = c;
  if (face) face.setAttribute('stroke', c);
  const al = ['M35 66 Q50 82 65 66', 'M28 36 Q38 32 46 36', 'M54 36 Q62 32 72 36'];
  const cfg = ({
    alegre: al,
    orgullosa: al,
    concentrada: ['M40 70 L60 70', 'M28 42 L46 41', 'M54 41 L72 42'],
    firme: ['M38 72 Q50 68 62 72', 'M28 38 L46 44', 'M54 44 L72 38']
  })[emocion] || ['M38 68 Q50 78 62 68', 'M28 40 Q38 34 46 40', 'M54 40 Q62 34 72 40'];
  const mouth = document.getElementById('mouth');
  const eyebrowL = document.getElementById('eyebrowL');
  const eyebrowR = document.getElementById('eyebrowR');
  if (mouth) mouth.setAttribute('d', cfg[0]);
  if (eyebrowL) eyebrowL.setAttribute('d', cfg[1]);
  if (eyebrowR) eyebrowR.setAttribute('d', cfg[2]);
}

function mostrarPensando() {
  quitarPensando();
  const c = document.getElementById('chat');
  if (!c) return;
  const m = document.createElement('div');
  m.id = 'msgThinking';
  m.className = 'msg lyris thinking';
  m.innerHTML = '<span>Lyris está pensando...</span><span class="speaking-indicator"><span class="sound-bar"></span><span class="sound-bar"></span><span class="sound-bar"></span></span>';
  c.appendChild(m);
  c.scrollTop = c.scrollHeight;
}

function quitarPensando() {
  const el = document.getElementById('msgThinking');
  if (el) el.remove();
}

function guardarEnHistorial(rol, texto, hora, emocion, b64) {
  try {
    let hist = JSON.parse(localStorage.getItem('lyris_chat_hist') || '[]');
    if (!Array.isArray(hist)) hist = [];
    hist.push({ rol: rol, texto: texto, hora: hora, emocion: emocion || 'neutral', b64: b64 || '' });
    if (hist.length > 50) hist = hist.slice(-50);
    localStorage.setItem('lyris_chat_hist', JSON.stringify(hist));
  } catch (e) {}
}

function agregarMensaje(txt, rem, emo = 'neutral', b64 = '', hora = '', guardar = true) {
  quitarPensando();
  const c = document.getElementById('chat');
  if (!c) return;
  const m = document.createElement('div');
  m.className = 'msg ' + rem;
  m.innerHTML = txt.replace(/`([^`]+)`/g, '<code>$1</code>');
  if (rem === 'lyris') {
    const b = document.createElement('button');
    b.className = 'btn-tts';
    b.title = 'Escuchar';
    b.textContent = '🔊';
    if (b64) b.dataset.b64 = b64;
    b.onclick = () => pedirVoz(b, txt, emo);
    m.appendChild(b);
  }
  const t = document.createElement('div');
  t.className = 'msg-time';
  const h = hora || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  t.textContent = h;
  m.appendChild(t);
  c.appendChild(m);
  c.scrollTop = c.scrollHeight;
  if (guardar) {
    guardarEnHistorial(rem, txt, h, emo, b64);
  }
}

function playAudio(b64) {
  if (!b64) return;
  const p = document.getElementById('lyrisAudio');
  if (!p) return;
  p.pause();
  if (_audioBlobUrl) {
    try { URL.revokeObjectURL(_audioBlobUrl); } catch (e) {}
    _audioBlobUrl = null;
  }
  try {
    const bs = atob(b64);
    const ab = new Uint8Array(bs.length);
    for (let i = 0; i < bs.length; i++) ab[i] = bs.charCodeAt(i);
    const blob = new Blob([ab], { type: 'audio/mpeg' });
    _audioBlobUrl = URL.createObjectURL(blob);
    p.src = _audioBlobUrl;
    p.play().catch(() => {});
  } catch (err) {}
}

async function pedirVoz(b, txt, emo) {
  initAudio();
  if (b.dataset.b64) {
    playAudio(b.dataset.b64);
    return;
  }
  b.textContent = '⏳';
  try {
    const r = await fetchConToken('/api/movil/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto: txt, emocion: emo })
    });
    const d = await r.json();
    if (d.ok && d.audio_base64) {
      b.dataset.b64 = d.audio_base64;
      b.textContent = '🔊';
      playAudio(d.audio_base64);
    } else {
      b.textContent = '⚠️';
      setTimeout(() => { b.textContent = '🔊'; }, 2000);
    }
  } catch (e) {
    b.textContent = '⚠️';
    setTimeout(() => { b.textContent = '🔊'; }, 2000);
  }
}

async function enviarTexto() {
  initAudio();
  const inp = document.getElementById('txtInput');
  if (!inp) return;
  const txt = inp.value.trim();
  if (!txt) return;
  inp.value = '';
  agregarMensaje(txt, 'user');
  mostrarPensando();
  try {
    const r = await fetchConToken('/api/movil/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto: txt, hablar: vozActiva })
    });
    const d = await r.json();
    quitarPensando();
    if (d.ok) {
      actualizarCara(d.emocion);
      agregarMensaje(d.respuesta, 'lyris', d.emocion, d.audio_base64 || '');
      if (vozActiva && d.audio_base64) {
        playAudio(d.audio_base64);
      }
    } else {
      agregarMensaje(d.error || 'Error procesando consulta.', 'lyris');
    }
  } catch (e) {
    quitarPensando();
    agregarMensaje('Sin conexión con Lyris central.', 'lyris');
  }
}

function limpiarChat() {
  try { localStorage.removeItem('lyris_chat_hist'); } catch (e) {}
  const c = document.getElementById('chat');
  if (!c) return;
  c.innerHTML = '';
  agregarMensaje('Hola, soy Lyris. ¿En qué trabajamos hoy?', 'lyris', 'alegre', '', 'Ahora', false);
}

function cargarHistorial() {
  const c = document.getElementById('chat');
  if (!c) return;
  let hist = [];
  try { hist = JSON.parse(localStorage.getItem('lyris_chat_hist') || '[]'); } catch (e) { hist = []; }
  if (Array.isArray(hist) && hist.length > 0) {
    c.innerHTML = '';
    for (const m of hist) {
      agregarMensaje(m.texto, m.rol, m.emocion, m.b64, m.hora, false);
    }
    c.scrollTop = c.scrollHeight;
  } else {
    c.innerHTML = '';
    agregarMensaje('Hola, soy Lyris. ¿En qué trabajamos hoy?', 'lyris', 'alegre', '', 'Ahora', false);
  }
}

let mediaRecorder = null, audioChunks = [];
async function iniciarGrabacion() {
  initAudio();
  const btnMic = document.getElementById('btnMic');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };
    mediaRecorder.onstop = async () => {
      if (btnMic) btnMic.classList.remove('recording');
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      if (blob.size < 500) return;
      mostrarPensando();
      const fd = new FormData();
      fd.append('audio', blob, 'nota.webm');
      try {
        const r = await fetchConToken('/api/movil/voz', { method: 'POST', body: fd });
        const d = await r.json();
        quitarPensando();
        if (d.ok) {
          if (d.texto_usuario) agregarMensaje(d.texto_usuario, 'user');
          actualizarCara(d.emocion);
          agregarMensaje(d.respuesta, 'lyris', d.emocion, d.audio_base64 || '');
          if (vozActiva && d.audio_base64) playAudio(d.audio_base64);
        } else {
          agregarMensaje(d.error || 'No se capturó audio.', 'lyris');
        }
      } catch (err) {
        quitarPensando();
        agregarMensaje('Fallo enviando nota de voz a Lyris.', 'lyris');
      }
    };
    mediaRecorder.start();
    if (btnMic) btnMic.classList.add('recording');
  } catch (e) {
    alert('Permiso de micrófono requerido.');
  }
}

function detenerGrabacion() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  }
}

async function toggleMentor() {
  const btn = document.getElementById('btnMentor');
  const a = btn ? btn.classList.toggle('active-mentor') : false;
  const inp = document.getElementById('txtInput');
  if (inp) inp.value = a ? 'activa modo mentora' : 'desactiva modo mentora';
  enviarTexto();
}

async function togglePrivado() {
  const btn = document.getElementById('btnPrivado');
  const a = btn ? btn.classList.toggle('active-privado') : false;
  const inp = document.getElementById('txtInput');
  if (inp) inp.value = a ? 'activa modo privado' : 'desactiva modo privado';
  enviarTexto();
}

function registrarEventosMovil() {
  const btnSend = document.getElementById('btnSend');
  if (btnSend) btnSend.onclick = enviarTexto;

  const txtInput = document.getElementById('txtInput');
  if (txtInput) {
    txtInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') enviarTexto();
    });
  }

  const btnMic = document.getElementById('btnMic');
  if (btnMic) {
    btnMic.addEventListener('mousedown', iniciarGrabacion);
    btnMic.addEventListener('mouseup', detenerGrabacion);
    btnMic.addEventListener('touchstart', (e) => {
      e.preventDefault();
      iniciarGrabacion();
    });
    btnMic.addEventListener('touchend', (e) => {
      e.preventDefault();
      detenerGrabacion();
    });
  }

  const btnVoz = document.getElementById('btnVoz');
  if (btnVoz) btnVoz.onclick = toggleVoz;

  const btnMentor = document.getElementById('btnMentor');
  if (btnMentor) btnMentor.onclick = toggleMentor;

  const btnPrivado = document.getElementById('btnPrivado');
  if (btnPrivado) btnPrivado.onclick = togglePrivado;

  const btnLimpiar = document.getElementById('btnLimpiar');
  if (btnLimpiar) btnLimpiar.onclick = limpiarChat;

  cargarHistorial();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', registrarEventosMovil);
} else {
  registrarEventosMovil();
}
"""
