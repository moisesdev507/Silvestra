"""Tema visual holográfico Lyris y scripts de experiencia de usuario para tablet."""

CSS_TEMA_LYRIS = """
/* === TEMA HOLOGRÁFICO LYRIS // GALAXY TAB A7 === */
:root {
  --cyan-glow: rgba(0, 240, 255, 0.4);
  --cyan-border: rgba(0, 240, 255, 0.22);
  --bg-card-holo: rgba(8, 14, 28, 0.72);
  --green-glow: rgba(16, 185, 129, 0.35);
  --amber-glow: rgba(245, 158, 11, 0.4);
}

.hud-header {
  background: linear-gradient(180deg, rgba(5, 12, 24, 0.95) 0%, rgba(4, 8, 18, 0.8) 100%);
  border-bottom: 1px solid var(--cyan-border);
  box-shadow: 0 2px 20px rgba(0, 240, 255, 0.08);
}

.brand-title {
  color: #00f0ff !important;
  letter-spacing: 2.5px;
  text-shadow: 0 0 12px rgba(0, 240, 255, 0.6);
  font-weight: 800;
}

.brand-badge {
  background: rgba(0, 240, 255, 0.12);
  border: 1px solid rgba(0, 240, 255, 0.3);
  color: #00f0ff;
  border-radius: 4px;
}

.hud-card {
  background: var(--bg-card-holo) !important;
  border: 1px solid var(--cyan-border) !important;
  border-radius: 10px !important;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.45), inset 0 0 12px rgba(0, 240, 255, 0.04) !important;
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
}

.hud-card:hover {
  border-color: rgba(0, 240, 255, 0.45) !important;
  box-shadow: 0 6px 28px rgba(0, 240, 255, 0.12), inset 0 0 16px rgba(0, 240, 255, 0.08) !important;
}

.metric-bar-bg {
  background: rgba(15, 23, 42, 0.8) !important;
  border: 1px solid rgba(255, 255, 255, 0.08);
  height: 9px !important;
  border-radius: 5px !important;
  overflow: hidden;
}

.metric-bar-fill {
  height: 100%;
  border-radius: 5px;
  transition: width 0.45s cubic-bezier(0.4, 0, 0.2, 1) !important;
  box-shadow: 0 0 10px var(--cyan-glow);
}

/* Esfera de energía holográfica central */
.orb-container {
  background: radial-gradient(circle at center, rgba(0, 240, 255, 0.12) 0%, rgba(8, 20, 38, 0.5) 60%, transparent 100%) !important;
  border: 1px solid rgba(0, 240, 255, 0.25) !important;
  border-radius: 50% !important;
  padding: 16px !important;
  box-shadow: 0 0 40px rgba(0, 240, 255, 0.18), inset 0 0 30px rgba(0, 240, 255, 0.08) !important;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
}

.orb-container::before {
  content: "";
  position: absolute;
  top: -6px; left: -6px; right: -6px; bottom: -6px;
  border-radius: 50%;
  border: 1px dashed rgba(0, 240, 255, 0.2);
  pointer-events: none;
  animation: orbOrbit 30s linear infinite;
}

@keyframes orbOrbit {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Botones y controles táctiles >= 48px para Galaxy Tab A7 */
.btn-action, .btn-bio, .btn-hud, .console-send {
  min-height: 48px !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  border-radius: 8px !important;
  cursor: pointer;
  touch-action: manipulation;
  transition: all 0.2s ease-in-out;
}

.btn-mode {
  min-height: 44px !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  border-radius: 6px !important;
  touch-action: manipulation;
}

.btn-action:active, .btn-bio:active, .btn-hud:active, .btn-mode:active {
  transform: scale(0.96);
  filter: brightness(1.2);
}

.clock-digits {
  font-family: var(--font-mono);
  letter-spacing: 3px;
  text-shadow: 0 0 20px rgba(0, 240, 255, 0.5);
}

.date-string {
  color: #94a3b8;
  font-size: 12px;
  letter-spacing: 1px;
}

.stream-box, .console-box {
  background: var(--bg-card-holo) !important;
  border: 1px solid var(--cyan-border) !important;
  border-radius: 10px !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4) !important;
}

.console-input {
  min-height: 48px !important;
  font-size: 14px !important;
  border-radius: 8px 0 0 8px !important;
}
"""

JS_TEMA_LYRIS = """
<script>
(function() {
  // 1. Reloj y fecha local instantáneos en arranque/conexión
  function tickRelojLocal() {
    var ahora = new Date();
    var h = ahora.getHours();
    var m = ahora.getMinutes();
    var h12 = h % 12 || 12;
    var ampm = h >= 12 ? 'PM' : 'AM';
    var txtH = (h12 < 10 ? '0' : '') + h12 + ':' + (m < 10 ? '0' : '') + m;
    var elH = document.getElementById('clockHours');
    var elAmpm = document.getElementById('clockAmpm');
    var elDate = document.getElementById('clockDate');
    if (elH && (!elH.dataset.servidor || elH.innerText === '12:00')) elH.innerText = txtH;
    if (elAmpm && (!elAmpm.dataset.servidor || elAmpm.innerText === 'PM')) elAmpm.innerText = ampm;
    if (elDate && (!elDate.dataset.servidor || elDate.innerText.indexOf('Cargando') !== -1)) {
      var dias = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
      var meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                   'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
      elDate.innerText = dias[ahora.getDay()] + ', ' + ahora.getDate() + ' de ' + meses[ahora.getMonth()] + ' de ' + ahora.getFullYear();
    }
  }
  tickRelojLocal();
  setInterval(tickRelojLocal, 1000);

  // 2. Transición suave de barras de telemetría
  window.addEventListener('load', function() {
    tickRelojLocal();
  });
})();
</script>
"""
