"""Componentes visuales y scripts del panel Context Engine para el HUD de la tablet."""

HTML_CONTEXTO_PANEL = """
      <!-- PANEL CONTEXT ENGINE // 5 TARJETAS DE TELEMETRÍA SITUACIONAL -->
      <div class="hud-card contexto-card">
        <div class="card-header">
          <span class="card-title">CONTEXT ENGINE // SITUACIONAL</span>
          <span id="ctxFrescuraBadge" class="ctx-badge ctx-live">EN VIVO</span>
        </div>
        <div class="contexto-grid">
          <!-- 1. SISTEMA -->
          <div class="ctx-mini-card">
            <div class="ctx-title">// 1. SISTEMA</div>
            <div id="ctxApp" class="ctx-val" title="Aplicación en primer plano">--</div>
            <div id="ctxInact" class="ctx-sub">Inactividad: 0s</div>
          </div>
          <!-- 2. ACTIVIDAD -->
          <div class="ctx-mini-card">
            <div class="ctx-title">// 2. ACTIVIDAD</div>
            <div id="ctxAct" class="ctx-val" style="color:var(--gold)">--</div>
            <div style="display:flex; align-items:center; gap:4px; margin-top:2px">
              <span id="ctxCertezaBadge" class="ctx-badge ctx-prob">PROBABLE</span>
              <span id="ctxModo" class="ctx-sub">Modo: normal</span>
            </div>
          </div>
          <!-- 3. PRESENCIA -->
          <div class="ctx-mini-card">
            <div class="ctx-title">// 3. PRESENCIA</div>
            <div id="ctxPres" class="ctx-val">--</div>
            <div id="ctxPresSub" class="ctx-sub">Monitoreo facial</div>
          </div>
          <!-- 4. RECORDATORIOS -->
          <div class="ctx-mini-card">
            <div class="ctx-title">// 4. RECORDATORIOS</div>
            <div id="ctxRecsCount" class="ctx-val" style="color:var(--cyan)">0</div>
            <div id="ctxRecsProx" class="ctx-sub" title="Próximo recordatorio">Sin pendientes</div>
          </div>
          <!-- 5. ENLACE & TELEMETRÍA -->
          <div class="ctx-mini-card">
            <div class="ctx-title">// 5. ENLACE SSE</div>
            <div id="ctxEnlace" class="ctx-val" style="color:var(--green)">CONECTADO</div>
            <div id="ctxEdad" class="ctx-sub">Sync: 0s</div>
          </div>
        </div>
      </div>
"""

CSS_CONTEXTO_PANEL = """
/* Context Engine HUD Card & Grid */
.contexto-card {
  margin-top: 6px;
  padding: 8px 10px;
}
.contexto-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
}
@media (max-width: 900px) {
  .contexto-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (max-width: 600px) {
  .contexto-grid {
    grid-template-columns: 1fr;
  }
}
.ctx-mini-card {
  background: rgba(4, 9, 18, 0.75);
  border: 1px solid var(--border-dim);
  border-radius: 3px;
  padding: 5px 7px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 48px;
  overflow: hidden;
}
.ctx-title {
  font-size: 8.5px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.ctx-val {
  font-size: 11.5px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin: 1px 0;
}
.ctx-sub {
  font-size: 9px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ctx-badge {
  display: inline-block;
  font-size: 8px;
  font-family: var(--font-mono);
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 2px;
  letter-spacing: 0.5px;
}
.ctx-live {
  background: rgba(16, 185, 129, 0.2);
  border: 1px solid var(--green);
  color: var(--green);
}
.ctx-stale {
  background: rgba(239, 68, 68, 0.2);
  border: 1px solid #ef4444;
  color: #ef4444;
}
.ctx-det {
  background: rgba(0, 240, 255, 0.15);
  border: 1px solid var(--cyan);
  color: var(--cyan);
}
.ctx-prob {
  background: rgba(255, 209, 102, 0.15);
  border: 1px solid var(--gold);
  color: var(--gold);
}
.ctx-conf {
  background: rgba(16, 185, 129, 0.2);
  border: 1px solid var(--green);
  color: var(--green);
}
"""

