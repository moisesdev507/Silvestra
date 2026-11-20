"""Plantilla HTML estructurada para la interfaz Jarvis HUD de la tablet."""
from pantalla_remota_estilos import CSS_JARVIS
from pantalla_remota_js import JS_JARVIS

PAGINA_JARVIS_HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="theme-color" content="#050811">
  <title>SILVESTRA // JARVIS HUD</title>
  <style>
{CSS_JARVIS}
  </style>
</head>
<body>
  <header class="hud-header">
    <div class="brand">
      <div class="brand-title">SILVESTRA // JARVIS HUD</div>
      <div class="brand-badge">SYSTEM V2.0</div>
    </div>
    <div class="header-status">
      <div class="live-indicator">
        <div class="pulse-dot"></div>
        <span id="connStatus">CONECTANDO...</span>
      </div>
      <div id="modePill" class="mode-pill mode-normal">MODO NORMAL</div>
      <button id="btnFullscreen" class="btn-hud" title="Alternar Pantalla Completa">
        ⛶ PANTALLA COMPLETA
      </button>
    </div>
  </header>

  <main class="hud-grid">
    <!-- PANEL IZQUIERDO: TELEMETRÍA, VOZ Y CLIMA -->
    <section class="hud-panel">
      <div class="hud-card">
        <div class="card-header">
          <span class="card-title">TELEMETRÍA EN VIVO</span>
          <span style="font-size:9px; color:var(--cyan); font-family:var(--font-mono)">LAPTOP</span>
        </div>
        <div class="metric-row">
          <div class="metric-label-val">
            <span>PROCESADOR CPU</span>
            <span id="cpuVal" style="color:var(--cyan); font-family:var(--font-mono)">0%</span>
          </div>
          <div class="metric-bar-bg"><div id="cpuBar" class="metric-bar-fill" style="width:0%"></div></div>
        </div>
        <div class="metric-row">
          <div class="metric-label-val">
            <span>MEMORIA RAM</span>
            <span id="ramVal" style="color:var(--cyan); font-family:var(--font-mono)">0%</span>
          </div>
          <div class="metric-bar-bg"><div id="ramBar" class="metric-bar-fill" style="width:0%"></div></div>
        </div>
        <div class="metric-row" style="margin-bottom:0">
          <div class="metric-label-val">
            <span>BATERÍA LAPTOP</span>
            <span id="batVal" style="color:var(--gold); font-family:var(--font-mono)">--</span>
          </div>
          <div class="metric-bar-bg"><div id="batBar" class="metric-bar-fill" style="width:100%; background:linear-gradient(90deg, #d97706, var(--gold))"></div></div>
        </div>
      </div>

      <div class="hud-card">
        <div class="card-header">
          <span class="card-title">SISTEMA DE VOZ</span>
          <span id="micBadge" style="font-size:9px; color:var(--green); font-family:var(--font-mono)">ACTIVO</span>
        </div>
        <div class="metric-row">
          <div class="metric-label-val">
            <span>MICRÓFONO</span>
            <span id="micStateText" style="color:#fff; font-family:var(--font-mono)">En espera</span>
          </div>
          <div class="metric-bar-bg"><div id="volBar" class="metric-bar-fill" style="width:0%; background:var(--green); box-shadow:0 0 8px var(--green)"></div></div>
        </div>
        <div style="font-size:10px; color:var(--text-muted); font-family:var(--font-mono)">VAD Adaptativo // Edge-TTS es-PA</div>
      </div>

      <div class="hud-card" style="flex:1; display:flex; flex-direction:column; justify-content:center">
        <div class="card-header" style="margin-bottom:3px">
          <span class="card-title">CONDICIÓN CLIMÁTICA</span>
          <span style="font-size:9px; color:var(--cyan); font-family:var(--font-mono)">PANAMÁ</span>
        </div>
        <div id="climaText" style="font-size:13px; font-weight:700; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">
          Consultando...
        </div>
      </div>
    </section>

    <!-- COLUMNA CENTRAL: ORBE, RELOJ, SUBTÍTULO Y TARJETA -->
    <section class="hud-center">
      <div class="orb-container">
        <canvas id="orbCanvas" width="170" height="170"></canvas>
        <div id="orbStateBadge" class="state-badge">REPOSO</div>
      </div>

      <div class="clock-section">
        <div class="clock-digits"><span id="clockHours">12:00</span><span id="clockAmpm" class="clock-ampm">PM</span></div>
        <div id="clockDate" class="date-string">Cargando fecha...</div>
      </div>

      <div class="stream-box">
        <div class="stream-label">// ÚLTIMA TRANSMISIÓN DE VOZ</div>
        <div id="streamSub" class="stream-text">Sistema en línea. Esperando órdenes.</div>
      </div>

      <div class="dynamic-card">
        <div class="dynamic-card-title">PROYECCIÓN // TARJETA PRINCIPAL</div>
        <div id="dynamicCardText" class="dynamic-card-body">SILVESTRA VIRTUAL INTERFACE // SISTEMA OPERATIVO</div>
      </div>
    </section>

    <!-- PANEL DERECHO: RECORDATORIOS, NOTAS Y EVENTOS -->
    <section class="hud-panel">
      <div class="hud-card flex-card">
        <div class="card-header">
          <span class="card-title">RECORDATORIOS EN COLA</span>
          <span id="recsCount" style="font-size:9px; color:var(--cyan); font-family:var(--font-mono)">0</span>
        </div>
        <div id="recsContainer" class="item-list">
          <div style="font-size:11px; color:var(--text-muted)">Sin recordatorios pendientes.</div>
        </div>
      </div>

      <div class="hud-card flex-card">
        <div class="card-header">
          <span class="card-title">BANCO DE NOTAS</span>
          <span id="notesCount" style="font-size:9px; color:var(--cyan); font-family:var(--font-mono)">0</span>
        </div>
        <div id="notesContainer" class="item-list">
          <div style="font-size:11px; color:var(--text-muted)">Sin notas recientes.</div>
        </div>
      </div>

      <div class="hud-card flex-card">
        <div class="card-header">
          <span class="card-title">REGISTRO DE OPERACIONES</span>
          <span style="font-size:9px; color:var(--cyan); font-family:var(--font-mono)">LOG</span>
        </div>
        <div id="eventLog" class="item-list">
          <div class="log-entry">[00:00] Inicializando interfaz HUD...</div>
        </div>
      </div>
    </section>
  </main>

  <script>
{JS_JARVIS}
  </script>
</body>
</html>
"""
