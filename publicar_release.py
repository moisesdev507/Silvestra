"""publicar_release.py - Publicador automatizado de Releases en GitHub para Silvestra / Kaya."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

import version

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist_exe"


class LectorProgreso:
    """Lector de archivo en bloques para streaming con indicador de porcentaje."""

    def __init__(self, ruta: Path, callback: Optional[Callable[[int, int], None]] = None) -> None:
        self.ruta = ruta
        self._f = open(ruta, "rb")
        self.total = os.path.getsize(ruta)
        self.leido = 0
        self.callback = callback

    def read(self, size: int = 65536) -> bytes:
        bloque = self._f.read(size)
        if bloque:
            self.leido += len(bloque)
            if self.callback:
                self.callback(self.leido, self.total)
        return bloque

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> LectorProgreso:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def verificar_gh_disponible() -> bool:
    """Verifica si el binario 'gh' esta instalado y autenticado."""
    if not shutil.which("gh"):
        return False
    try:
        res = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False


def obtener_token_git() -> Optional[str]:
    """Obtiene el token de GitHub desde variables de entorno o Git Credential Manager."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        val = os.environ.get(var)
        if val:
            return val.strip()

    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            for linea in proc.stdout.splitlines():
                if linea.startswith("password="):
                    return linea.split("=", 1)[1].strip()
    except Exception as exc:
        print(f"[release] Aviso al consultar git credential: {exc}", flush=True)

    return None