JS_CONTEXTO_PANEL = """
// Context Engine Remote Telemetry Client Controller
(function() {
  let ultTsContexto = 0;
  let estadoEnlaceSSE = 'CONECTADO';

  function actualizarContexto(ctx) {
    if (!ctx) return;
    ultTsContexto = Date.now();

    // 1. Sistema
    const sis = ctx.sistema || {};
    const elApp = document.getElementById('ctxApp');
    if (elApp) elApp.textContent = sis.aplicacion || 'En reposo';
    const elInact = document.getElementById('ctxInact');
    if (elInact) elInact.textContent = 'Inact: ' + (sis.inactividad_seg || 0) + 's';

    // 2. Actividad y Certeza
    const act = ctx.actividad || {};
    const elAct = document.getElementById('ctxAct');
    if (elAct) elAct.textContent = (act.valor || 'desconocida').toUpperCase();

    const elCerteza = document.getElementById('ctxCertezaBadge');
    if (elCerteza) {
      const c = (act.certeza || 'PROBABLE').toUpperCase();
      elCerteza.textContent = c === 'PROBABLE' ? (act.certeza_detalle || 'PROBABLE') : c;
      elCerteza.className = 'ctx-badge ' + (c === 'CONFIRMADO' ? 'ctx-conf' : (c === 'DETECTADO' ? 'ctx-det' : 'ctx-prob'));
    }

    const elModo = document.getElementById('ctxModo');
    if (elModo) elModo.textContent = 'Modo: ' + (act.modo_etiqueta || act.modo || 'Normal');

    // 3. Presencia
    const pre = ctx.presencia || {};
    const elPres = document.getElementById('ctxPres');
    if (elPres) {
      const est = pre.estado || 'Inactiva';
      elPres.textContent = est.toUpperCase();
      elPres.style.color = est === 'Presente' ? 'var(--green)' : (est === 'Ausente' ? 'var(--gold)' : 'var(--text-muted)');
    }

    // 4. Recordatorios
    const rec = ctx.recordatorios || {};
    const elRecs = document.getElementById('ctxRecsCount');
    if (elRecs) elRecs.textContent = rec.total || 0;
    const elRecsProx = document.getElementById('ctxRecsProx');
    if (elRecsProx) elRecsProx.textContent = rec.proximo || 'Sin pendientes';

    // 5. Conexión & Frescura
    const con = ctx.conexion || {};
    const elBadge = document.getElementById('ctxFrescuraBadge');
    const elEdad = document.getElementById('ctxEdad');
    const esEnVivo = con.estado_actualizacion === 'en_vivo';

    if (elBadge) {
      elBadge.textContent = esEnVivo ? 'EN VIVO' : 'DESACTUALIZADO';
      elBadge.className = 'ctx-badge ' + (esEnVivo ? 'ctx-live' : 'ctx-stale');
    }
    if (elEdad) {
      elEdad.textContent = 'Sync: ' + (con.edad_seg || 0) + 's';
    }
  }

  // Watchdog local cada 1.5s para detectar desconexión o datos congelados (>15s)
  setInterval(function() {
    if (ultTsContexto > 0 && (Date.now() - ultTsContexto) > 15000) {
      const elBadge = document.getElementById('ctxFrescuraBadge');
      if (elBadge) {
        elBadge.textContent = 'DESACTUALIZADO';
        elBadge.className = 'ctx-badge ctx-stale';
      }
      const elEdad = document.getElementById('ctxEdad');
      if (elEdad) {
        const seg = Math.round((Date.now() - ultTsContexto) / 1000);
        elEdad.textContent = 'Sync: +' + seg + 's';
      }
    }
  }, 1500);

  window.actualizarContexto = actualizarContexto;
  window.fijarEstadoEnlaceContexto = function(est) {
    estadoEnlaceSSE = est;
    const el = document.getElementById('ctxEnlace');
    if (el) {
      el.textContent = est;
      el.style.color = est === 'CONECTADO' ? 'var(--green)' : (est === 'RECONECTANDO' ? 'var(--gold)' : '#ef4444');
    }
  };
})();
"""
