// Kaya Live PWA - Cliente Web con Audio Bidireccional y Visión
let ws = null;
let audioCtx = null;
let micStream = null;
let scriptNode = null;
let audioCola = [];
let audioReproduciendo = false;
let proximoTiempoPlay = 0;

let micMuteado = false;
let modoPaseoActivo = false;
let timerPaseo = null;
let facingMode = "environment"; // trasera por defecto en móvil

const badgeEstado = document.getElementById("badgeEstado");
const orbePulso = document.getElementById("orbePulso");
const orbeNucleo = document.getElementById("orbeNucleo");
const txtSubtitulo = document.getElementById("txtSubtitulo");
const btnOrbe = document.getElementById("btnOrbe");
const btnMute = document.getElementById("btnMute");
const iconMute = document.getElementById("iconMute");
const btnFoto = document.getElementById("btnFoto");
const btnPaseo = document.getElementById("btnPaseo");
const btnCamara = document.getElementById("btnCamara");
const btnDesconectar = document.getElementById("btnDesconectar");
const videoPreview = document.getElementById("videoPreview");
const canvasFrame = document.getElementById("canvasFrame");

const COLORES = {
  reposo: "#64748b",
  conectando: "#f59e0b",
  escuchando: "#06b6d4",
  pensando: "#f59e0b",
  hablando: "#10b981",
  error: "#ef4444"
};

function actualizarVisualEstado(estado) {
  const color = COLORES[estado] || COLORES.reposo;
  badgeEstado.textContent = estado.toUpperCase();
  badgeEstado.style.color = color;
  badgeEstado.style.borderColor = color;
  orbePulso.style.backgroundColor = color;
  orbeNucleo.style.background = `radial-gradient(circle at 35% 35%, #ffffff, ${color} 65%)`;
}

function animarVolumen(nivel) {
  const escala = 1 + Math.min(nivel * 1.3, 1.4);
  orbePulso.style.transform = `scale(${escala})`;
}

async function iniciarAudioContext() {
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    audioCtx = new AudioContextClass({ sampleRate: 24000 });
  }
  if (audioCtx.state === "suspended") {
    await audioCtx.resume();
  }
}