def api_request(
    url: str,
    token: str,
    metodo: str = "GET",
    datos: Optional[dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Any:
    """Realiza una solicitud REST a la API de GitHub."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": f"Silvestra-Publisher/{version.VERSION}",
    }
    cuerpo = None
    if datos is not None:
        cuerpo = json.dumps(datos).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    req = urllib.request.Request(url, data=cuerpo, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 204:
                return {}
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        detalles = ""
        try:
            detalles = he.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        if he.code not in (404,):
            print(f"[release] Error HTTP {he.code} en {url}: {detalles}", flush=True)
        raise


def limpiar_borradores(repo: str, token: str, tag_objetivo: str) -> None:
    """Elimina borradores huerfanos o releases previos incompletos para el tag."""
    url = f"https://api.github.com/repos/{repo}/releases"
    try:
        releases = api_request(url, token)
        for rel in releases:
            rel_id = rel.get("id")
            es_borrador = rel.get("draft", False)
            tag_rel = rel.get("tag_name", "")
            if es_borrador or (tag_rel == tag_objetivo and not rel.get("published_at")):
                print(f"[release] Eliminando release previo/borrador (ID {rel_id}, tag: '{tag_rel}')...", flush=True)
                api_request(f"{url}/{rel_id}", token, metodo="DELETE")
    except Exception as e:
        print(f"[release] Aviso al verificar borradores: {e}", flush=True)


def asegurar_release(
    repo: str,
    tag: str,
    titulo: str,
    notas: str,
    token: str,
) -> dict[str, Any]:
    """Crea o actualiza el release en GitHub marcandolo como Latest."""
    base_url = f"https://api.github.com/repos/{repo}/releases"

    # Verificar si ya existe un release con ese tag
    try:
        rel_existente = api_request(f"{base_url}/tags/{tag}", token)
        if rel_existente and "id" in rel_existente:
            print(f"[release] Release '{tag}' existente detectado (ID: {rel_existente['id']}). Actualizando...", flush=True)
            payload = {
                "name": titulo,
                "body": notas,
                "draft": False,
                "prerelease": False,
                "make_latest": "true",
            }
            return api_request(f"{base_url}/{rel_existente['id']}", token, metodo="PATCH", datos=payload)
    except urllib.error.HTTPError as he:
        if he.code != 404:
            print(f"[release] Consulta de tag devolvio HTTP {he.code}", flush=True)

    # Crear nuevo release
    print(f"[release] Creando nuevo Release '{tag}' en {repo}...", flush=True)
    payload = {
        "tag_name": tag,
        "name": titulo,
        "body": notas,
        "draft": False,
        "prerelease": False,
        "make_latest": "true",
    }
    return api_request(base_url, token, metodo="POST", datos=payload)


def subir_con_curl(upload_url: str, ruta_archivo: Path, token: str) -> bool:
    """Sube el asset utilizando curl.exe con streaming binario y barra de progreso."""
    content_type = "application/zip" if str(ruta_archivo).endswith(".zip") else "application/octet-stream"
    cmd = [
        "curl.exe",
        "-f",
        "-L",
        "-#",
        "-X", "POST",
        "-H", f"Authorization: Bearer {token}",
        "-H", f"Content-Type: {content_type}",
        "--data-binary", f"@{ruta_archivo}",
        upload_url,
    ]
    tam_mb = os.path.getsize(ruta_archivo) / (1024 * 1024)
    print(f"[release] Subiendo {ruta_archivo.name} ({tam_mb:.1f} MB) via curl...", flush=True)
    try:
        res = subprocess.run(cmd)
        if res.returncode == 0:
            print(f"OK: {ruta_archivo.name} subido exitosamente via curl.", flush=True)
            return True
        print(f"[release] curl retorno codigo {res.returncode}", flush=True)
    except Exception as e:
        print(f"[release] Error ejecutando curl: {e}", flush=True)
    return False


def limpiar_assets_invalidos_o_previos(
    release: dict[str, Any],
    nombre_nuevo: str,
    token: str,
) -> None:
    """Elimina assets en estado distinto de 'uploaded' o con el mismo nombre a subir."""
    repo_url = release.get("url", "")
    base_api = repo_url.split("/releases/")[0]
    rel_id = release.get("id")
    try:
        rel_actual = api_request(f"{base_api}/releases/{rel_id}", token)
        assets = rel_actual.get("assets", [])
    except Exception:
        assets = release.get("assets", [])

    for asset in assets:
        asset_id = asset.get("id")
        asset_name = asset.get("name", "")
        asset_state = str(asset.get("state", "")).lower()

        debe_eliminar = False
        razon = ""
        if asset_state != "uploaded":
            debe_eliminar = True
            razon = f"estado incompleto ('{asset_state}')"
        elif asset_name == nombre_nuevo:
            debe_eliminar = True
            razon = f"reemplazo de archivo '{asset_name}'"

        if debe_eliminar:
            print(f"[release] Eliminando asset previo '{asset_name}' (ID: {asset_id}, {razon})...", flush=True)
            try:
                del_url = f"{base_api}/releases/assets/{asset_id}"
                api_request(del_url, token, metodo="DELETE")
            except Exception as exc:
                print(f"[release] Aviso eliminando asset previo: {exc}", flush=True)


def subir_archivo_asset(
    release: dict[str, Any],
    ruta_archivo: Path,
    token: str,
) -> bool:
    """Sube un archivo como asset al release con barra de progreso en consola."""
    if not ruta_archivo.exists():
        print(f"[release] Error: archivo no encontrado: {ruta_archivo}", flush=True)
        return False

    nombre = ruta_archivo.name
    tamano = os.path.getsize(ruta_archivo)
    tamano_mb = tamano / (1024 * 1024)

    # Limpiar cualquier asset en estado no 'uploaded' o previo con el mismo nombre
    limpiar_assets_invalidos_o_previos(release, nombre, token)

    upload_url_tpl = release.get("upload_url", "")
    upload_url = upload_url_tpl.split("{")[0] + f"?name={nombre}"

    # Preferir curl.exe para archivos grandes si esta disponible
    if shutil.which("curl.exe") or shutil.which("curl"):
        if subir_con_curl(upload_url, ruta_archivo, token):
            return True
        print("[release] Reintentando subida via urllib...", flush=True)

    print(f"[release] Subiendo {nombre} ({tamano_mb:.1f} MB) via urllib...", flush=True)
    t0 = time.time()

    ultimo_pct = [-1]

    def _progreso(leido: int, total: int) -> None:
        pct = int((leido / total) * 100) if total > 0 else 0
        if pct != ultimo_pct[0] and pct % 5 == 0:
            ultimo_pct[0] = pct
            leido_mb = leido / (1024 * 1024)
            dt = max(time.time() - t0, 0.001)
            mbps = (leido / (1024 * 1024)) / dt
            print(f"[release] {nombre}: {pct}% ({leido_mb:.1f}/{tamano_mb:.1f} MB) a {mbps:.2f} MB/s", flush=True)

    content_type = "application/zip" if nombre.endswith(".zip") else "application/octet-stream"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "Content-Length": str(tamano),
        "User-Agent": f"Silvestra-Publisher/{version.VERSION}",
    }

    try:
        with LectorProgreso(ruta_archivo, callback=_progreso) as lector:
            req = urllib.request.Request(upload_url, data=lector, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=1800) as resp:
                if resp.status in (200, 201):
                    dt_total = time.time() - t0
                    print(f"OK: {nombre} subido exitosamente en {dt_total:.1f}s.", flush=True)
                    return True
                print(f"[release] Aviso: respuesta HTTP {resp.status} al subir asset.", flush=True)
    except Exception as e:
        print(f"[release] Error subiendo {nombre}: {e}", flush=True)
        return False

    return False


def publicar(
    ver: Optional[str] = None,
    titulo: Optional[str] = None,
    notas: Optional[str] = None,
    archivos: Optional[list[Path]] = None,
) -> bool:
    """Flujo principal de publicacion de release."""
    v = (ver or version.VERSION).strip()
    tag = v if v.startswith("v") else f"v{v}"
    title = titulo or f"Kaya {tag}"
    notes = notas or "Sincroniza retorno a reposo azul y auto-actualizacion"
    repo = version.REPO_GITHUB

    if archivos is None:
        archivos = []
        zip_path = DIST_DIR / "Kaya_Windows.zip"
        if zip_path.exists():
            archivos.append(zip_path)

    print(f"=== PUBLICANDO RELEASE {tag} ({repo}) ===", flush=True)

    # 1. Intentar con GitHub CLI si esta autenticado
    if verificar_gh_disponible():
        print("[release] Utilizando GitHub CLI ('gh')...", flush=True)
        cmd = [
            "gh", "release", "create", tag,
            "--title", title,
            "--notes", notes,
            "--latest",
        ]
        for a in archivos:
            cmd.append(str(a))
        try:
            res = subprocess.run(cmd, check=True)
            print("OK: Release publicado con exito via gh.", flush=True)
            return True
        except subprocess.CalledProcessError as cpe:
            print(f"[release] gh fallo con codigo {cpe.returncode}. Pasando a API REST...", flush=True)

    # 2. Respaldo: API REST con credenciales de Git Credential Manager
    print("[release] Obteniendo token de GitHub desde Git Credential Manager...", flush=True)
    token = obtener_token_git()
    if not token:
        print("[release] Error: No se pudo obtener token de GitHub.", flush=True)
        return False

    limpiar_borradores(repo, token, tag)
    rel = asegurar_release(repo, tag, title, notes, token)
    if not rel or "id" not in rel:
        print(f"[release] Error: no se pudo obtener o crear el release '{tag}'.", flush=True)
        return False

    exito = True
    for a in archivos:
        ok = subir_archivo_asset(rel, a, token)
        if not ok:
            exito = False

    if exito:
        print(f"OK: Release {tag} publicado con exito en https://github.com/{repo}/releases/tag/{tag}", flush=True)
    return exito


def main() -> None:
    parser = argparse.ArgumentParser(description="Publicador de Releases de Kaya")
    parser.add_argument("--version", dest="ver", default=None, help="Version (ej: 1.0.2)")
    parser.add_argument("--title", dest="title", default=None, help="Titulo del release")
    parser.add_argument("--notes", dest="notes", default=None, help="Notas del release")
    parser.add_argument("archivos", nargs="*", help="Archivos a subir (por defecto dist_exe/Kaya_Windows.zip)")
    args = parser.parse_args()

    archivos_path = [Path(a) for a in args.archivos] if args.archivos else None
    ok = publicar(ver=args.ver, titulo=args.title, notas=args.notes, archivos=archivos_path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
