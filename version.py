"""version.py - Control de version y repositorio de Silvestra / Kaya."""

from __future__ import annotations

import subprocess
from pathlib import Path

VERSION = "1.0.2"


def _detectar_repo_github() -> str:
    """Detecta 'owner/repo' desde git remote origin o usa el valor predeterminado."""
    default_repo = "moisesdev507/Silvestra"
    try:
        git_dir = Path(__file__).resolve().parent / ".git"
        if not git_dir.exists():
            return default_repo
        salida = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        ).strip()
        # Formatos comunes:
        # https://github.com/moisesdev507/Silvestra.git
        # git@github.com:moisesdev507/Silvestra.git
        if "github.com" in salida:
            parte = salida.split("github.com")[-1].lstrip(":").lstrip("/")
            if parte.endswith(".git"):
                parte = parte[:-4]
            partes = parte.split("/")
            if len(partes) >= 2:
                return f"{partes[0]}/{partes[1]}"
    except Exception:
        pass
    return default_repo


REPO_GITHUB = _detectar_repo_github()
