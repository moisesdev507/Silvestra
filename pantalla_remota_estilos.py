"""Estilos CSS profesionales para la interfaz Jarvis HUD de la tablet."""

CSS_JARVIS = """
:root {
  --bg-space: #050811;
  --bg-card: rgba(8, 15, 28, 0.82);
  --bg-card-hover: rgba(12, 22, 40, 0.92);
  --cyan: #00f0ff;
  --cyan-dim: rgba(0, 240, 255, 0.2);
  --cyan-glow: 0 0 12px rgba(0, 240, 255, 0.45);
  --gold: #ffd166;
  --gold-dim: rgba(255, 209, 102, 0.2);
  --green: #10b981;
  --border: rgba(0, 240, 255, 0.25);
  --border-dim: rgba(255, 255, 255, 0.08);
  --text-main: #f8fafc;
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

html, body {
  width: 100%;
  height: 100%;
  height: 100dvh;
  max-height: 100dvh;
  overflow: hidden;
  background-color: var(--bg-space);
  background-image: 
    radial-gradient(circle at 50% 25%, rgba(0, 180, 216, 0.07) 0%, transparent 65%),
    linear-gradient(rgba(0, 240, 255, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 240, 255, 0.025) 1px, transparent 1px);
  background-size: 100% 100%, 30px 30px, 30px 30px;
  color: var(--text-main);
  font-family: var(--font-hud);
}

/* Header superior compacto */
header.hud-header {
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: rgba(6, 11, 22, 0.95);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.6);
  z-index: 10;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-title {
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 2px;
  color: var(--cyan);
  text-shadow: var(--cyan-glow);
}

.brand-badge {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--cyan-dim);
  border: 1px solid var(--cyan);
  color: #fff;
  font-family: var(--font-mono);
  letter-spacing: 1px;
}

.header-status {
  display: flex;
  align-items: center;
  gap: 12px;
  font-family: var(--font-mono);
  font-size: 11px;
}

.live-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--green);
}

.pulse-dot {
  width: 7px;
  height: 7px;
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
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: bold;
  letter-spacing: 1px;
  transition: all 0.3s;
}

.mode-normal {
  background: rgba(0, 240, 255, 0.12);
  border: 1px solid var(--cyan);
  color: var(--cyan);
}

.mode-privado {
  background: rgba(255, 209, 102, 0.18);
  border: 1px solid var(--gold);
  color: var(--gold);
}

.btn-hud {
  background: rgba(0, 240, 255, 0.08);
  border: 1px solid var(--border);
  color: var(--cyan);
  padding: 3px 10px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  cursor: pointer;
  letter-spacing: 1px;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.btn-hud:hover, .btn-hud:active {
  background: var(--cyan);
  color: #050811;
  box-shadow: var(--cyan-glow);
}

/* Grid principal tablet horizontal */
main.hud-grid {
  height: calc(100dvh - 42px);
  max-height: calc(100dvh - 42px);
  display: grid;
  grid-template-columns: 260px 1fr 290px;
  gap: 10px;
  padding: 8px 12px;
  overflow: hidden;
}

@media (max-width: 900px) {
  main.hud-grid {
    grid-template-columns: 240px 1fr 260px;
    gap: 8px;
  }
}

/* Paneles laterales con esquinas técnicas Jarvis */
.hud-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  overflow: hidden;
}

.hud-card {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 10px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(8px);
  overflow: hidden;
}

/* Corner brackets estilo HUD militar/Jarvis */
.hud-card::before {
  content: '';
  position: absolute;
  top: -1px; left: -1px;
  width: 7px; height: 7px;
  border-top: 2px solid var(--cyan);
  border-left: 2px solid var(--cyan);
  pointer-events: none;
}

.hud-card::after {
  content: '';
  position: absolute;
  bottom: -1px; right: -1px;
  width: 7px; height: 7px;
  border-bottom: 2px solid var(--cyan);
  border-right: 2px solid var(--cyan);
  pointer-events: none;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.card-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.2px;
  color: var(--text-muted);
  text-transform: uppercase;
}

.metric-row {
  margin-bottom: 7px;
}

.metric-label-val {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 3px;
}

.metric-bar-bg {
  width: 100%;
  height: 5px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.metric-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #0284c7, var(--cyan));
  border-radius: 3px;
  transition: width 0.35s ease;
  box-shadow: var(--cyan-glow);
}

/* Columna central */
.hud-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  padding: 4px 0;
  overflow: hidden;
}

.orb-container {
  position: relative;
  width: 170px;
  height: 170px;
  display: flex;
  align-items: center;
  justify-content: center;
}

#orbCanvas {
  width: 170px;
  height: 170px;
}

.state-badge {
  position: absolute;
  bottom: -4px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.5px;
  padding: 2px 10px;
  border-radius: 10px;
  background: rgba(5, 8, 17, 0.95);
  border: 1px solid var(--cyan);
  color: var(--cyan);
  text-shadow: var(--cyan-glow);
  text-transform: uppercase;
}

/* Reloj Digital Central */
.clock-section {
  text-align: center;
  margin-top: -2px;
}

.clock-digits {
  font-family: var(--font-mono);
  font-size: 40px;
  font-weight: 800;
  color: #fff;
  letter-spacing: 2px;
  text-shadow: 0 0 16px rgba(0, 240, 255, 0.4);
  line-height: 1;
}

.clock-ampm {
  font-size: 16px;
  color: var(--cyan);
  margin-left: 5px;
}

.date-string {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.8px;
  margin-top: 3px;
}

/* Subtítulo y Tarjeta Dinámica */
.stream-box {
  width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px 12px;
  min-height: 48px;
  max-height: 52px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
}

.stream-label {
  font-size: 9px;
  letter-spacing: 1.2px;
  color: var(--cyan);
  font-family: var(--font-mono);
}

.stream-text {
  font-size: 12px;
  color: var(--text-main);
  line-height: 1.3;
  font-style: italic;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dynamic-card {
  width: 100%;
  background: linear-gradient(135deg, rgba(14, 28, 48, 0.88), rgba(8, 14, 25, 0.94));
  border: 1px solid var(--cyan);
  border-radius: 4px;
  padding: 8px 12px;
  min-height: 52px;
  max-height: 58px;
  box-shadow: 0 0 14px rgba(0, 240, 255, 0.15);
  overflow: hidden;
}

.dynamic-card-title {
  font-size: 9px;
  font-family: var(--font-mono);
  letter-spacing: 1.5px;
  color: var(--gold);
  margin-bottom: 2px;
  text-transform: uppercase;
}

.dynamic-card-body {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Listas del panel derecho */
.flex-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.item-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-right: 2px;
}

.item-list::-webkit-scrollbar {
  width: 3px;
}
.item-list::-webkit-scrollbar-thumb {
  background: var(--cyan-dim);
  border-radius: 2px;
}

.list-item {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-dim);
  border-radius: 4px;
  padding: 5px 7px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-top {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--cyan);
}

.item-text {
  font-size: 11px;
  color: var(--text-main);
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.private-banner {
  padding: 12px 8px;
  text-align: center;
  background: rgba(255, 209, 102, 0.08);
  border: 1px dashed var(--gold);
  border-radius: 4px;
  color: var(--gold);
  font-size: 11px;
  font-family: var(--font-mono);
  letter-spacing: 0.8px;
}

.log-entry {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  padding: 2px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
"""
