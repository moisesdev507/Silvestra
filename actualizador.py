"""actualizador.py - Verificacion y actualizacion segura de Kaya desde GitHub Releases."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from version import REPO_GITHUB, VERSION

logger = logging.getLogger("silvestra.actualizador")

# Archivos y carpetas protegidos que NUNCA deben sobreescribirse
ARCHIVOS_EXCLUIDOS = [".env", "memoria.json", "silvestra.log", "*.tmp"]
CARPETAS_EXCLUIDAS = ["datos", "__pycache__"]


def parsear_version(tag: str) -> tuple[int, ...]:
    """Convierte tags como 'v1.0.1' o '1.2.0-beta' en tupla de enteros."""
    limpio = tag.strip().lstrip("vV")
    partes = re.findall(r"\d+", limpio)
    return tuple(int(p) for p in partes) if partes else (0, 0, 0)


def es_version_mayor(remota: str, local: str) -> bool:
    """Compara si la version remota es estrictamente mayor que la local."""
    return parsear_version(remota) > parsear_version(local)


def consultar_release_remoto(repo: str = REPO_GITHUB, timeout: float = 4.0) -> dict[str, Any] | None:
    """Consulta la API de GitHub Releases buscando la ultima version y assets."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Kaya-Updater/{VERSION}",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                tag = data.get("tag_name", "")
                assets = data.get("assets", [])
                zip_asset = next((a for a in assets if a.get("name") == "Kaya_Windows.zip"), None)
                if tag and zip_asset and "browser_download_url" in zip_asset:
                    return {
                        "tag": tag,
                        "url_zip": zip_asset["browser_download_url"],
                        "nombre_asset": zip_asset["name"],
                        "tamano": zip_asset.get("size", 0),
                        "notas": data.get("body", ""),
                    }
    except Exception as exc:
        logger.debug("Consulta de actualizacion omitida o fallida: %s", exc)
    return None


def generar_script_bat(
    directorio_destino: str,
    ruta_zip: str,
    pid_esperar: int,
    ejecutable_relanzar: str,
) -> str:
    """Genera el contenido del .bat auxiliar con robocopy y exclusiones estrictas."""
    exclusiones_archivos = " ".join(f'"{a}"' for a in ARCHIVOS_EXCLUIDOS)
    exclusiones_carpetas = " ".join(f'"{c}"' for c in CARPETAS_EXCLUIDAS)

    bat = f"""@echo off
setlocal enabledelayedexpansion
title Actualizando Kaya...
echo Esperando a que Kaya (PID {pid_esperar}) se cierre...

:bucle_espera
tasklist /fi "PID eq {pid_esperar}" 2>NUL | find /I "{pid_esperar}" >NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >NUL
    goto bucle_espera
)
timeout /t 2 /nobreak >NUL

set "TEMP_EXTRACT=%TEMP%\\Kaya_Update_Temp_%RANDOM%"
mkdir "!TEMP_EXTRACT!" 2>NUL

echo Extrayendo paquete de actualizacion...
tar -xf "{ruta_zip}" -C "!TEMP_EXTRACT!" >NUL 2>&1
if not "%ERRORLEVEL%"=="0" (
    powershell -NoProfile -Command "Expand-Archive -LiteralPath '{ruta_zip}' -DestinationPath '!TEMP_EXTRACT!' -Force" >NUL 2>&1
)

echo Copiando archivos manteniendo configuraciones y memorias intactas...
set "ORIGEN_COPIA=!TEMP_EXTRACT!"
if exist "!TEMP_EXTRACT!\\Kaya" (
    set "ORIGEN_COPIA=!TEMP_EXTRACT!\\Kaya"
)

robocopy "!ORIGEN_COPIA!" "{directorio_destino}" /E /XF {exclusiones_archivos} /XD {exclusiones_carpetas} /R:3 /W:1 >NUL

echo Limpiando temporales...
del /F /Q "{ruta_zip}" 2>NUL
rmdir /S /Q "!TEMP_EXTRACT!" 2>NUL

echo Iniciando nueva version de Kaya...
start "" "{ejecutable_relanzar}"
(goto) 2>nul & del "%~f0"
"""
    return bat


