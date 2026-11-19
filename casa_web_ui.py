"""Plantilla HTML, CSS y JavaScript para la interfaz 2D de la Casa Virtual en tablet."""

PAGINA_CASA_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Silvestra - Casa Virtual 2D</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
body {
  background: #0d121d;
  color: #e2e8f0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 14px;
  user-select: none;
}
header {
  width: 100%;
  max-width: 680px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #141b2d;
  border-radius: 12px;
  border: 1px solid #232d42;
  margin-bottom: 12px;
}
.tit-box h1 { font-size: 1.1rem; color: #4fd1c5; font-weight: 700; display: flex; align-items: center; gap: 6px; }
.tit-box p { font-size: 0.78rem; color: #a0aec0; }
.badge {
  font-size: 0.75rem;
  background: #1b263b;
  color: #68d391;
  padding: 4px 10px;
  border-radius: 20px;
  border: 1px solid #2d3f5e;
  font-weight: 600;
}
#plano {
  position: relative;
  width: 100%;
  max-width: 680px;
  height: 380px;
  background: #101624;
  border-radius: 18px;
  border: 2px solid #232d42;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5);
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 10px;
  padding: 10px;
}
.cuarto {
  position: relative;
  background: #162035;
  border: 2px solid #28354f;
  border-radius: 14px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  cursor: pointer;
  transition: all 0.25s ease;
}
.cuarto:hover, .cuarto:active {
  background: #1b2844;
  border-color: #4fd1c5;
}
.cuarto.activo {
  border-color: #4fd1c5;
  box-shadow: inset 0 0 18px rgba(79, 209, 197, 0.15);
}
.cuarto-cab {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.cuarto-nom {
  font-size: 0.95rem;
  font-weight: 700;
  color: #f7fafc;
  display: flex;
  align-items: center;
  gap: 6px;
}
.luz-btn {
  background: #232d42;
  color: #cbd5e0;
  border: 1px solid #364461;
  border-radius: 14px;
  padding: 3px 8px;
  font-size: 0.72rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  transition: all 0.2s;
}
.luz-btn.on {
  background: #3b3519;
  color: #ffd166;
  border-color: #ffd166;
  box-shadow: 0 0 8px rgba(255, 209, 102, 0.3);
}
.cuarto-centro {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.zona-drop {
  width: 54px;
  height: 54px;
  border-radius: 50%;
  border: 2px dashed #2d3b55;
  display: flex;
  align-items: center;
  justify-content: center;
}
#muneco {
  position: absolute;
  width: 58px;
  height: 58px;
  background: radial-gradient(circle, #2b3952 0%, #162035 100%);
  border: 2.5px solid #4fd1c5;
  border-radius: 50%;
  box-shadow: 0 0 20px rgba(79, 209, 197, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  pointer-events: none;
  z-index: 20;
  transition: transform 0.45s cubic-bezier(0.25, 1, 0.5, 1);
}
.anillo-badge {
  position: absolute;
  bottom: -4px;
  right: -4px;
  background: #ffd166;
  border: 1.5px solid #0d121d;
  border-radius: 50%;
  width: 22px;
  height: 22px;
  font-size: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 8px rgba(255, 209, 102, 0.6);
}
.anillo-onda {
  position: absolute;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 2px solid #ffd166;
  opacity: 0;
  pointer-events: none;
}
@keyframes pulsoAnillo {
  0% { transform: scale(0.9); opacity: 1; }
  100% { transform: scale(2.2); opacity: 0; }
}
.pulsando {
  animation: pulsoAnillo 0.8s ease-out forwards;
}
footer {
  width: 100%;
  max-width: 680px;
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
#burbuja {
  background: #141b2d;
  border: 1px solid #232d42;
  border-left: 4px solid #4fd1c5;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 0.85rem;
  color: #cbd5e0;
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 8px;
}
#btn-anillo {
  width: 100%;
  padding: 15px;
  background: linear-gradient(135deg, #319795 0%, #2b6cb0 100%);
  color: white;
  border: none;
  border-radius: 14px;
  font-size: 1.05rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  box-shadow: 0 6px 18px rgba(49, 151, 149, 0.35);
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}
#btn-anillo:active {
  transform: scale(0.97);
  box-shadow: 0 2px 8px rgba(49, 151, 149, 0.4);
}
</style>
</head>
<body>
<header>
  <div class="tit-box">
    <h1>🏡 Casa Virtual 2D</h1>
    <p>Plano interactivo para tablet y navegador</p>
  </div>
  <div class="badge" id="lbl-pos">Sala</div>
</header>

<div id="plano">
  <div class="cuarto activo" id="c-sala" onclick="moverCuarto('Sala')">
    <div class="cuarto-cab">
      <span class="cuarto-nom">🛋️ Sala</span>
      <button class="luz-btn on" id="luz-sala" onclick="toggleLuz(event, 'Sala')">💡 Luz</button>
    </div>
    <div class="cuarto-centro"><div class="zona-drop"></div></div>
  </div>

  <div class="cuarto" id="c-cocina" onclick="moverCuarto('Cocina')">
    <div class="cuarto-cab">
      <span class="cuarto-nom">🍳 Cocina</span>
      <button class="luz-btn" id="luz-cocina" onclick="toggleLuz(event, 'Cocina')">💡 Luz</button>
    </div>
    <div class="cuarto-centro"><div class="zona-drop"></div></div>
  </div>

  <div class="cuarto" id="c-entrada" onclick="moverCuarto('Entrada')">
    <div class="cuarto-cab">
      <span class="cuarto-nom">🚪 Entrada</span>
      <button class="luz-btn" id="luz-entrada" onclick="toggleLuz(event, 'Entrada')">💡 Luz</button>
    </div>
    <div class="cuarto-centro"><div class="zona-drop"></div></div>
  </div>

  <div class="cuarto" id="c-cuarto" onclick="moverCuarto('Cuarto')">
    <div class="cuarto-cab">
      <span class="cuarto-nom">🛏️ Cuarto</span>
      <button class="luz-btn" id="luz-cuarto" onclick="toggleLuz(event, 'Cuarto')">💡 Luz</button>
    </div>
    <div class="cuarto-centro"><div class="zona-drop"></div></div>
  </div>

  <div id="muneco">
    <span>🤖</span>
    <div class="anillo-badge">💍</div>
    <div class="anillo-onda" id="onda"></div>
  </div>
</div>

<footer>
  <div id="burbuja">💬 <span>Silvestra: Lista en la casa virtual.</span></div>
  <button id="btn-anillo" onclick="toqueAnillo()">
    <span>💍</span> TOQUE DE ANILLO
  </button>
</footer>

<script>
let cuartoActual = "Sala";
const luces = { "Sala": true, "Cocina": false, "Entrada": false, "Cuarto": false };

function actualizarPosicionMuneco(cuartoNom) {
  const mapIds = { "Sala": "c-sala", "Cocina": "c-cocina", "Entrada": "c-entrada", "Cuarto": "c-cuarto" };
  const elem = document.getElementById(mapIds[cuartoNom]);
  const plano = document.getElementById("plano");
  const muneco = document.getElementById("muneco");
  if (!elem || !plano || !muneco) return;

  document.querySelectorAll(".cuarto").forEach(c => c.classList.remove("activo"));
  elem.classList.add("activo");
  document.getElementById("lbl-pos").textContent = cuartoNom;

  const drop = elem.querySelector(".zona-drop");
  const rectDrop = drop.getBoundingClientRect();
  const rectPlano = plano.getBoundingClientRect();

  const x = (rectDrop.left - rectPlano.left) + (rectDrop.width / 2) - 29;
  const y = (rectDrop.top - rectPlano.top) + (rectDrop.height / 2) - 29;

  muneco.style.transform = `translate3d(${x}px, ${y}px, 0)`;
}

function decir(txt) {
  const el = document.querySelector("#burbuja span");
  if (el) el.textContent = txt;
}

async function enviarEvento(tipo, cuarto) {
  try {
    const res = await fetch("/api/casa/evento", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tipo: tipo, cuarto: cuarto })
    });
    const d = await res.json();
    if (d && d.frase) decir("Silvestra: " + d.frase);
    if (d && d.luces) {
      for (const [k, v] of Object.entries(d.luces)) {
        luces[k] = v;
        const b = document.getElementById("luz-" + k.toLowerCase());
        if (b) b.classList.toggle("on", !!v);
      }
    }
  } catch (err) {
    console.warn("Fallo evento casa:", err);
  }
}

