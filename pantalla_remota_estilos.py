"""Estilos CSS profesionales para la interfaz Jarvis HUD de la tablet."""

CSS_JARVIS = """
:root {
  --bg-space: #050811;
  --bg-card: rgba(10, 18, 32, 0.78);
  --bg-card-hover: rgba(15, 27, 48, 0.88);
  --cyan: #00f0ff;
  --cyan-dim: rgba(0, 240, 255, 0.25);
  --cyan-glow: 0 0 15px rgba(0, 240, 255, 0.45);
  --gold: #ffd166;
  --gold-dim: rgba(255, 209, 102, 0.25);
  --green: #10b981;
  --border: rgba(0, 240, 255, 0.22);
  --border-dim: rgba(255, 255, 255, 0.08);
  --text-main: #f1f5f9;
  --text-muted: #94a3b8;
  --font-hud: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
  --font-mono: Consolas, 'SF Mono', 'Courier New', monospace;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
  user-select: none;
  -webkit-user-select: none;
}

body {
  background-color: var(--bg-space);
  background-image: 
    radial-gradient(circle at 50% 30%, rgba(0, 180, 216, 0.08) 0%, transparent 70%),
    linear-gradient(rgba(0, 240, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 240, 255, 0.03) 1px, transparent 1px);
  background-size: 100% 100%, 36px 36px, 36px 36px;
  color: var(--text-main);
  font-family: var(--font-hud);
  min-height: 100vh;
  overflow-x: hidden;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

/* Header superior estilo HUD */
header.hud-header {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: rgba(7, 13, 25, 0.9);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.5);
  z-index: 10;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-title {
  font-size: 15px;
  font-weight: 800;
  letter-spacing: 2px;
  color: var(--cyan);
  text-shadow: var(--cyan-glow);
}

.brand-badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 4px;
  background: var(--cyan-dim);
  border: 1px solid var(--cyan);
  color: #fff;
  font-family: var(--font-mono);
  letter-spacing: 1px;
}

.header-status {
  display: flex;
  align-items: center;
  gap: 16px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.live-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--green);
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
  animation: pulse 1.8s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.9); opacity: 0.8; }
  50% { transform: scale(1.3); opacity: 1; }
  100% { transform: scale(0.9); opacity: 0.8; }
}

.mode-pill {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: bold;
  letter-spacing: 1px;
  transition: all 0.3s;
}

.mode-normal {
  background: rgba(0, 240, 255, 0.15);
  border: 1px solid var(--cyan);
  color: var(--cyan);
}

.mode-privado {
  background: rgba(255, 209, 102, 0.2);
  border: 1px solid var(--gold);
  color: var(--gold);
}

/* Grid principal para Tablet Horizontal */
main.hud-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 280px 1fr 310px;
  gap: 18px;
  padding: 18px 24px;
  max-width: 1600px;
  margin: 0 auto;
  width: 100%;
}

@media (max-width: 980px) {
  main.hud-grid {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}

/* Paneles laterales */
.hud-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hud-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(8px);
}

.hud-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: var(--cyan);
  box-shadow: var(--cyan-glow);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: var(--text-muted);
  text-transform: uppercase;
}

.metric-row {
  margin-bottom: 12px;
}

.metric-label-val {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 5px;
}

.metric-bar-bg {
  width: 100%;
  height: 7px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 4px;
  overflow: hidden;
}

.metric-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #0284c7, var(--cyan));
  border-radius: 4px;
  transition: width 0.4s ease;
  box-shadow: var(--cyan-glow);
}

/* Columna central */
.hud-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

/* Contenedor del orbe Jarvis */
.orb-container {
  position: relative;
  width: 240px;
  height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
}

#orbCanvas {
  width: 240px;
  height: 240px;
}

.state-badge {
  position: absolute;
  bottom: 0;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 2px;
  padding: 4px 14px;
  border-radius: 12px;
  background: rgba(5, 8, 17, 0.9);
  border: 1px solid var(--cyan);
  color: var(--cyan);
  text-shadow: var(--cyan-glow);
  text-transform: uppercase;
}

/* Reloj Digital Central */
.clock-section {
  text-align: center;
}

.clock-digits {
  font-family: var(--font-mono);
  font-size: 52px;
  font-weight: 800;
  color: #fff;
  letter-spacing: 2px;
  text-shadow: 0 0 20px rgba(0, 240, 255, 0.4);
  line-height: 1;
}

.clock-ampm {
  font-size: 20px;
  color: var(--cyan);
  margin-left: 6px;
}

.date-string {
  font-size: 14px;
  color: var(--text-muted);
  letter-spacing: 1px;
  margin-top: 6px;
}

/* Subtítulo y Tarjeta Dinámica */
.stream-box {
  width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  min-height: 60px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stream-label {
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--cyan);
  font-family: var(--font-mono);
}

.stream-text {
  font-size: 14px;
  color: var(--text-main);
  line-height: 1.4;
  font-style: italic;
}

.dynamic-card {
  width: 100%;
  background: linear-gradient(135deg, rgba(14, 28, 48, 0.9), rgba(8, 14, 25, 0.95));
  border: 1px solid var(--cyan);
  border-radius: 8px;
  padding: 14px 18px;
  box-shadow: 0 0 16px rgba(0, 240, 255, 0.18);
}

.dynamic-card-title {
  font-size: 11px;
  font-family: var(--font-mono);
  letter-spacing: 2px;
  color: var(--gold);
  margin-bottom: 6px;
  text-transform: uppercase;
}

.dynamic-card-body {
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  line-height: 1.4;
}

/* Listas del panel derecho */
.item-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 180px;
  overflow-y: auto;
}

.list-item {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-dim);
  border-radius: 6px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  transition: border-color 0.2s;
}

.list-item:hover {
  border-color: var(--cyan);
}

.item-top {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--cyan);
}

.item-text {
  font-size: 13px;
  color: var(--text-main);
  line-height: 1.3;
}

.private-banner {
  padding: 18px 12px;
  text-align: center;
  background: rgba(255, 209, 102, 0.08);
  border: 1px dashed var(--gold);
  border-radius: 6px;
  color: var(--gold);
  font-size: 12px;
  font-family: var(--font-mono);
  letter-spacing: 1px;
}

.log-entry {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
"""
