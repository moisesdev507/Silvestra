"""Definición del plano arquitectónico SVG 2D realista con muebles y texturas."""

SVG_PLANO = """
<svg id="plano-svg" viewBox="0 0 940 600" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <pattern id="pat-madera" width="60" height="20" patternUnits="userSpaceOnUse">
      <rect width="60" height="20" fill="#231a14"/>
      <rect x="0" y="0" width="58" height="9" fill="#2d221a" stroke="#1a120c" stroke-width="0.8"/>
      <rect x="30" y="10" width="58" height="9" fill="#291e17" stroke="#1a120c" stroke-width="0.8"/>
      <line x1="0" y1="10" x2="60" y2="10" stroke="#150f09" stroke-width="1"/>
      <line x1="30" y1="0" x2="30" y2="10" stroke="#150f09" stroke-width="0.8"/>
      <line x1="0" y1="10" x2="0" y2="20" stroke="#150f09" stroke-width="0.8"/>
    </pattern>
    <pattern id="pat-baldosa" width="36" height="36" patternUnits="userSpaceOnUse">
      <rect width="36" height="36" fill="#182030"/>
      <rect x="1" y="1" width="34" height="34" fill="#1f293d" rx="2"/>
      <path d="M 0 36 L 36 36 M 36 0 L 36 36" stroke="#121824" stroke-width="1.5"/>
    </pattern>
    <radialGradient id="grad-luz-sala" cx="30%" cy="40%" r="70%">
      <stop offset="0%" stop-color="#ffe8a3" stop-opacity="0.38"/>
      <stop offset="45%" stop-color="#ffd166" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="#090d16" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="grad-luz-cocina" cx="60%" cy="40%" r="70%">
      <stop offset="0%" stop-color="#ffe8a3" stop-opacity="0.38"/>
      <stop offset="50%" stop-color="#ffd166" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="#090d16" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="grad-luz-entrada" cx="50%" cy="50%" r="65%">
      <stop offset="0%" stop-color="#ffe8a3" stop-opacity="0.40"/>
      <stop offset="50%" stop-color="#ffd166" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="#090d16" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="grad-luz-cuarto" cx="55%" cy="55%" r="70%">
      <stop offset="0%" stop-color="#ffe8a3" stop-opacity="0.38"/>
      <stop offset="48%" stop-color="#ffd166" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="#090d16" stop-opacity="0"/>
    </radialGradient>
    <filter id="som-mueble" x="-10%" y="-10%" width="130%" height="130%">
      <feDropShadow dx="2" dy="3" stdDeviation="3" flood-color="#04060a" flood-opacity="0.6"/>
    </filter>
  </defs>

  <rect x="25" y="18" width="890" height="564" rx="10" fill="#0d131f" stroke="#1e293b" stroke-width="4"/>

  <!-- SALA -->
  <g id="cuarto-sala" class="cuarto-grupo luz-on" onclick="moverCuarto('Sala')">
    <rect x="34" y="26" width="470" height="268" fill="url(#pat-madera)"/>
    <g filter="url(#som-mueble)">
      <rect x="60" y="66" width="225" height="185" rx="10" fill="#322e2b" stroke="#483f36" stroke-width="2"/>
      <path d="M 75 78 L 220 78 A 8 8 0 0 1 228 86 L 228 135 A 8 8 0 0 1 220 143 L 138 143 L 138 215 A 8 8 0 0 1 130 223 L 83 223 A 8 8 0 0 1 75 215 Z" fill="#253549" stroke="#3b516d" stroke-width="2"/>
      <rect x="85" y="86" width="40" height="46" rx="4" fill="#324763"/>
      <rect x="130" y="86" width="40" height="46" rx="4" fill="#324763"/>
      <rect x="175" y="86" width="40" height="46" rx="4" fill="#324763"/>
      <rect x="85" y="150" width="44" height="32" rx="4" fill="#324763"/>
      <rect x="85" y="186" width="44" height="28" rx="4" fill="#324763"/>
      <rect x="150" y="155" width="85" height="48" rx="6" fill="#1b1612" stroke="#4a3728" stroke-width="1.8"/>
      <rect x="165" y="165" width="28" height="28" rx="3" fill="#283344"/>
      <circle cx="212" cy="179" r="6" fill="#e2e8f0"/>
      <rect x="255" y="34" width="160" height="24" rx="4" fill="#1c2433" stroke="#2d3b52" stroke-width="1.5"/>
      <rect x="270" y="38" width="130" height="6" rx="2" fill="#0b0f19"/>
      <line x1="270" y1="41" x2="400" y2="41" stroke="#38bdf8" stroke-width="1.5" opacity="0.8"/>
      <circle cx="56" cy="48" r="14" fill="#22543d" stroke="#276749" stroke-width="2"/>
      <circle cx="53" cy="45" r="7" fill="#38a169"/>
    </g>
    <text x="360" y="120" fill="#718096" font-size="13" font-weight="700" letter-spacing="1">SALA</text>
    <rect class="cuarto-luz-radial" x="34" y="26" width="470" height="268" fill="url(#grad-luz-sala)"/>
    <rect class="cuarto-sombra-noche" x="34" y="26" width="470" height="268" fill="#080e1a"/>
    <rect class="cuarto-overlay-hover" x="34" y="26" width="470" height="268"/>
    <g class="lampara-btn" onclick="toggleLuz(event, 'Sala')">
      <circle cx="270" cy="180" r="20" fill="transparent"/>
      <circle class="lampara-halo" cx="270" cy="180" r="11" fill="#ffd166"/>
      <circle cx="270" cy="180" r="6" fill="#fff"/>
      <text x="270" y="206" text-anchor="middle" fill="#ffd166" font-size="10" font-weight="700">💡 Luz</text>
    </g>
  </g>

  <!-- COCINA -->
  <g id="cuarto-cocina" class="cuarto-grupo luz-off" onclick="moverCuarto('Cocina')">
    <rect x="508" y="26" width="400" height="268" fill="url(#pat-baldosa)"/>
    <g filter="url(#som-mueble)">
      <path d="M 520 34 L 895 34 L 895 190 L 845 190 L 845 80 L 520 80 Z" fill="#252f3f" stroke="#3b485d" stroke-width="2"/>
      <rect x="620" y="38" width="65" height="38" rx="4" fill="#111827" stroke="#4b5563" stroke-width="1.5"/>
      <circle cx="636" cy="48" r="6" fill="#374151" stroke="#9ca3af" stroke-width="1"/>
      <circle cx="668" cy="48" r="6" fill="#374151" stroke="#9ca3af" stroke-width="1"/>
      <circle cx="636" cy="66" r="6" fill="#374151" stroke="#9ca3af" stroke-width="1"/>
      <circle cx="668" cy="66" r="6" fill="#374151" stroke="#9ca3af" stroke-width="1"/>
      <rect x="725" y="40" width="56" height="34" rx="3" fill="#1a202c" stroke="#64748b" stroke-width="1.5"/>
      <rect x="729" y="44" width="22" height="26" rx="2" fill="#334155"/>
      <rect x="755" y="44" width="22" height="26" rx="2" fill="#334155"/>
      <circle cx="753" cy="42" r="3" fill="#cbd5e0"/>
      <rect x="840" y="198" width="58" height="68" rx="4" fill="#374151" stroke="#6b7280" stroke-width="1.8"/>
      <line x1="840" y1="230" x2="898" y2="230" stroke="#1f2937" stroke-width="1.5"/>
      <rect x="846" y="210" width="4" height="15" rx="1" fill="#9ca3af"/>
      <rect x="846" y="238" width="4" height="20" rx="1" fill="#9ca3af"/>
      <rect x="560" y="140" width="140" height="55" rx="8" fill="#2d2218" stroke="#4a3b2c" stroke-width="2"/>
      <rect x="568" y="146" width="124" height="43" rx="5" fill="#3b2c1d"/>
      <circle cx="595" cy="216" r="13" fill="#1e293b" stroke="#334155" stroke-width="1.8"/>
      <circle cx="665" cy="216" r="13" fill="#1e293b" stroke="#334155" stroke-width="1.8"/>
    </g>
    <text x="735" y="165" fill="#718096" font-size="13" font-weight="700" letter-spacing="1">COCINA</text>
    <rect class="cuarto-luz-radial" x="508" y="26" width="400" height="268" fill="url(#grad-luz-cocina)"/>
    <rect class="cuarto-sombra-noche" x="508" y="26" width="400" height="268" fill="#080e1a"/>
    <rect class="cuarto-overlay-hover" x="508" y="26" width="400" height="268"/>
    <g class="lampara-btn" onclick="toggleLuz(event, 'Cocina')">
      <circle cx="680" cy="115" r="20" fill="transparent"/>
      <circle class="lampara-halo" cx="680" cy="115" r="11" fill="#ffd166"/>
      <circle cx="680" cy="115" r="6" fill="#fff"/>
      <text x="680" y="140" text-anchor="middle" fill="#ffd166" font-size="10" font-weight="700">💡 Luz</text>
    </g>
  </g>

  <!-- ENTRADA -->
  <g id="cuarto-entrada" class="cuarto-grupo luz-off" onclick="moverCuarto('Entrada')">
    <rect x="34" y="304" width="370" height="270" fill="url(#pat-baldosa)"/>
    <g filter="url(#som-mueble)">
      <rect x="140" y="505" width="85" height="45" rx="5" fill="#3f2e1e" stroke="#5a422d" stroke-width="1.8"/>
      <text x="182" y="532" text-anchor="middle" fill="#d97706" font-size="10" font-weight="800" letter-spacing="1">HOLA</text>
      <path d="M 140 558 A 65 65 0 0 1 205 493" fill="none" stroke="#64748b" stroke-width="1.8" stroke-dasharray="4 3"/>
      <line x1="140" y1="558" x2="140" y2="495" stroke="#a16207" stroke-width="4.5" stroke-linecap="round"/>
      <rect x="42" y="350" width="30" height="95" rx="5" fill="#2b1f17" stroke="#483424" stroke-width="1.8"/>
      <rect x="48" y="365" width="18" height="28" rx="3" fill="#1e293b"/>
      <circle cx="57" cy="415" r="6" fill="#cbd5e0"/>
      <circle cx="58" cy="485" r="16" fill="#1b4332" stroke="#2d6a4f" stroke-width="2"/>
      <circle cx="58" cy="485" r="8" fill="#52b788"/>
      <circle cx="255" cy="535" r="11" fill="#334155" stroke="#475569" stroke-width="1.5"/>
    </g>
    <text x="210" y="375" fill="#718096" font-size="13" font-weight="700" letter-spacing="1">ENTRADA</text>
    <rect class="cuarto-luz-radial" x="34" y="304" width="370" height="270" fill="url(#grad-luz-entrada)"/>
    <rect class="cuarto-sombra-noche" x="34" y="304" width="370" height="270" fill="#080e1a"/>
    <rect class="cuarto-overlay-hover" x="34" y="304" width="370" height="270"/>
    <g class="lampara-btn" onclick="toggleLuz(event, 'Entrada')">
      <circle cx="210" cy="430" r="20" fill="transparent"/>
      <circle class="lampara-halo" cx="210" cy="430" r="11" fill="#ffd166"/>
      <circle cx="210" cy="430" r="6" fill="#fff"/>
      <text x="210" y="455" text-anchor="middle" fill="#ffd166" font-size="10" font-weight="700">💡 Luz</text>
    </g>
  </g>

  <!-- CUARTO -->
  <g id="cuarto-cuarto" class="cuarto-grupo luz-off" onclick="moverCuarto('Cuarto')">
    <rect x="412" y="304" width="496" height="270" fill="url(#pat-madera)"/>
    <g filter="url(#som-mueble)">
      <rect x="560" y="318" width="168" height="195" rx="8" fill="#1e293b" stroke="#334155" stroke-width="2"/>
      <rect x="555" y="314" width="178" height="14" rx="4" fill="#0f172a" stroke="#1e293b" stroke-width="1.5"/>
      <rect x="575" y="332" width="60" height="34" rx="5" fill="#e2e8f0" stroke="#cbd5e0" stroke-width="1"/>
      <rect x="653" y="332" width="60" height="34" rx="5" fill="#e2e8f0" stroke="#cbd5e0" stroke-width="1"/>
      <rect x="566" y="375" width="156" height="132" rx="6" fill="#1e3a5f" stroke="#2563eb" stroke-width="1"/>
      <rect x="566" y="455" width="156" height="52" rx="4" fill="#132742"/>
      <rect x="515" y="325" width="38" height="42" rx="4" fill="#2d2218" stroke="#4a3728" stroke-width="1.5"/>
      <circle cx="534" cy="346" r="6" fill="#ffd166" opacity="0.8"/>
      <rect x="735" y="325" width="38" height="42" rx="4" fill="#2d2218" stroke="#4a3728" stroke-width="1.5"/>
      <circle cx="754" cy="346" r="6" fill="#ffd166" opacity="0.8"/>
      <rect x="550" y="518" width="188" height="36" rx="6" fill="#332f2c" stroke="#4a423d" stroke-width="1.5"/>
      <rect x="422" y="400" width="46" height="105" rx="5" fill="#1f2937" stroke="#374151" stroke-width="1.8"/>
      <rect x="428" y="435" width="22" height="35" rx="3" fill="#0f172a" stroke="#60a5fa" stroke-width="1.2"/>
      <ellipse cx="488" cy="452" rx="16" ry="18" fill="#111827" stroke="#4b5563" stroke-width="1.8"/>
      <rect x="478" y="440" width="8" height="24" rx="2" fill="#374151"/>
      <rect x="850" y="320" width="48" height="230" rx="4" fill="#1a202c" stroke="#334155" stroke-width="1.8"/>
      <line x1="874" y1="320" x2="874" y2="550" stroke="#475569" stroke-width="1.5"/>
      <rect x="868" y="425" width="3" height="20" rx="1" fill="#94a3b8"/>
      <rect x="877" y="425" width="3" height="20" rx="1" fill="#94a3b8"/>
    </g>
    <text x="635" y="405" fill="#718096" font-size="13" font-weight="700" letter-spacing="1">CUARTO</text>
    <rect class="cuarto-luz-radial" x="412" y="304" width="496" height="270" fill="url(#grad-luz-cuarto)"/>
    <rect class="cuarto-sombra-noche" x="412" y="304" width="496" height="270" fill="#080e1a"/>
    <rect class="cuarto-overlay-hover" x="412" y="304" width="496" height="270"/>
    <g class="lampara-btn" onclick="toggleLuz(event, 'Cuarto')">
      <circle cx="640" cy="465" r="20" fill="transparent"/>
      <circle class="lampara-halo" cx="640" cy="465" r="11" fill="#ffd166"/>
      <circle cx="640" cy="465" r="6" fill="#fff"/>
      <text x="640" y="490" text-anchor="middle" fill="#ffd166" font-size="10" font-weight="700">💡 Luz</text>
    </g>
  </g>

  <!-- PAREDES ARQUITECTÓNICAS -->
  <g fill="#1a2436" stroke="#2d3f5e" stroke-width="1.5">
    <path d="M 28 20 L 912 20 L 912 578 L 28 578 Z M 38 30 L 38 568 L 902 568 L 902 30 Z" fill-rule="evenodd"/>
    <rect x="34" y="294" width="130" height="12"/>
    <rect x="250" y="294" width="658" height="12"/>
    <rect x="500" y="26" width="12" height="110"/>
    <rect x="500" y="220" width="12" height="80"/>
    <rect x="404" y="298" width="12" height="276"/>
  </g>

  <!-- PERSONAJE TOP-DOWN Y ANILLO -->
  <g id="personaje" transform="translate(250, 180)">
    <circle id="onda-anillo-elem" class="onda-anillo" cx="16" cy="12" r="6"/>
    <ellipse cx="0" cy="2" rx="23" ry="17" fill="#03060a" opacity="0.6"/>
    <ellipse cx="0" cy="2" rx="22" ry="14" fill="#2b6cb0" stroke="#4299e1" stroke-width="1.8"/>
    <circle cx="0" cy="0" r="15" fill="#2d3748" stroke="#4a5568" stroke-width="1.5"/>
    <circle cx="0" cy="-3" r="13" fill="#1a202c"/>
    <path d="M 12 4 Q 20 6 16 12" fill="none" stroke="#2b6cb0" stroke-width="4.5" stroke-linecap="round"/>
    <circle cx="16" cy="12" r="5" fill="#ecc94b"/>
    <circle class="anillo-punto" cx="16" cy="12" r="3.2" fill="#4fd1c5"/>
    <circle cx="16" cy="12" r="1.5" fill="#ffffff"/>
  </g>
</svg>
"""