function moverCuarto(cuartoNom) {
  if (cuartoActual === cuartoNom) return;
  cuartoActual = cuartoNom;
  actualizarPosicionMuneco(cuartoNom);
  enviarEvento("mover", cuartoNom);
}

function toqueAnillo() {
  const onda = document.getElementById("onda");
  if (onda) {
    onda.classList.remove("pulsando");
    void onda.offsetWidth;
    onda.classList.add("pulsando");
  }
  enviarEvento("anillo", cuartoActual);
}

function toggleLuz(ev, cuartoNom) {
  ev.stopPropagation();
  luces[cuartoNom] = !luces[cuartoNom];
  const b = document.getElementById("luz-" + cuartoNom.toLowerCase());
  if (b) b.classList.toggle("on", luces[cuartoNom]);
  enviarEvento("luz", cuartoNom);
}

window.addEventListener("resize", () => actualizarPosicionMuneco(cuartoActual));
window.addEventListener("DOMContentLoaded", () => {
  actualizarPosicionMuneco(cuartoActual);
  fetch("/api/casa/estado").then(r => r.json()).then(d => {
    if (d.cuarto) { cuartoActual = d.cuarto; actualizarPosicionMuneco(d.cuarto); }
    if (d.luces) {
      for (const [k, v] of Object.entries(d.luces)) {
        luces[k] = v;
        const b = document.getElementById("luz-" + k.toLowerCase());
        if (b) b.classList.toggle("on", !!v);
      }
    }
    if (d.frase) decir("Silvestra: " + d.frase);
  }).catch(() => {});
});
</script>
</body>
</html>
"""