async function iniciarMicrofono() {
  await iniciarAudioContext();
  if (micStream) return;

  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
        sampleRate: 16000
      }
    });

    const micCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const fuente = micCtx.createMediaStreamSource(micStream);

    // Buffer de 1024 a 16kHz = ~64ms
    scriptNode = micCtx.createScriptProcessor(1024, 1, 1);
    scriptNode.onaudioprocess = (e) => {
      if (micMuteado || !ws || ws.readyState !== WebSocket.OPEN) return;
      const canalFloat = e.inputBuffer.getChannelData(0);
      const pcm16 = new Int16Array(canalFloat.length);
      for (let i = 0; i < canalFloat.length; i++) {
        const s = Math.max(-1, Math.min(1, canalFloat[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      ws.send(pcm16.buffer);
    };

    fuente.connect(scriptNode);
    scriptNode.connect(micCtx.destination);
  } catch (err) {
    console.error("Error al acceder al micrófono:", err);
    txtSubtitulo.textContent = "Permiso de micrófono requerido para hablar con Kaya.";
  }
}

function reproducirChunkPCM24(arrayBuffer) {
  if (!audioCtx) return;
  const int16 = new Int16Array(arrayBuffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768.0;
  }

  const audioBuf = audioCtx.createBuffer(1, float32.length, 24000);
  audioBuf.copyToChannel(float32, 0);

  const source = audioCtx.createBufferSource();
  source.buffer = audioBuf;
  source.connect(audioCtx.destination);

  const ahora = audioCtx.currentTime;
  if (proximoTiempoPlay < ahora) {
    proximoTiempoPlay = ahora;
  }
  source.start(proximoTiempoPlay);
  proximoTiempoPlay += audioBuf.duration;
}

function cortarAudioBargeIn() {
  if (audioCtx) {
    proximoTiempoPlay = audioCtx.currentTime;
  }
}

function conectarWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  actualizarVisualEstado("conectando");
  txtSubtitulo.textContent = "Conectando con Kaya Live...";

  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}/ws/live`;
  ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";

  ws.onopen = async () => {
    actualizarVisualEstado("escuchando");
    txtSubtitulo.textContent = "Kaya te escucha...";
    await iniciarMicrofono();
  };

  ws.onmessage = (event) => {
    if (typeof event.data === "string") {
      try {
        const msg = JSON.parse(event.data);
        if (msg.tipo === "estado") {
          actualizarVisualEstado(msg.estado);
        } else if (msg.tipo === "nivel") {
          animarVolumen(msg.nivel);
        } else if (msg.tipo === "texto") {
          if (msg.rol === "kaya") {
            txtSubtitulo.textContent = msg.texto;
          }
        } else if (msg.tipo === "interrupcion") {
          cortarAudioBargeIn();
        }
      } catch (e) {
        console.error("Error parseando JSON:", e);
      }
    } else {
      reproducirChunkPCM24(event.data);
    }
  };

  ws.onclose = () => {
    actualizarVisualEstado("reposo");
    txtSubtitulo.textContent = "Sesión cerrada. Toca el orbe para reconectar.";
  };

  ws.onerror = () => {
    actualizarVisualEstado("error");
    txtSubtitulo.textContent = "Error de conexión con el servidor.";
  };
}

async function iniciarCamara() {
  if (videoPreview.srcObject) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: facingMode, width: { ideal: 640 }, height: { ideal: 480 } }
    });
    videoPreview.srcObject = stream;
    await videoPreview.play();
  } catch (err) {
    console.error("Error iniciando cámara:", err);
  }
}

async function enviarFotoJPEG() {
  await iniciarCamara();
  if (!videoPreview.videoWidth) {
    setTimeout(enviarFotoJPEG, 300);
    return;
  }
  canvasFrame.width = videoPreview.videoWidth;
  canvasFrame.height = videoPreview.videoHeight;
  const ctx = canvasFrame.getContext("2d");
  ctx.drawImage(videoPreview, 0, 0);

  canvasFrame.toBlob((blob) => {
    if (blob && ws && ws.readyState === WebSocket.OPEN) {
      const reader = new FileReader();
      reader.onload = () => {
        const base64 = reader.result.split(",")[1];
        ws.send(JSON.stringify({ tipo: "imagen", jpeg: base64 }));
        txtSubtitulo.textContent = "👁️ Fotograma enviado a Kaya.";
      };
      reader.readAsDataURL(blob);
    }
  }, "image/jpeg", 0.75);
}

function togglePaseo() {
  modoPaseoActivo = !modoPaseoActivo;
  btnPaseo.classList.toggle("activo", modoPaseoActivo);
  if (modoPaseoActivo) {
    iniciarCamara().then(() => {
      enviarFotoJPEG();
      timerPaseo = setInterval(enviarFotoJPEG, 1000);
    });
  } else {
    clearInterval(timerPaseo);
  }
}

async function rotarCamara() {
  facingMode = facingMode === "environment" ? "user" : "environment";
  if (videoPreview.srcObject) {
    videoPreview.srcObject.getTracks().forEach((t) => t.stop());
    videoPreview.srcObject = null;
    await iniciarCamara();
  }
}

btnOrbe.addEventListener("click", () => {
  iniciarAudioContext();
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    conectarWebSocket();
  } else {
    ws.send(JSON.stringify({ tipo: "toggle" }));
  }
});

btnMute.addEventListener("click", () => {
  micMuteado = !micMuteado;
  btnMute.classList.toggle("activo", micMuteado);
  iconMute.textContent = micMuteado ? "🔇" : "🎤";
});

btnFoto.addEventListener("click", () => {
  enviarFotoJPEG();
});

btnPaseo.addEventListener("click", () => {
  togglePaseo();
});

btnCamara.addEventListener("click", () => {
  rotarCamara();
});

btnDesconectar.addEventListener("click", () => {
  if (ws) ws.close();
  if (timerPaseo) clearInterval(timerPaseo);
  if (videoPreview.srcObject) {
    videoPreview.srcObject.getTracks().forEach((t) => t.stop());
    videoPreview.srcObject = null;
  }
});
