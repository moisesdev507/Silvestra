"""Script ejecutable de consola para Kaya Gemini Live.

Utiliza el motor modular kaya_live_nucleo.py con voz Achernar y herramientas de PC.
"""
import argparse
import asyncio
import sys
import traceback

import kaya_live_nucleo


def main():
    parser = argparse.ArgumentParser(description="Kaya Gemini Live - Asistente por voz nativa bidireccional.")
    parser.add_argument("--modelo", default=kaya_live_nucleo.MODELO_DEFECTO, help=f"Modelo Gemini Live (defecto: {kaya_live_nucleo.MODELO_DEFECTO})")
    parser.add_argument("--voz", default=kaya_live_nucleo.VOZ_DEFECTO, help=f"Voz predefinida (defecto: {kaya_live_nucleo.VOZ_DEFECTO})")
    parser.add_argument("--silencio", type=float, default=kaya_live_nucleo.TIMEOUT_SILENCIO_DEFECTO, help=f"Segundos de silencio para auto-reposo (defecto: {kaya_live_nucleo.TIMEOUT_SILENCIO_DEFECTO})")
    parser.add_argument("--verificar", action="store_true", help="Solo valida la conexión con Gemini Live API y las herramientas")
    args = parser.parse_args()

    sesion = kaya_live_nucleo.SesionKayaLive(
        modelo=args.modelo,
        voz=args.voz,
        timeout_silencio=args.silencio,
    )

    try:
        asyncio.run(sesion.ejecutar(solo_verificar=args.verificar))
    except KeyboardInterrupt:
        print("\n[LIVE] Sesión finalizada por el usuario. ¡Hasta luego!", flush=True)
    except Exception as e:
        print(f"\n[LIVE] Error en ejecución: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
