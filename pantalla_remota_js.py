"""Lógica de cliente JavaScript para el HUD Jarvis de la tablet."""

JS_JARVIS = """
(function() {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token') || '';

  // 1. Wake Lock API para evitar suspensión de la pantalla
  if ('wakeLock' in navigator) {
    navigator.wakeLock.request('screen').catch(() => {});
  }

  // 2. Control de Pantalla Completa (1 toque)
  const btnFs = document.getElementById('btnFullscreen');
  function toggleFullscreen() {
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      const docEl = document.documentElement;
      if (docEl.requestFullscreen) {
        docEl.requestFullscreen().catch(() => {});
      } else if (docEl.webkitRequestFullscreen) {
        docEl.webkitRequestFullscreen();
      }
      if (btnFs) btnFs.innerHTML = '🗗 SALIR';
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
      if (btnFs) btnFs.innerHTML = '⛶ PANTALLA COMPLETA';
    }
  }

  if (btnFs) {
    btnFs.addEventListener('click', toggleFullscreen);
  }

  document.addEventListener('fullscreenchange', () => {
    if (btnFs) {
      const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement);
      btnFs.innerHTML = isFs ? '🗗 SALIR' : '⛶ PANTALLA COMPLETA';
    }
  });

  // 3. Canvas del Orbe Jarvis interactivo
  const canvas = document.getElementById('orbCanvas');
  const ctx = canvas.getContext('2d');
  let orbState = 'reposo';
  let orbVolume = 0.0;
  let angle = 0;

  function drawOrb() {
    const w = canvas.width, h = canvas.height, cx = w / 2, cy = h / 2;
    ctx.clearRect(0, 0, w, h);

    let primary = '#00f0ff', glow = 'rgba(0, 240, 255, 0.45)', speed = 0.015;
    if (orbState === 'escuchando') {
      primary = '#ffd166'; glow = 'rgba(255, 209, 102, 0.55)'; speed = 0.03;
    } else if (orbState === 'pensando') {
      primary = '#38bdf8'; glow = 'rgba(56, 189, 248, 0.7)'; speed = 0.055;
    } else if (orbState === 'hablando') {
      primary = '#10b981'; glow = 'rgba(16, 185, 129, 0.65)'; speed = 0.025;
    } else if (orbState === 'dormida') {
      primary = '#334155'; glow = 'rgba(51, 65, 85, 0.2)'; speed = 0.005;
    }

    // Núcleo central
    const baseR = 26 + (orbState === 'hablando' ? orbVolume * 18 : Math.sin(angle * 2.2) * 2.5);
    const grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, baseR);
    grad.addColorStop(0, '#ffffff');
    grad.addColorStop(0.38, primary);
    grad.addColorStop(1, 'transparent');
    ctx.beginPath();
    ctx.arc(cx, cy, baseR, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();

    // Anillo 1 (rotación horaria con arco interrumpido)
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.strokeStyle = primary;
    ctx.lineWidth = 2;
    ctx.shadowColor = glow;
    ctx.shadowBlur = 8;
    ctx.beginPath();
    ctx.arc(0, 0, 48, 0, Math.PI * 1.4);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, 48, Math.PI * 1.6, Math.PI * 1.9);
    ctx.stroke();
    ctx.restore();

    // Anillo 2 (rotación antihoraria segmentada)
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-angle * 1.4);
    ctx.strokeStyle = primary;
    ctx.lineWidth = 1.2;
    ctx.setLineDash([6, 9]);
    ctx.beginPath();
    ctx.arc(0, 0, 62, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    // Anillo 3 exterior con nodos
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle * 0.6);
    ctx.strokeStyle = glow;
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(0, 0, 75, 0, Math.PI * 2);
    ctx.stroke();

    for (let i = 0; i < 4; i++) {
      const th = (Math.PI / 2) * i;
      ctx.beginPath();
      ctx.arc(Math.cos(th) * 75, Math.sin(th) * 75, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = primary;
      ctx.fill();
    }
    ctx.restore();

    angle += speed;
    requestAnimationFrame(drawOrb);
  }
  requestAnimationFrame(drawOrb);

  // 4. Estados de conexión
  const connEl = document.getElementById('connStatus');
  function marcarConectado() {
    if (connEl) {
      connEl.textContent = 'EN LÍNEA';
      connEl.style.color = 'var(--green)';
    }
  }

  function marcarReconectando() {
    if (connEl) {
      connEl.textContent = 'RECONECTANDO';
      connEl.style.color = 'var(--gold)';
    }
  }

  // 5. Renderizado de datos del HUD
  function aplicarDatos(d) {
    if (!d) return;
    marcarConectado();

    // Telemetría
    if (d.telemetria) {
      const t = d.telemetria;
      document.getElementById('cpuVal').textContent = t.cpu + '%';
      document.getElementById('cpuBar').style.width = t.cpu + '%';
      document.getElementById('ramVal').textContent = t.ram + '%';
      document.getElementById('ramBar').style.width = t.ram + '%';

      if (t.bateria && t.bateria.disponible) {
        const acTxt = t.bateria.cargando ? ' (AC)' : '';
        document.getElementById('batVal').textContent = t.bateria.porcentaje + '%' + acTxt;
        document.getElementById('batBar').style.width = t.bateria.porcentaje + '%';
      } else {
        document.getElementById('batVal').textContent = 'AC Corriente';
        document.getElementById('batBar').style.width = '100%';
      }

      document.getElementById('micStateText').textContent = t.microfono || 'Activo';
      const isListen = t.escuchando;
      document.getElementById('micBadge').textContent = isListen ? 'ESCUCHANDO' : 'ACTIVO';
      document.getElementById('micBadge').style.color = isListen ? 'var(--gold)' : 'var(--green)';

      const modePill = document.getElementById('modePill');
      if (t.modo_privado) {
        modePill.textContent = 'MODO PRIVADO ACTIVO';
        modePill.className = 'mode-pill mode-privado';
      } else {
        modePill.textContent = 'MODO NORMAL';
        modePill.className = 'mode-pill mode-normal';
      }
    }

    // Estado Silvestra
    if (d.silvestra) {
      const s = d.silvestra;
      orbState = s.estado || 'reposo';
      orbVolume = s.volumen || 0;
      document.getElementById('orbStateBadge').textContent = orbState.toUpperCase();
      document.getElementById('volBar').style.width = Math.min(100, (orbVolume * 100)) + '%';

      if (s.subtitulo) {
        document.getElementById('streamSub').textContent = s.subtitulo;
      }
      if (s.tarjeta) {
        document.getElementById('dynamicCardText').textContent = s.tarjeta;
      }
    }

    // Biometría en vivo
    if (d.biometria && window.actualizarBiometria) {
      window.actualizarBiometria(d.biometria);
    }

    // Datos y listas
    if (d.datos) {
      const dt = d.datos;
      if (dt.clima) {
        document.getElementById('climaText').textContent = dt.clima;
      }
      if (dt.reloj) {
        document.getElementById('clockHours').textContent = dt.reloj.hora;
        document.getElementById('clockAmpm').textContent = dt.reloj.ampm;
        document.getElementById('clockDate').textContent = dt.reloj.fecha;
      }

      const esPrivado = d.telemetria && d.telemetria.modo_privado;

      // Recordatorios
      const recBox = document.getElementById('recsContainer');
      if (esPrivado) {
        recBox.innerHTML = '<div class="private-banner">🔒 MODO PRIVADO ACTIVO<br>Recordatorios protegidos</div>';
        document.getElementById('recsCount').textContent = 'OCULTO';
      } else if (dt.recordatorios && dt.recordatorios.length > 0) {
        document.getElementById('recsCount').textContent = dt.recordatorios.length;
        recBox.innerHTML = dt.recordatorios.map(r => '<div class="list-item"><div class="item-top"><span>HORA</span><span>' + r.hora + '</span></div><div class="item-text">' + r.texto + '</div></div>').join('');
      } else {
        document.getElementById('recsCount').textContent = '0';
        recBox.innerHTML = '<div style="font-size:11px; color:var(--text-muted)">Sin recordatorios pendientes.</div>';
      }

      // Notas
      const notesBox = document.getElementById('notesContainer');
      if (esPrivado) {
        notesBox.innerHTML = '<div class="private-banner">🔒 MODO PRIVADO ACTIVO<br>Notas protegidas</div>';
        document.getElementById('notesCount').textContent = 'OCULTO';
      } else if (dt.notas && dt.notas.length > 0) {
        document.getElementById('notesCount').textContent = dt.notas.length;
        notesBox.innerHTML = dt.notas.map(n => '<div class="list-item"><div class="item-top"><span>' + (n.materia||'General') + '</span><span>' + (n.fecha||'') + '</span></div><div class="item-text">' + n.texto + '</div></div>').join('');
      } else {
        document.getElementById('notesCount').textContent = '0';
        notesBox.innerHTML = '<div style="font-size:11px; color:var(--text-muted)">Sin notas recientes.</div>';
      }

      // Eventos
      if (dt.eventos && dt.eventos.length > 0) {
        document.getElementById('eventLog').innerHTML = dt.eventos.map(e => '<div class="log-entry">[' + e.hora + '] ' + e.texto + '</div>').join('');
      }
    }
  }

  // 6. Conexión Server-Sent Events con token seguro
  const sseUrl = `/eventos?token=${encodeURIComponent(token)}`;
  let evtSource = null;

  function iniciarSSE() {
    if (evtSource) {
      try { evtSource.close(); } catch(e) {}
    }
    evtSource = new EventSource(sseUrl);

    evtSource.onopen = function() {
      marcarConectado();
    };

    evtSource.onmessage = function(e) {
      try {
        aplicarDatos(JSON.parse(e.data));
      } catch(err) {}
    };

    evtSource.onerror = function() {
      // Intento de fallback inmediato por endpoint JSON
      fetch(`/api/panel/estado?token=${encodeURIComponent(token)}`)
        .then(r => r.json())
        .then(d => {
          aplicarDatos(d);
        })
        .catch(() => {
          marcarReconectando();
        });
    };
  }

  // Carga inicial inmediata por REST
  fetch(`/api/panel/estado?token=${encodeURIComponent(token)}`)
    .then(r => r.json())
    .then(d => aplicarDatos(d))
    .catch(() => {});

  iniciarSSE();

  // 7. Consola interactiva: enviar comando a Silvestra
  let _cmdPending = false;
  function enviarComando() {
    if (_cmdPending) return;
    const inp = document.getElementById('consoleInput');
    const fb  = document.getElementById('consoleFb');
    if (!inp) return;
    const texto = inp.value.trim();
    if (!texto) return;
    _cmdPending = true;
    if (fb) { fb.textContent = 'ENVIANDO...'; fb.style.color = 'var(--gold)'; }
    fetch('/api/panel/comando?token=' + encodeURIComponent(token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto: texto })
    })
    .then(function(r) {
      var status = r.status;
      return r.json().then(function(d) { return { d: d, status: status }; });
    })
    .then(function(res) {
      var d = res.d;
      if (fb) {
        fb.textContent = d.ok ? '✔ ENVIADO' : ('✖ HTTP ' + res.status + ' — ' + (d.error || 'Error'));
        fb.style.color  = d.ok ? 'var(--green)' : '#f87171';
      }
      if (d.ok && inp) inp.value = '';
    })
    .catch(function() { if (fb) { fb.textContent = '✖ SIN CONEXIÓN'; fb.style.color = '#f87171'; } })
    .finally(function() { _cmdPending = false; setTimeout(function() { if (fb) fb.textContent = ''; }, 3500); });
  }

  var ci = document.getElementById('consoleInput');
  if (ci) {
    ci.addEventListener('keydown', function(e) { if (e.key === 'Enter') { e.preventDefault(); enviarComando(); } });
  }
  var btnEnviar = document.getElementById('btnEnviar');
  if (btnEnviar) { btnEnviar.addEventListener('click', enviarComando); }

  // 8. Acciones rápidas de la tablet (delegación de eventos en action-grid)
  let _accionPending = false;
  function ejecutarAccion(nombre) {
    if (_accionPending) return;
    var fb = document.getElementById('accionFb');
    _accionPending = true;
    if (fb) { fb.textContent = 'EJECUTANDO...'; fb.style.color = 'var(--gold)'; }
    fetch('/api/panel/accion?token=' + encodeURIComponent(token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accion: nombre })
    })
    .then(function(r) {
      var status = r.status;
      return r.json().then(function(d) { return { d: d, status: status }; });
    })
    .then(function(res) {
      var d = res.d;
      if (fb) {
        fb.textContent = d.ok ? ('✔ ' + nombre.toUpperCase()) : ('✖ HTTP ' + res.status + ' — ' + (d.error || 'Error'));
        fb.style.color  = d.ok ? 'var(--green)' : '#f87171';
      }
    })
    .catch(function() { if (fb) { fb.textContent = '✖ SIN CONEXIÓN'; fb.style.color = '#f87171'; } })
    .finally(function() { _accionPending = false; setTimeout(function() { if (fb) fb.textContent = ''; }, 3500); });
  }

  // Delegación con blindaje de doble confirmación (3s) para acciones críticas
  var _confirmPending = null;
  var _confirmTimer = null;
  document.querySelectorAll('[data-accion]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var act = btn.getAttribute('data-accion') || '';
      var esCritica = btn.hasAttribute('data-confirm') ||
                      /reiniciar|renacer|despertar|apagar|suspender/.test(act);
      if (esCritica) {
        if (_confirmPending !== btn) {
          if (_confirmTimer) clearTimeout(_confirmTimer);
          if (_confirmPending) {
            _confirmPending.textContent = _confirmPending.getAttribute('data-orig-text') || _confirmPending.textContent;
            _confirmPending.style.borderColor = '';
            _confirmPending.style.color = '';
          }
          _confirmPending = btn;
          if (!btn.getAttribute('data-orig-text')) {
            btn.setAttribute('data-orig-text', btn.textContent);
          }
          btn.textContent = '¿Confirmar? (3s)';
          btn.style.borderColor = '#f87171';
          btn.style.color = '#f87171';
          _confirmTimer = setTimeout(function() {
            if (_confirmPending === btn) {
              btn.textContent = btn.getAttribute('data-orig-text') || btn.textContent;
              btn.style.borderColor = '';
              btn.style.color = '';
              _confirmPending = null;
            }
          }, 3000);
          return;
        } else {
          if (_confirmTimer) clearTimeout(_confirmTimer);
          btn.textContent = btn.getAttribute('data-orig-text') || btn.textContent;
          btn.style.borderColor = '';
          btn.style.color = '';
          _confirmPending = null;
        }
      }
      ejecutarAccion(act);
    });
  });

})();
"""
