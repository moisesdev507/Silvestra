"""Módulo JavaScript auxiliar para el cliente HUD de la tablet."""

JS_CLIENTE_AUX = """
(function() {
  // Wake Lock API para evitar suspensión en tablet
  if ('wakeLock' in navigator) {
    navigator.wakeLock.request('screen').catch(function() {});
  }

  // Control de Pantalla Completa con alto contraste
  const btnFs = document.getElementById('btnFullscreen');
  function toggleFullscreen() {
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      const el = document.documentElement;
      if (el.requestFullscreen) el.requestFullscreen().catch(function() {});
      else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
      if (btnFs) btnFs.innerHTML = '🗗 SALIR';
    } else {
      if (document.exitFullscreen) document.exitFullscreen().catch(function() {});
      else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
      if (btnFs) btnFs.innerHTML = '⛶ PANTALLA COMPLETA';
    }
  }
  if (btnFs) btnFs.addEventListener('click', toggleFullscreen);
  document.addEventListener('fullscreenchange', function() {
    if (btnFs) {
      const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement);
      btnFs.innerHTML = isFs ? '🗗 SALIR' : '⛶ PANTALLA COMPLETA';
    }
  });

  // Acciones rápidas del panel HUD tablet
  let _accionPending = false;
  function _headers() {
    const h = { 'Content-Type': 'application/json' };
    if (window._hudToken) h['X-Device-Token'] = window._hudToken;
    return h;
  }

  window.ejecutarAccion = function(nombre) {
    if (_accionPending) return;
    const fb = document.getElementById('accionFb');
    _accionPending = true;
    if (fb) { fb.textContent = 'EJECUTANDO...'; fb.style.color = 'var(--gold)'; }
    fetch('/api/panel/accion', {
      method: 'POST',
      headers: _headers(),
      body: JSON.stringify({ accion: nombre })
    })
    .then(function(r) {
      const st = r.status;
      return r.json().then(function(d) { return { d: d, status: st }; });
    })
    .then(function(res) {
      const d = res.d;
      if (fb) {
        fb.textContent = d.ok ? ('✔ ' + nombre.toUpperCase()) : ('✖ ' + (d.error || 'Error'));
        fb.style.color = d.ok ? 'var(--green)' : '#f87171';
      }
      if (d.ok && window.marcarConectado) window.marcarConectado();
    })
    .catch(function() {
      if (fb) { fb.textContent = '✖ SIN CONEXIÓN'; fb.style.color = '#f87171'; }
    })
    .finally(function() {
      _accionPending = false;
      setTimeout(function() { if (fb) fb.textContent = ''; }, 3500);
    });
  };

  // Delegación de eventos en botones [data-accion]
  let _confirmPending = null;
  let _confirmTimer = null;
  document.querySelectorAll('[data-accion]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      const act = btn.getAttribute('data-accion') || '';
      const esCritica = btn.hasAttribute('data-confirm') ||
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
      window.ejecutarAccion(act);
    });
  });
})();
"""
