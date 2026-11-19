"""Ensamblador de la interfaz HTML/JS para la Casa Virtual 2D realista."""

from casa_web_estilos import CSS_CASA
from casa_web_plano import SVG_PLANO

PAGINA_CASA_HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Silvestra - Casa Virtual 2D</title>
<style>
{CSS_CASA}
</style>
</head>
<body>
<div id="app-container">
  <header>
    <div class="header-left">
      <span class="header-title">🏡 Silvestra - Casa Virtual</span>
      <span class="header-sub">Plano arquitectónico 2D interactivo</span>
    </div>
    <div class="header-badge" id="lbl-pos">Sala</div>
  </header>

  <div id="plano-wrapper">
    {SVG_PLANO}
  </div>

  <footer>
    <div id="burbuja-texto">
      <strong>💬 Silvestra:</strong>
      <span id="txt-silvestra">Lista en la casa virtual.</span>
    </div>
    <button id="btn-toque-anillo" onclick="toqueAnillo()">
      <span style="font-size: 1.15rem;">💍</span>
      <span>TOQUE DE ANILLO</span>
    </button>
  </footer>
</div>

<script>
let cuartoActual = "Sala";
const luces = {{ "Sala": true, "Cocina": false, "Entrada": false, "Cuarto": false }};
const coords = {{
  "Sala": {{ x: 250, y: 180 }},
  "Cocina": {{ x: 680, y: 180 }},
  "Entrada": {{ x: 200, y: 430 }},
  "Cuarto": {{ x: 620, y: 430 }}
}};

function decir(txt) {{
  const el = document.getElementById("txt-silvestra");
  if (el && txt) el.textContent = txt;
}}

function aplicarLuces(datosLuces) {{
  if (!datosLuces) return;
  for (const [c, encendida] of Object.entries(datosLuces)) {{
    luces[c] = encendida;
    const g = document.getElementById("cuarto-" + c.toLowerCase());
    if (g) {{
      g.classList.toggle("luz-on", !!encendida);
      g.classList.toggle("luz-off", !encendida);
    }}
  }}
}}

function reposicionarPersonaje(cuartoNom) {{
  const c = coords[cuartoNom] || coords["Sala"];
  const p = document.getElementById("personaje");
  if (p) {{
    p.style.transform = `translate(${{c.x}}px, ${{c.y}}px)`;
  }}
  const b = document.getElementById("lbl-pos");
  if (b) b.textContent = cuartoNom;
}}

async function enviarEvento(tipo, cuarto) {{
  try {{
    const qs = window.location.search || "";
    const res = await fetch("/api/casa/evento" + qs, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ tipo: tipo, cuarto: cuarto }})
    }});
    const d = await res.json();
    if (d && d.frase) decir(d.frase);
    if (d && d.luces) aplicarLuces(d.luces);
  }} catch (err) {{
    console.warn("Fallo evento casa:", err);
  }}
}}

function moverCuarto(cuartoNom) {{
  if (!coords[cuartoNom] || cuartoActual === cuartoNom) return;
  cuartoActual = cuartoNom;
  reposicionarPersonaje(cuartoNom);
  enviarEvento("mover", cuartoNom);
}}

function toqueAnillo() {{
  const onda = document.getElementById("onda-anillo-elem");
  if (onda) {{
    onda.classList.remove("onda-activa");
    void onda.offsetWidth;
    onda.classList.add("onda-activa");
  }}
  enviarEvento("anillo", cuartoActual);
}}

function toggleLuz(ev, cuartoNom) {{
  if (ev) ev.stopPropagation();
  luces[cuartoNom] = !luces[cuartoNom];
  const g = document.getElementById("cuarto-" + cuartoNom.toLowerCase());
  if (g) {{
    g.classList.toggle("luz-on", luces[cuartoNom]);
    g.classList.toggle("luz-off", !luces[cuartoNom]);
  }}
  enviarEvento("luz", cuartoNom);
}}

window.addEventListener("DOMContentLoaded", () => {{
  reposicionarPersonaje(cuartoActual);
  aplicarLuces(luces);
  const qs = window.location.search || "";
  fetch("/api/casa/estado" + qs)
    .then(r => r.json())
    .then(d => {{
      if (d.cuarto) {{
        cuartoActual = d.cuarto;
        reposicionarPersonaje(d.cuarto);
      }}
      if (d.luces) aplicarLuces(d.luces);
      if (d.frase) decir(d.frase);
    }})
    .catch(() => {{}});
}});
</script>
</body>
</html>
"""
