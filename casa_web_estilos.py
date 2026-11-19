"""Estilos CSS para la vista arquitectónica 2D de la Casa Virtual."""

CSS_CASA = """
* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
html, body {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #090d16;
  color: #e2e8f0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  user-select: none;
}
#app-container {
  display: flex;
  flex-direction: column;
  width: 100vw;
  height: 100vh;
  justify-content: space-between;
  padding: 8px 14px 10px 14px;
}
header {
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 14px;
  background: rgba(19, 27, 45, 0.85);
  backdrop-filter: blur(10px);
  border-radius: 10px;
  border: 1px solid #23304a;
  z-index: 10;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: #4fd1c5;
  letter-spacing: 0.3px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.header-sub {
  font-size: 0.72rem;
  color: #718096;
}
.header-badge {
  font-size: 0.75rem;
  background: #142036;
  color: #ffd166;
  padding: 3px 10px;
  border-radius: 14px;
  border: 1px solid #283e66;
  font-weight: 600;
}
#plano-wrapper {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  padding: 4px 0;
}
#plano-svg {
  width: 100%;
  height: 100%;
  max-width: 1100px;
  max-height: 100%;
  filter: drop-shadow(0 14px 30px rgba(0,0,0,0.65));
  border-radius: 14px;
}
.cuarto-grupo {
  cursor: pointer;
  transition: filter 0.25s ease;
}
.cuarto-grupo:hover .cuarto-overlay-hover {
  opacity: 0.12;
}
.cuarto-overlay-hover {
  fill: #4fd1c5;
  opacity: 0;
  transition: opacity 0.2s ease;
  pointer-events: none;
}
.cuarto-sombra-noche {
  transition: opacity 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}
.cuarto-luz-radial {
  transition: opacity 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}
.luz-off .cuarto-sombra-noche { opacity: 0.88; }
.luz-off .cuarto-luz-radial { opacity: 0.0; }
.luz-on .cuarto-sombra-noche { opacity: 0.05; }
.luz-on .cuarto-luz-radial { opacity: 1.0; }

.lampara-btn {
  cursor: pointer;
  transition: transform 0.2s ease, filter 0.2s ease;
}
.lampara-btn:hover {
  transform: scale(1.15);
}
.lampara-btn:active {
  transform: scale(0.92);
}
.lampara-halo {
  transition: opacity 0.3s ease, fill 0.3s ease;
}
.luz-off .lampara-halo { opacity: 0.2; fill: #4a5568; }
.luz-on .lampara-halo { opacity: 1; fill: #ffd166; filter: drop-shadow(0 0 8px rgba(255,209,102,0.8)); }

#personaje {
  pointer-events: none;
  transition: transform 0.6s cubic-bezier(0.25, 1, 0.4, 1);
  z-index: 50;
}
.anillo-punto {
  animation: pulso-brillo 1.8s infinite ease-in-out;
}
@keyframes pulso-brillo {
  0%, 100% { filter: drop-shadow(0 0 3px #4fd1c5) drop-shadow(0 0 7px #ffd166); transform: scale(1); }
  50% { filter: drop-shadow(0 0 7px #4fd1c5) drop-shadow(0 0 14px #ffd166); transform: scale(1.25); }
}

.onda-anillo {
  fill: none;
  stroke: #4fd1c5;
  stroke-width: 3;
  opacity: 0;
  pointer-events: none;
}
.onda-activa {
  animation: anim-onda 0.9s cubic-bezier(0.1, 0.8, 0.3, 1) forwards;
}
@keyframes anim-onda {
  0% { r: 6; opacity: 1; stroke: #ffd166; stroke-width: 4; }
  60% { stroke: #4fd1c5; stroke-width: 2.5; }
  100% { r: 160; opacity: 0; stroke: #3182ce; stroke-width: 1; }
}

footer {
  height: 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 14px;
  background: rgba(19, 27, 45, 0.92);
  backdrop-filter: blur(12px);
  border-radius: 12px;
  border: 1px solid #23304a;
  z-index: 10;
}
#burbuja-texto {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: #cbd5e0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
#burbuja-texto strong {
  color: #4fd1c5;
  font-weight: 700;
}
#btn-toque-anillo {
  height: 42px;
  padding: 0 22px;
  background: linear-gradient(135deg, #2c7a7b 0%, #2b6cb0 100%);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 0.88rem;
  font-weight: 700;
  letter-spacing: 0.3px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(44, 122, 123, 0.4);
  transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.2s ease;
  white-space: nowrap;
}
#btn-toque-anillo:active {
  transform: scale(0.96);
  box-shadow: 0 2px 6px rgba(44, 122, 123, 0.5);
}
"""
