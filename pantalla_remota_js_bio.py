"""Lógica de cliente JavaScript para el panel biométrico del HUD Jarvis."""

JS_BIOMETRIA = """
(function() {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token') || '';

  let _soloDuenoPending = false;
  let _reforzarPending = false;

  window.actualizarBiometria = function(b) {
    if (!b) return;
    const bBadge = document.getElementById('bioBadge');
    if (bBadge) {
      if (b.identidad === 'dueno') {
        bBadge.textContent = 'DUEÑO';
        bBadge.className = 'bio-badge bio-dueno';
      } else if (b.identidad === 'invitado') {
        bBadge.textContent = 'INVITADO';
        bBadge.className = 'bio-badge bio-invitado';
      } else {
        bBadge.textContent = 'EN ESPERA';
        bBadge.className = 'bio-badge bio-espera';
      }
    }

    const vTxt = document.getElementById('bioVozText');
    if (vTxt) {
      const sim = (b.similitud_voz !== null && b.similitud_voz !== undefined) ? b.similitud_voz : '--';
      vTxt.textContent = 'Voz: ' + sim + ' · ' + (b.muestras_voz || 0) + ' mues';
    }

    const cTxt = document.getElementById('bioCaraText');
    if (cTxt) {
      let caraSt = 'OFF';
      if (b.camara_activa) {
        caraSt = b.camara_dueno ? 'OK' : 'ACTIVA';
      }
      cTxt.textContent = 'Cara: ' + caraSt + ' · ' + (b.muestras_cara || 0) + ' mues';
    }

    const btnSolo = document.getElementById('btnSoloDueno');
    if (btnSolo && !_soloDuenoPending) {
      if (b.solo_dueno) {
        btnSolo.textContent = 'Solo Dueño: ON';
        btnSolo.className = 'btn-bio bio-on';
      } else {
        btnSolo.textContent = 'Solo Dueño: OFF';
        btnSolo.className = 'btn-bio';
      }
    }
  };

  function toggleSoloDueno() {
    if (_soloDuenoPending) return;
    const btn = document.getElementById('btnSoloDueno');
    const fb = document.getElementById('bioFb');
    _soloDuenoPending = true;
    if (fb) { fb.textContent = 'CAMBIANDO...'; fb.style.color = 'var(--gold)'; }
    fetch('/api/panel/solo_dueno?token=' + encodeURIComponent(token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accion: 'toggle_solo_dueno' })
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.biometria) {
        window.actualizarBiometria(d.biometria);
      }
      if (fb) {
        fb.textContent = d.ok ? '✔ ACTUALIZADO' : '✖ ERROR';
        fb.style.color = d.ok ? 'var(--green)' : '#f87171';
      }
    })
    .catch(function() {
      if (fb) { fb.textContent = '✖ SIN CONEXIÓN'; fb.style.color = '#f87171'; }
    })
    .finally(function() {
      _soloDuenoPending = false;
      setTimeout(function() { if (fb) fb.textContent = ''; }, 3000);
    });
  }

  function solicitarReforzarVoz() {
    if (_reforzarPending) return;
    const btn = document.getElementById('btnReforzarVoz');
    const fb = document.getElementById('bioFb');
    _reforzarPending = true;
    if (btn) { btn.disabled = true; btn.textContent = 'Escuchando...'; }
    if (fb) { fb.textContent = 'SOLICITANDO...'; fb.style.color = 'var(--gold)'; }
    fetch('/api/panel/reforzar_voz?token=' + encodeURIComponent(token), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accion: 'reforzar_voz' })
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.biometria) {
        window.actualizarBiometria(d.biometria);
      }
      if (fb) {
        fb.textContent = d.ok ? '✔ SOLICITADO' : ('✖ ' + (d.mensaje || 'Espera'));
        fb.style.color = d.ok ? 'var(--green)' : 'var(--gold)';
      }
    })
    .catch(function() {
      if (fb) { fb.textContent = '✖ SIN CONEXIÓN'; fb.style.color = '#f87171'; }
    })
    .finally(function() {
      setTimeout(function() {
        _reforzarPending = false;
        if (btn) { btn.disabled = false; btn.textContent = 'Reforzar voz'; }
        if (fb) fb.textContent = '';
      }, 4000);
    });
  }

  const bSolo = document.getElementById('btnSoloDueno');
  if (bSolo) bSolo.addEventListener('click', toggleSoloDueno);
  const bRef = document.getElementById('btnReforzarVoz');
  if (bRef) bRef.addEventListener('click', solicitarReforzarVoz);

})();
"""
