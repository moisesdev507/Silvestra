"""Plantilla HTML y JavaScript interactivo para la interfaz Jarvis HUD de la tablet."""
from pantalla_remota_estilos import CSS_JARVIS

PAGINA_JARVIS_HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
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
        <span id="connStatus">ONLINE</span>
      </div>
      <div id="modePill" class="mode-pill mode-normal">MODO NORMAL</div>
    </div>
  </header>

  <main class="hud-grid">
    <!-- PANEL IZQUIERDO: TELEMETRÍA -->
    <section class="hud-panel">
      <div class="hud-card">
        <div class="card-header">
          <span class="card-title">TELEMETRÍA EN VIVO</span>
          <span style="font-size:10px; color:var(--cyan); font-family:var(--font-mono)">LAPTOP</span>
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
          <span id="micBadge" style="font-size:10px; color:var(--green); font-family:var(--font-mono)">ACTIVO</span>
        </div>
        <div class="metric-row">
          <div class="metric-label-val">
            <span>MICRÓFONO</span>
            <span id="micStateText" style="color:#fff; font-family:var(--font-mono)">En espera</span>
          </div>
          <div class="metric-bar-bg"><div id="volBar" class="metric-bar-fill" style="width:0%; background:var(--green); box-shadow:0 0 10px var(--green)"></div></div>
        </div>
        <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono)">VAD Adaptativo // Edge-TTS es-PA</div>
      </div>

      <div class="hud-card">
        <div class="card-header">
          <span class="card-title">CLIMA LOCAL</span>
          <span style="font-size:10px; color:var(--cyan); font-family:var(--font-mono)">PANAMÁ</span>
        </div>
        <div id="climaText" style="font-size:15px; font-weight:700; color:#fff">Consultando...</div>
      </div>
    </section>

    <!-- COLUMNA CENTRAL -->
    <section class="hud-center">
      <div class="orb-container">
        <canvas id="orbCanvas" width="240" height="240"></canvas>
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
      <div class="hud-card">
        <div class="card-header">
          <span class="card-title">RECORDATORIOS EN COLA</span>
          <span id="recsCount" style="font-size:10px; color:var(--cyan); font-family:var(--font-mono)">0</span>
        </div>
        <div id="recsContainer" class="item-list">
          <div style="font-size:12px; color:var(--text-muted)">Sin recordatorios pendientes.</div>
        </div>
      </div>

      <div class="hud-card">
        <div class="card-header">
          <span class="card-title">BANCO DE NOTAS</span>
          <span id="notesCount" style="font-size:10px; color:var(--cyan); font-family:var(--font-mono)">0</span>
        </div>
        <div id="notesContainer" class="item-list">
          <div style="font-size:12px; color:var(--text-muted)">Sin notas recientes.</div>
        </div>
      </div>

      <div class="hud-card" style="flex:1">
        <div class="card-header">
          <span class="card-title">REGISTRO DE OPERACIONES</span>
          <span style="font-size:10px; color:var(--cyan); font-family:var(--font-mono)">LOG</span>
        </div>
        <div id="eventLog" class="item-list" style="max-height:160px">
          <div class="log-entry">[00:00] Inicializando interfaz HUD...</div>
        </div>
      </div>
    </section>
  </main>

  <script>
  (function() {{
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token') || '';

    if ('wakeLock' in navigator) {{
      navigator.wakeLock.request('screen').catch(() => {{}});
    }}

    const canvas = document.getElementById('orbCanvas');
    const ctx = canvas.getContext('2d');
    let orbState = 'reposo';
    let orbVolume = 0.0;
    let angle = 0;

    function drawOrb() {{
      const w = canvas.width, h = canvas.height, cx = w / 2, cy = h / 2;
      ctx.clearRect(0, 0, w, h);

      let primary = '#00f0ff', glow = 'rgba(0, 240, 255, 0.4)', speed = 0.015;
      if (orbState === 'escuchando') {{
        primary = '#ffd166'; glow = 'rgba(255, 209, 102, 0.5)'; speed = 0.03;
      }} else if (orbState === 'pensando') {{
        primary = '#38bdf8'; glow = 'rgba(56, 189, 248, 0.7)'; speed = 0.06;
      }} else if (orbState === 'hablando') {{
        primary = '#10b981'; glow = 'rgba(16, 185, 129, 0.6)'; speed = 0.025;
      }} else if (orbState === 'dormida') {{
        primary = '#334155'; glow = 'rgba(51, 65, 85, 0.2)'; speed = 0.005;
      }}

      // Núcleo
      const baseR = 36 + (orbState === 'hablando' ? orbVolume * 22 : Math.sin(angle * 2) * 3);
      const grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, baseR);
      grad.addColorStop(0, '#ffffff');
      grad.addColorStop(0.35, primary);
      grad.addColorStop(1, 'transparent');
      ctx.beginPath();
      ctx.arc(cx, cy, baseR, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      // Anillo 1
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(angle);
      ctx.strokeStyle = primary;
      ctx.lineWidth = 2.5;
      ctx.shadowColor = glow;
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.arc(0, 0, 62, 0, Math.PI * 1.4);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(0, 0, 62, Math.PI * 1.6, Math.PI * 1.9);
      ctx.stroke();
      ctx.restore();

      // Anillo 2
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(-angle * 1.5);
      ctx.strokeStyle = primary;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([8, 12]);
      ctx.beginPath();
      ctx.arc(0, 0, 80, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // Anillo 3
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(angle * 0.7);
      ctx.strokeStyle = glow;
      ctx.lineWidth = 1;
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(0, 0, 98, 0, Math.PI * 2);
      ctx.stroke();

      for (let i = 0; i < 4; i++) {{
        const th = (Math.PI / 2) * i;
        ctx.beginPath();
        ctx.arc(Math.cos(th) * 98, Math.sin(th) * 98, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = primary;
        ctx.fill();
      }}
      ctx.restore();

      angle += speed;
      requestAnimationFrame(drawOrb);
    }}
    requestAnimationFrame(drawOrb);

    function aplicarDatos(d) {{
      if (!d) return;

      if (d.telemetria) {{
        const t = d.telemetria;
        document.getElementById('cpuVal').textContent = t.cpu + '%';
        document.getElementById('cpuBar').style.width = t.cpu + '%';
        document.getElementById('ramVal').textContent = t.ram + '%';
        document.getElementById('ramBar').style.width = t.ram + '%';

        if (t.bateria && t.bateria.disponible) {{
          const acTxt = t.bateria.cargando ? ' (AC)' : '';
          document.getElementById('batVal').textContent = t.bateria.porcentaje + '%' + acTxt;
          document.getElementById('batBar').style.width = t.bateria.porcentaje + '%';
        }} else {{
          document.getElementById('batVal').textContent = 'AC Corriente';
          document.getElementById('batBar').style.width = '100%';
        }}

        document.getElementById('micStateText').textContent = t.microfono || 'Activo';
        const isListen = t.escuchando;
        document.getElementById('micBadge').textContent = isListen ? 'ESCUCHANDO' : 'ACTIVO';
        document.getElementById('micBadge').style.color = isListen ? 'var(--gold)' : 'var(--green)';

        const modePill = document.getElementById('modePill');
        if (t.modo_privado) {{
          modePill.textContent = 'MODO PRIVADO ACTIVO';
          modePill.className = 'mode-pill mode-privado';
        }} else {{
          modePill.textContent = 'MODO NORMAL';
          modePill.className = 'mode-pill mode-normal';
        }}
      }}

      if (d.silvestra) {{
        const s = d.silvestra;
        orbState = s.estado || 'reposo';
        orbVolume = s.volumen || 0;
        document.getElementById('orbStateBadge').textContent = orbState.toUpperCase();
        document.getElementById('volBar').style.width = Math.min(100, (orbVolume * 100)) + '%';

        if (s.subtitulo) {{
          document.getElementById('streamSub').textContent = s.subtitulo;
        }}
        if (s.tarjeta) {{
          document.getElementById('dynamicCardText').textContent = s.tarjeta;
        }}
      }}

      if (d.datos) {{
        const dt = d.datos;
        if (dt.clima) document.getElementById('climaText').textContent = dt.clima;
        if (dt.reloj) {{
          document.getElementById('clockHours').textContent = dt.reloj.hora;
          document.getElementById('clockAmpm').textContent = dt.reloj.ampm;
          document.getElementById('clockDate').textContent = dt.reloj.fecha;
        }}

        const esPrivado = d.telemetria && d.telemetria.modo_privado;

        // Notas
        const notesBox = document.getElementById('notesContainer');
        if (esPrivado) {{
          notesBox.innerHTML = '<div class="private-banner">🔒 MODO PRIVADO ACTIVO<br>Notas protegidas</div>';
          document.getElementById('notesCount').textContent = 'OCULTO';
        }} else if (dt.notas && dt.notas.length > 0) {{
          document.getElementById('notesCount').textContent = dt.notas.length;
          notesBox.innerHTML = dt.notas.map(n => '<div class="list-item"><div class="item-top"><span>' + (n.materia||'General') + '</span><span>' + (n.fecha||'') + '</span></div><div class="item-text">' + n.texto + '</div></div>').join('');
        }} else {{
          document.getElementById('notesCount').textContent = '0';
          notesBox.innerHTML = '<div style="font-size:12px; color:var(--text-muted)">Sin notas recientes.</div>';
        }}

        // Recordatorios
        const recBox = document.getElementById('recsContainer');
        if (esPrivado) {{
          recBox.innerHTML = '<div class="private-banner">🔒 MODO PRIVADO ACTIVO<br>Recordatorios protegidos</div>';
          document.getElementById('recsCount').textContent = 'OCULTO';
        }} else if (dt.recordatorios && dt.recordatorios.length > 0) {{
          document.getElementById('recsCount').textContent = dt.recordatorios.length;
          recBox.innerHTML = dt.recordatorios.map(r => '<div class="list-item"><div class="item-top"><span>HORA</span><span>' + r.hora + '</span></div><div class="item-text">' + r.texto + '</div></div>').join('');
        }} else {{
          document.getElementById('recsCount').textContent = '0';
          recBox.innerHTML = '<div style="font-size:12px; color:var(--text-muted)">Sin recordatorios pendientes.</div>';
        }}

        // Eventos
        if (dt.eventos && dt.eventos.length > 0) {{
          document.getElementById('eventLog').innerHTML = dt.eventos.map(e => `
            <div class="log-entry">[${{e.hora}}] ${{e.texto}}</div>
          `).join('');
        }}
      }}
    }}

    const sseUrl = `/eventos?token=${{encodeURIComponent(token)}}`;
    let evtSource = null;

    function iniciarSSE() {{
      if (evtSource) {{
        try {{ evtSource.close(); }} catch(e) {{}}
      }}
      evtSource = new EventSource(sseUrl);

      evtSource.onopen = function() {{
        document.getElementById('connStatus').textContent = 'ONLINE';
        document.getElementById('connStatus').style.color = 'var(--green)';
      }};

      evtSource.onmessage = function(e) {{
        try {{
          aplicarDatos(JSON.parse(e.data));
        }} catch(err) {{}}
      }};

      evtSource.onerror = function() {{
        document.getElementById('connStatus').textContent = 'RECONECTANDO';
        document.getElementById('connStatus').style.color = 'var(--gold)';
        fetch(`/api/panel/estado?token=${{encodeURIComponent(token)}}`)
          .then(r => r.json())
          .then(d => aplicarDatos(d))
          .catch(() => {{}});
      }};
    }}

    iniciarSSE();
  }})();
  </script>
</body>
</html>
"""
