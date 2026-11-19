"""Plantilla web HTML+CSS+JS para visualización remota de Silvestra."""

from pantalla_remota_web2 import CSS_PANEL, HTML_PANEL, JS_PANEL

_BASE_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>Silvestra</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; user-select: none; }
    body, html { width: 100%; height: 100%; overflow: hidden; background: #0d1117; display: flex; justify-content: center; align-items: center; font-family: 'Segoe UI', system-ui, sans-serif; transition: background 0.8s; }
    #canvas-cara { width: 100vw; height: 100vh; display: block; touch-action: none; transition: opacity 0.8s, filter 0.8s; }
    #btn-fullscreen { position: absolute; top: 16px; right: 16px; width: 44px; height: 44px; border-radius: 50%; background: rgba(27,35,51,0.75); border: 1px solid rgba(79,209,197,0.4); color: #4fd1c5; font-size: 20px; display: flex; align-items: center; justify-content: center; cursor: pointer; backdrop-filter: blur(8px); z-index: 100; }
    #badge-estado { position: absolute; top: 16px; left: 16px; padding: 6px 14px; border-radius: 20px; background: rgba(27,35,51,0.75); border: 1px solid rgba(79,209,197,0.3); color: #a0aec0; font-size: 13px; z-index: 90; display: flex; align-items: center; gap: 6px; }
    #punto-estado { width: 8px; height: 8px; border-radius: 50%; background: #4fd1c5; box-shadow: 0 0 8px #4fd1c5; }
    #subtitulo-box { position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%) translateY(10px); width: 90%; max-width: 660px; background: rgba(23,29,44,0.88); border: 2px solid #4fd1c5; border-radius: 14px; padding: 12px 20px; color: #fff; font-size: 1.15rem; line-height: 1.45; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); transition: opacity 0.3s, transform 0.3s; pointer-events: none; opacity: 0; z-index: 95; }
    #subtitulo-box.activo { opacity: 1; transform: translateX(-50%) translateY(0); }
    /*CSS_PANEL*/
  </style>
</head>
<body>
  <div id="badge-estado"><div id="punto-estado"></div><span id="txt-estado">En reposo</span></div>
  <button id="btn-fullscreen" title="Pantalla completa">⛶</button>
  <canvas id="canvas-cara"></canvas>
  <!--HTML_PANEL-->
  <div id="subtitulo-box"><span id="txt-subtitulo"></span></div>

  <script>
    const canvas = document.getElementById('canvas-cara'), ctx = canvas.getContext('2d');
    const badgeEstado = document.getElementById('txt-estado'), puntoEstado = document.getElementById('punto-estado');
    const subtituloBox = document.getElementById('subtitulo-box'), txtSubtitulo = document.getElementById('txt-subtitulo');
    const btnFullscreen = document.getElementById('btn-fullscreen');
    const token = new URLSearchParams(window.location.search).get('token') || '';

    const PERFILES_EMOCION = {
      neutral:    { cejas_y: 0.0,  cejas_ang: 0.0,  ojos_ap: 1.00, boca_curva: 1.0,  boca_ancho: 28.0, rubor: 90.0,  color: [79, 209, 197] },
      alegre:     { cejas_y: -3.5, cejas_ang: 2.5,  ojos_ap: 1.06, boca_curva: 1.5,  boca_ancho: 34.0, rubor: 140.0, color: [52, 211, 153] },
      animada:    { cejas_y: -6.0, cejas_ang: 3.5,  ojos_ap: 1.15, boca_curva: 1.8,  boca_ancho: 36.0, rubor: 160.0, color: [251, 191, 36] },
      calida:     { cejas_y: -2.0, cejas_ang: 1.5,  ojos_ap: 0.96, boca_curva: 1.2,  boca_ancho: 30.0, rubor: 140.0, color: [244, 114, 182] },
      seria:      { cejas_y: 2.5,  cejas_ang: -3.5, ojos_ap: 0.84, boca_curva: 0.1,  boca_ancho: 22.0, rubor: 55.0,  color: [96, 165, 250] },
      preocupada: { cejas_y: -4.5, cejas_ang: 5.5,  ojos_ap: 1.08, boca_curva: -0.3, boca_ancho: 24.0, rubor: 80.0,  color: [167, 139, 250] }
    };

    const AMARILLO = [255, 209, 102], GRIS = [120, 132, 160];
    let vivo = { estado: 'reposo', emocion: 'neutral', volumen: 0.0, subtitulo: '' };
    let val_cejas_y = 0.0, val_cejas_ang = 0.0, val_ojos_ap = 1.0, val_boca_curva = 1.0;
    let val_boca_ancho = 28.0, val_rubor = 90.0, val_color = [79, 209, 197];
    let boca_abre = 0.0, ojo_x = 0.0, ojo_y = 0.0;
    let t0 = performance.now() / 1000.0, prox_parpadeo = t0 + 2.0, parpadeo_ini = null;
    let micro_sac_x = 0.0, micro_sac_y = 0.0, prox_micro_sac = t0 + 3.0;

    function redimensionar() {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr; canvas.height = window.innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    window.addEventListener('resize', redimensionar);
    redimensionar();

    async function solicitarWakeLock() {
      if ('wakeLock' in navigator) {
        try { await navigator.wakeLock.request('screen'); } catch (e) {}
      }
    }
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') solicitarWakeLock(); });
    window.addEventListener('click', solicitarWakeLock, { once: true });
    window.addEventListener('touchstart', solicitarWakeLock, { once: true });
    solicitarWakeLock();

    btnFullscreen.addEventListener('click', () => {
      if (!document.fullscreenElement) { document.documentElement.requestFullscreen().catch(() => {}); btnFullscreen.textContent = '✕'; }
      else { document.exitFullscreen().catch(() => {}); btnFullscreen.textContent = '⛶'; }
    });

    /*JS_PANEL*/

    function conectarEventos() {
      if (!token) return;
      const es = new EventSource('/eventos?token=' + encodeURIComponent(token));
      es.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          vivo.estado = d.estado || 'reposo';
          vivo.emocion = d.emocion || 'neutral';
          vivo.volumen = parseFloat(d.volumen || 0.0);
          vivo.subtitulo = d.subtitulo || '';

          if (vivo.subtitulo && vivo.subtitulo.trim()) {
            txtSubtitulo.textContent = vivo.subtitulo; subtituloBox.classList.add('activo');
          } else {
            subtituloBox.classList.remove('activo');
          }

          if (d.panel) procesarDatosPanel(d.panel);

          const etiquetas = { reposo: 'En reposo', hablando: 'Hablando...', escuchando: 'Escuchando...', pensando: 'Pensando...', dormida: 'Descansando' };
          badgeEstado.textContent = etiquetas[vivo.estado] || 'En línea';
          puntoEstado.style.background = vivo.estado === 'dormida' ? '#7884a0' : (vivo.estado === 'escuchando' ? '#ffd166' : '#4fd1c5');
          puntoEstado.style.boxShadow = '0 0 8px ' + puntoEstado.style.background;
        } catch (err) {}
      };
      es.onerror = () => { badgeEstado.textContent = 'Reconectando...'; puntoEstado.style.background = '#e53e3e'; };
    }
    conectarEventos();

    function animar() {
      const ahora = performance.now() / 1000.0, t = ahora - t0;
      const w = window.innerWidth, h = window.innerHeight;
      ctx.clearRect(0, 0, w, h);

      const perfil = PERFILES_EMOCION[vivo.emocion] || PERFILES_EMOCION.neutral;
      const factor = 0.16;
      val_cejas_y += (perfil.cejas_y - val_cejas_y) * factor;
      val_cejas_ang += (perfil.cejas_ang - val_cejas_ang) * factor;
      val_ojos_ap += (perfil.ojos_ap - val_ojos_ap) * factor;
      val_boca_curva += (perfil.boca_curva - val_boca_curva) * factor;
      val_boca_ancho += (perfil.boca_ancho - val_boca_ancho) * factor;
      val_rubor += (perfil.rubor - val_rubor) * factor;
      for (let i = 0; i < 3; i++) val_color[i] += (perfil.color[i] - val_color[i]) * factor;

      let color_final = [Math.round(val_color[0]), Math.round(val_color[1]), Math.round(val_color[2])];
      if (vivo.estado === 'dormida') color_final = GRIS;
      else if (vivo.estado === 'escuchando') color_final = AMARILLO;

      const hablando = (vivo.estado === 'hablando'), escuchando = (vivo.estado === 'escuchando'), pensando = (vivo.estado === 'pensando');

      if (hablando || escuchando) ultimaActividad = ahora;
      const enReposo = (ahora - ultimaActividad >= 20.0);
      const targetReposo = (enReposo && !hablando && !escuchando) ? 1.0 : 0.0;
      progresoReposo += (targetReposo - progresoReposo) * 0.08;

      if (progresoReposo > 0.1) {
        panelInfo.classList.add('activo'); panelInfo.style.opacity = Math.min(1.0, (progresoReposo - 0.1) / 0.9);
      } else {
        panelInfo.classList.remove('activo'); panelInfo.style.opacity = 0;
      }

      const escBase = Math.min(w, h) / 320.0;
      let cx = w / 2.0, cy = h / 2.0, escCara = escBase;
      if (w > h) {
        cx = (w / 2.0) * (1.0 - progresoReposo) + (w * 0.28) * progresoReposo;
        escCara = escBase * (1.0 - progresoReposo * 0.32);
      } else {
        cy = (h / 2.0) * (1.0 - progresoReposo) + (h * 0.26) * progresoReposo;
        escCara = escBase * (1.0 - progresoReposo * 0.30);
      }

      let inclinacion = 0.0, y_resp = 0.0, resp_escala = escCara;
      if (!hablando && vivo.estado !== 'dormida') {
        inclinacion = 1.2 * Math.sin(t * 0.7) * Math.sin(t * 0.25);
        y_resp = 3.5 * Math.sin(t * 1.2) * escCara;
        resp_escala = escCara * (1 + 0.012 * Math.sin(t * 1.6));
      } else {
        y_resp = 4.0 * Math.sin(t * 1.1) * escCara;
        resp_escala = escCara * (1 + 0.015 * Math.sin(t * 1.6));
      }

      ctx.save();
      ctx.translate(cx, cy + y_resp);
      ctx.scale(resp_escala, resp_escala);
      if (inclinacion) ctx.rotate((inclinacion * Math.PI) / 180.0);

      // Resplandor
      const gGlow = ctx.createRadialGradient(0, 0, 0, 0, 0, 135);
      gGlow.addColorStop(0.55, `rgba(${color_final.join(',')}, 0.24)`);
      gGlow.addColorStop(1.0, `rgba(${color_final.join(',')}, 0)`);
      ctx.fillStyle = gGlow;
      ctx.beginPath(); ctx.arc(0, 0, 135, 0, Math.PI * 2); ctx.fill();

      // Anillos giratorios
      const vel = pensando ? 160 : (hablando ? 70 : 40);
      const pulso = 0.5 + 0.5 * Math.sin(t * (hablando ? 9 : 2.2));
      const anillos = [
        { radio: 118, grosor: 3.0, sentido: 1.0, largo: 110 },
        { radio: 106, grosor: 2.2, sentido: -1.4, largo: 70 },
        { radio: 128, grosor: 1.6, sentido: 0.7, largo: 50 }
      ];
      anillos.forEach(an => {
        ctx.strokeStyle = `rgba(${color_final.join(',')}, ${(140 + 90 * pulso) / 255.0})`;
        ctx.lineWidth = an.grosor; ctx.lineCap = 'round';
        const ini = ((t * vel * an.sentido) % 360) * Math.PI / 180.0;
        const largoRad = (an.largo * Math.PI) / 180.0;
        for (let k = 0; k < 3; k++) {
          const a0 = ini + (k * 120 * Math.PI) / 180.0;
          ctx.beginPath(); ctx.arc(0, 0, an.radio, a0, a0 + largoRad); ctx.stroke();
        }
      });

      // Cabeza
      const gHead = ctx.createRadialGradient(-25, -35, 0, -25, -35, 120);
      gHead.addColorStop(0.0, '#ffffff'); gHead.addColorStop(0.6, '#e2f4f6'); gHead.addColorStop(1.0, '#a0d7dc');
      ctx.fillStyle = gHead; ctx.strokeStyle = `rgba(${color_final.join(',')}, 0.78)`; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.ellipse(0, 0, 92, 88, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();

      // Lacito
      ctx.save(); ctx.translate(-52, -74); ctx.rotate((-25 * Math.PI) / 180.0);
      ctx.strokeStyle = '#d65a7d'; ctx.lineWidth = 2; ctx.fillStyle = '#ff8caa';
      ctx.beginPath(); ctx.ellipse(-11, 0, 12, 8, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.ellipse(11, 0, 12, 8, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#ff6996';
      ctx.beginPath(); ctx.ellipse(0, 0, 6, 6, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.restore();

      // Mirada sacadica
      if (ahora >= prox_micro_sac) {
        micro_sac_x = (Math.random() - 0.5) * 3.6; micro_sac_y = (Math.random() - 0.5) * 2.4;
        prox_micro_sac = ahora + 2.5 + Math.random() * 2.5;
      }
      let tDx = micro_sac_x, tDy = micro_sac_y;
      if (pensando) { tDx = 3.5 * Math.sin(t * 2); tDy = -4.0; }
      ojo_x += (tDx - ojo_x) * 0.15; ojo_y += (tDy - ojo_y) * 0.15;

      // Parpadeo
      if (parpadeo_ini === null && ahora >= prox_parpadeo) parpadeo_ini = ahora;
      let cierre = 0.0;
      if (parpadeo_ini !== null) {
        const f = (ahora - parpadeo_ini) / 0.17;
        if (f >= 1.0) {
          parpadeo_ini = null;
          prox_parpadeo = ahora + (Math.random() < 0.18 ? 0.25 : 3.0 + Math.random() * 3.0);
        } else cierre = Math.sin(f * Math.PI);
      }
      if (vivo.estado === 'dormida') cierre = Math.max(cierre, 0.65);
      const alto = 34 * (1 - 0.92 * cierre);

      // Cejas
      const elevar = pensando || vivo.estado === 'escuchando' ? -5 : val_cejas_y;
      ctx.strokeStyle = '#465a69'; ctx.lineWidth = 3; ctx.lineCap = 'round';
      [-1, 1].forEach(lado => {
        const ex = lado * 32, angLado = (-lado * val_cejas_ang * Math.PI) / 180.0;
        ctx.save(); ctx.translate(ex + ojo_x * 0.4, -42 + elevar + 5); ctx.rotate(angLado);
        ctx.beginPath(); ctx.arc(0, 0, 11, Math.PI * 1.1, Math.PI * 1.9); ctx.stroke(); ctx.restore();
      });

      // Ojos
      [-1, 1].forEach(lado => {
        const ex = lado * 32, altoOjo = (alto / 2 + 2) * val_ojos_ap;
        ctx.fillStyle = '#233746';
        ctx.beginPath(); ctx.ellipse(ex + ojo_x, -8 + ojo_y, 14, Math.max(1, altoOjo), 0, 0, Math.PI * 2); ctx.fill();
        if (cierre < 0.5) {
          ctx.fillStyle = '#ffffff'; ctx.beginPath(); ctx.arc(ex + ojo_x + 5, -15 + ojo_y, 4.5, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = 'rgba(255, 255, 255, 0.78)'; ctx.beginPath(); ctx.arc(ex + ojo_x - 4, -3 + ojo_y, 2.2, 0, Math.PI * 2); ctx.fill();
        }
      });

      // Mejillas
      ctx.fillStyle = `rgba(255, 140, 160, ${val_rubor / 255.0})`;
      ctx.beginPath(); ctx.ellipse(-55, 22, 12, 7, 0, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.ellipse(55, 22, 12, 7, 0, 0, Math.PI * 2); ctx.fill();

      // Boca
      if (hablando) {
        const targetAbre = vivo.volumen > 0.0 ? 3.0 + 15.0 * Math.min(1.0, vivo.volumen * 1.6) : 3.5 + 11.0 * ((Math.sin(t * 11.5) * 0.5 + 0.5) * (0.6 + 0.4 * Math.sin(t * 3.3) ** 2));
        boca_abre += (targetAbre - boca_abre) * 0.35;
        ctx.fillStyle = '#c85064';
        ctx.beginPath(); ctx.ellipse(0, 38, Math.max(11.0, val_boca_ancho * 0.48), Math.max(2.5, boca_abre), 0, 0, Math.PI * 2); ctx.fill();
      } else {
        boca_abre = 0.0;
        ctx.strokeStyle = '#c85064'; ctx.lineWidth = 3; ctx.lineCap = 'round';
        const wBoca = val_boca_ancho, hBoca = Math.max(4.0, 18.0 * Math.abs(val_boca_curva));
        ctx.beginPath();
        if (val_boca_curva >= 0) ctx.arc(0, 35 - hBoca / 2, wBoca / 2, Math.PI * 0.15, Math.PI * 0.85);
        else ctx.arc(0, 39 + hBoca / 2, wBoca / 2, Math.PI * 1.15, Math.PI * 1.85);
        ctx.stroke();
      }

      ctx.restore();
      requestAnimationFrame(animar);
    }
    requestAnimationFrame(animar);
  </script>
</body>
</html>
"""

PAGINA_HTML = (
    _BASE_HTML.replace("/*CSS_PANEL*/", CSS_PANEL)
    .replace("<!--HTML_PANEL-->", HTML_PANEL)
    .replace("/*JS_PANEL*/", JS_PANEL)
)
