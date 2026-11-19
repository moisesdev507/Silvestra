"""Fragmentos visuales (CSS, HTML y JS) del panel reloj de mesa para la tablet."""

CSS_PANEL = r"""
    #panel-info {
      position: absolute;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.6s ease;
      display: flex;
      flex-direction: column;
      gap: 16px;
      z-index: 85;
    }
    #panel-info.activo {
      opacity: 1;
      pointer-events: auto;
    }
    /* Orientación Horizontal (Landscape) */
    @media (orientation: landscape) {
      #panel-info {
        top: 50%;
        right: 5vw;
        transform: translateY(-50%);
        width: 48vw;
        max-width: 580px;
      }
    }
    /* Orientación Vertical (Portrait) */
    @media (orientation: portrait) {
      #panel-info {
        bottom: 5vh;
        left: 50%;
        transform: translateX(-50%);
        width: 88vw;
        max-width: 480px;
      }
    }
    #seccion-reloj {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    #reloj-hora {
      font-size: 4.6rem;
      font-weight: 800;
      line-height: 1.0;
      letter-spacing: -2px;
      color: #22d3ee;
      display: flex;
      align-items: baseline;
      gap: 8px;
      text-shadow: 0 0 24px rgba(34, 211, 238, 0.25);
    }
    #reloj-ampm {
      font-size: 1.5rem;
      font-weight: 600;
      color: #4fd1c5;
      letter-spacing: 0;
    }
    #reloj-fecha {
      font-size: 1.25rem;
      color: #cbd5e1;
      font-weight: 500;
      text-transform: capitalize;
    }
    .widget-grid {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .widget-card {
      background: rgba(23, 29, 44, 0.85);
      border: 1px solid rgba(79, 209, 197, 0.35);
      border-radius: 12px;
      padding: 10px 16px;
      backdrop-filter: blur(8px);
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
    }
    .widget-tit {
      font-size: 0.82rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: #94a3b8;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .widget-val {
      font-size: 1.05rem;
      color: #f8fafc;
      font-weight: 500;
    }
    .rec-item {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.95rem;
      color: #e2e8f0;
      padding: 3px 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    .rec-item:last-child {
      border-bottom: none;
    }
    .rec-hora {
      font-weight: 700;
      color: #ffd166;
      font-size: 0.9rem;
      min-width: 46px;
    }
    .rec-txt {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
    }
    #widget-saludo {
      font-style: italic;
      color: #e2e8f0;
      font-size: 0.95rem;
      line-height: 1.4;
      border-left: 3px solid #f472b6;
    }
    /* Brillo nocturno (10 PM a 6 AM) */
    body.nocturno {
      background: #030509 !important;
    }
    body.nocturno #canvas-cara {
      opacity: 0.48;
      filter: brightness(0.6) contrast(0.88);
    }
    body.nocturno #panel-info {
      opacity: 0.55;
    }
    body.nocturno #reloj-hora {
      color: #0e7490 !important;
      text-shadow: none !important;
    }
    body.nocturno .widget-card {
      background: rgba(13, 17, 26, 0.7);
      border-color: rgba(79, 209, 197, 0.15);
    }
"""

HTML_PANEL = r"""
  <div id="panel-info">
    <div id="seccion-reloj">
      <div id="reloj-hora"><span id="txt-hora">--:--</span> <span id="reloj-ampm">--</span></div>
      <div id="reloj-fecha">Cargando fecha...</div>
    </div>
    <div class="widget-grid">
      <div id="card-clima" class="widget-card" style="display:none;">
        <div class="widget-tit">🌤️ Clima</div>
        <div id="txt-clima" class="widget-val">--</div>
      </div>
      <div id="card-recordatorios" class="widget-card" style="display:none;">
        <div class="widget-tit">🔔 Próximos recordatorios</div>
        <div id="lista-recordatorios"></div>
      </div>
      <div id="card-saludo" class="widget-card" style="display:none;">
        <div class="widget-tit">💬 Mensaje de hoy</div>
        <div id="txt-saludo" class="widget-val"></div>
      </div>
    </div>
  </div>
"""

JS_PANEL = r"""
    const panelInfo = document.getElementById('panel-info');
    const txtHora = document.getElementById('txt-hora');
    const relojAmpm = document.getElementById('reloj-ampm');
    const relojFecha = document.getElementById('reloj-fecha');
    const cardClima = document.getElementById('card-clima');
    const txtClima = document.getElementById('txt-clima');
    const cardRecs = document.getElementById('card-recordatorios');
    const listaRecs = document.getElementById('lista-recordatorios');
    const cardSaludo = document.getElementById('card-saludo');
    const txtSaludo = document.getElementById('txt-saludo');

    let progresoReposo = 0.0;
    let ultimaActividad = performance.now() / 1000.0;
    let datosPanel = null;

    function registrarActividad() {
      ultimaActividad = performance.now() / 1000.0;
    }
    window.addEventListener('click', registrarActividad);
    window.addEventListener('touchstart', registrarActividad);

    function actualizarRelojLocal() {
      const ahora = new Date();
      let h = ahora.getHours();
      const m = ahora.getMinutes().toString().padStart(2, '0');
      const ampm = h >= 12 ? 'PM' : 'AM';
      h = h % 12 || 12;
      txtHora.textContent = `${h}:${m}`;
      relojAmpm.textContent = ampm;

      const dias = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
      const meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
      relojFecha.textContent = `${dias[ahora.getDay()]}, ${ahora.getDate()} de ${meses[ahora.getMonth()]}`;

      // Brillo nocturno automático si son entre 10 PM (22) y 6 AM
      const horaReal = ahora.getHours();
      const esNocheLocal = (horaReal >= 22 || horaReal < 6);
      document.body.classList.toggle('nocturno', esNocheLocal);
    }
    setInterval(actualizarRelojLocal, 1000);
    actualizarRelojLocal();

    function procesarDatosPanel(p) {
      if (!p) return;
      datosPanel = p;
      if (p.hora_12) txtHora.textContent = p.hora_12;
      if (p.ampm) relojAmpm.textContent = p.ampm;
      if (p.fecha) relojFecha.textContent = p.fecha;

      if (p.clima && p.clima.trim()) {
        txtClima.textContent = p.clima;
        cardClima.style.display = 'block';
      } else {
        cardClima.style.display = 'none';
      }

      if (!p.modo_privado && p.recordatorios && p.recordatorios.length > 0) {
        listaRecs.innerHTML = '';
        p.recordatorios.forEach(r => {
          const div = document.createElement('div');
          div.className = 'rec-item';
          div.innerHTML = `<span class="rec-hora">${r.hora}</span><span class="rec-txt">${r.texto}</span>`;
          listaRecs.appendChild(div);
        });
        cardRecs.style.display = 'block';
      } else {
        cardRecs.style.display = 'none';
      }

      if (p.saludo && p.saludo.trim()) {
        txtSaludo.textContent = `«${p.saludo}»`;
        cardSaludo.style.display = 'block';
      } else {
        cardSaludo.style.display = 'none';
      }

      if (p.es_noche !== undefined) {
        document.body.classList.toggle('nocturno', Boolean(p.es_noche));
      }
    }
"""