def descargar_archivo(url: str, destino: str, timeout: float = 30.0) -> bool:
    """Descarga un archivo con indicador de progreso basico."""
    req = urllib.request.Request(url, headers={"User-Agent": f"Kaya-Updater/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(destino, "wb") as f_out:
            bloque = 65536
            while True:
                chunk = resp.read(bloque)
                if not chunk:
                    break
                f_out.write(chunk)
        return True
    except Exception as exc:
        logger.error("Error al descargar paquete de actualizacion: %s", exc)
        return False


def lanzar_actualizacion_binaria(info_release: dict[str, Any]) -> tuple[bool, str]:
    """Descarga el ZIP, prepara el BAT y lo ejecuta para reemplazar el binario."""
    if not getattr(sys, "frozen", False):
        return False, "Kaya se ejecuta desde codigo fuente. No se reemplazaran archivos locales."

    exe_path = Path(sys.executable).resolve()
    dir_instalacion = exe_path.parent
    temp_dir = Path(tempfile.gettempdir())
    zip_destino = temp_dir / "Kaya_Windows.zip"
    bat_destino = temp_dir / "actualizar_kaya.bat"

    exito = descargar_archivo(info_release["url_zip"], str(zip_destino))
    if not exito:
        return False, "Fallo al descargar Kaya_Windows.zip desde GitHub Releases."

    contenido_bat = generar_script_bat(
        directorio_destino=str(dir_instalacion),
        ruta_zip=str(zip_destino),
        pid_esperar=os.getpid(),
        ejecutable_relanzar=str(exe_path),
    )
    with open(bat_destino, "w", encoding="ansi", errors="ignore") as f:
        f.write(contenido_bat)

    # Lanzar el BAT en segundo plano desvinculado
    os.spawnl(os.P_NOWAIT, os.environ.get("COMSPEC", "cmd.exe"), "cmd.exe", "/c", str(bat_destino))
    return True, "Actualizador iniciado con exito. Cerrando sesion actual..."


class DialogoActualizacion:
    """Ventana de dialogo PySide6 para ofrecer la actualizacion al usuario."""

    @staticmethod
    def mostrar(info: dict[str, Any], padre: Any = None) -> bool:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
        )

        dlg = QDialog(padre)
        dlg.setWindowTitle("Actualización Disponible - Kaya")
        dlg.setFixedSize(460, 320)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        dlg.setStyleSheet(
            """
            QDialog {
                background-color: #0b0f17;
                color: #e2e8f0;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel { color: #f8fafc; }
            QTextEdit {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton#btnCancelar {
                background-color: #334155;
                color: #94a3b8;
            }
            QPushButton#btnCancelar:hover { background-color: #475569; }
            """
        )

        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(20, 20, 20, 20)
        vbox.setSpacing(12)

        lbl_titulo = QLabel(f"<b>¡Nueva versión disponible! ({info['tag']})</b>")
        lbl_titulo.setStyleSheet("font-size: 14px; color: #38bdf8;")
        vbox.addWidget(lbl_titulo)

        lbl_sub = QLabel(
            f"Tu versión actual es <b>{VERSION}</b>. "
            "¿Deseas descargar e instalar la actualización ahora?"
        )
        lbl_sub.setWordWrap(True)
        vbox.addWidget(lbl_sub)

        if info.get("notas"):
            txt_notas = QTextEdit()
            txt_notas.setReadOnly(True)
            txt_notas.setPlainText(info["notas"][:1500])
            vbox.addWidget(txt_notas)

        lbl_info = QLabel("<i>Tus datos, claves (.env) y recuerdos se mantendrán intactos.</i>")
        lbl_info.setStyleSheet("font-size: 10px; color: #94a3b8;")
        vbox.addWidget(lbl_info)

        hbox = QHBoxLayout()
        btn_cancelar = QPushButton("Más tarde")
        btn_cancelar.setObjectName("btnCancelar")
        btn_actualizar = QPushButton("Actualizar ahora")

        btn_cancelar.clicked.connect(dlg.reject)
        btn_actualizar.clicked.connect(dlg.accept)

        hbox.addStretch()
        hbox.addWidget(btn_cancelar)
        hbox.addWidget(btn_actualizar)
        vbox.addLayout(hbox)

        return dlg.exec() == QDialog.Accepted


def _verificar_y_notificar(app_qt: Any) -> None:
    """Hilo secundario que consulta releases y emite senal a la UI si hay update."""
    time.sleep(3.0)  # Breve pausa para dejar que Kaya arranque completamente
    info = consultar_release_remoto()
    if not info:
        return

    if es_version_mayor(info["tag"], VERSION):
        logger.info("Nueva version detectada: %s (actual: %s)", info["tag"], VERSION)

        def _mostrar_y_proceder() -> None:
            if not DialogoActualizacion.mostrar(info):
                return
            if not getattr(sys, "frozen", False):
                logger.info("Entorno de desarrollo: no se reemplazan archivos locales.")
                return
            exito, msg = lanzar_actualizacion_binaria(info)
            if exito:
                # Cerrar aplicacion suavemente
                if hasattr(app_qt, "cerrar_sistema"):
                    app_qt.cerrar_sistema()
                else:
                    sys.exit(0)
            else:
                logger.error("No se pudo iniciar la actualizacion: %s", msg)

        # Enviar a la UI en el hilo principal de Qt
        if hasattr(app_qt, "cara") and hasattr(app_qt.cara, "root") and hasattr(app_qt.cara.root, "after"):
            app_qt.cara.root.after(0, _mostrar_y_proceder)
        elif hasattr(app_qt, "cola"):
            app_qt.cola.put(("actualizacion_disponible", _mostrar_y_proceder))
        elif hasattr(app_qt, "ventana"):
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, _mostrar_y_proceder)


def instalar(app_qt: Any) -> None:
    """Inicia el verificador de actualizaciones en un hilo daemon."""
    hilo = threading.Thread(
        target=_verificar_y_notificar,
        args=(app_qt,),
        name="ActualizadorKaya",
        daemon=True,
    )
    hilo.start()
