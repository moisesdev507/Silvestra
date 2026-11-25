"""Telemetría local instantánea J.A.R.V.I.S.: sin red y sin bloquear la UI.
Reutiliza pantalla_remota_datos (CPU/RAM/batería Win32); usa psutil si existe.
"""
import os
import re
import time

try:
    import psutil
except ImportError:
    psutil = None

U = (os.environ.get("SystemDrive") or "C:") + os.sep
GB, MB = 1073741824.0, 1048576.0
IGN = {"system idle process", "system", "registry", "smss.exe", "csrss.exe",
       "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "dwm.exe",
       "conhost.exe", "sihost.exe", "runtimebroker.exe", "searchindexer.exe"}
CON = ("que es ", "como funciona", "explica", "define", "diferencia entre",
       "para que sirve", "sirve para", "teoria")


def norm(t):
    from pantalla_remota_accion import normalizar_texto
    return normalizar_texto(t)


def limpio(n):
    n = str(n or "").strip()
    return n[:-4] if n.lower().endswith(".exe") else n


def _palabra(texto, *terminos):
    """Coincide solo con palabras/frases completas: 'ram' no debe estar en 'programacion'."""
    patron = r"\b(?:" + "|".join(re.escape(t) for t in terminos) + r")\b"
    return bool(re.search(patron, texto))


def estado_bateria():
    if psutil is not None:
        try:
            b = psutil.sensors_battery()
            if b is not None:
                s = getattr(b, "secsleft", None)
                if s in (getattr(psutil, "POWER_TIME_UNLIMITED", -1),
                         getattr(psutil, "POWER_TIME_UNKNOWN", -2)):
                    s = None
                return {"disponible": True, "porcentaje": int(round(b.percent)),
                        "cargando": bool(b.power_plugged), "segundos_restantes": s}
        except Exception:
            pass
    try:
        import pantalla_remota_datos as p
        _, _, b = p.obtener_telemetria_hardware()
        return {"disponible": bool(b.get("disponible")),
                "porcentaje": int(b.get("porcentaje", 0)),
                "cargando": bool(b.get("cargando")), "segundos_restantes": None}
    except Exception:
        return {"disponible": False, "porcentaje": 0, "cargando": False,
                "segundos_restantes": None}


def metricas():
    if psutil is not None:
        try:
            return (int(psutil.cpu_percent(interval=None)),
                    int(psutil.virtual_memory().percent))
        except Exception:
            pass
    try:
        import pantalla_remota_datos as p
        c, r, _ = p.obtener_telemetria_hardware()
        return int(c), int(r)
    except Exception:
        return 0, 0


def ram_gb():
    if psutil is not None:
        try:
            v = psutil.virtual_memory()
            return v.used / GB, v.total / GB
        except Exception:
            pass
    try:
        import ctypes
        import pantalla_remota_datos as p
        s = p._MEMORYSTATUSEX()
        s.dwLength = ctypes.sizeof(s)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            tot = s.ullTotalPhys / GB
            return tot - (s.ullAvailPhys / GB), tot
    except Exception:
        pass
    return None, None


def estado_sistema():
    c, r = metricas()
    if c == 0:
        time.sleep(0.05)
        c2, _ = metricas()
        c = c2 or c
    u, t = ram_gb()
    b = estado_bateria()
    rt = f"{u:.1f} de {t:.1f} GB ({r}%)" if u is not None else f"al {r}%"
    bt = (f" Batería al {b['porcentaje']}%{', cargando' if b['cargando'] else ''}."
          if b["disponible"] else " Sin batería detectada, en corriente.")
    return {"cpu": c, "ram_pct": r, "ram_usada_gb": u, "ram_total_gb": t,
            "bateria": b, "texto": f"CPU al {c}%, RAM {rt}.{bt}"}


def estado_disco():
    try:
        import shutil
        d = shutil.disk_usage(U)
        return {"unidad": U, "libre_gb": d.free / GB, "total_gb": d.total / GB,
                "usado_pct": int(round(d.used * 100.0 / max(1, d.total)))}
    except Exception:
        return {"unidad": U, "libre_gb": None, "total_gb": None, "usado_pct": None}


def proc_win(top):
    import ctypes
    from ctypes import wintypes as w

    class E(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("use", w.DWORD), ("pid", w.DWORD),
                    ("heap", ctypes.c_void_p), ("mod", w.DWORD), ("thr", w.DWORD),
                    ("par", w.DWORD), ("pri", ctypes.c_long), ("flg", w.DWORD),
                    ("exe", ctypes.c_wchar * 260)]

    class M(ctypes.Structure):
        _fields_ = [("cb", w.DWORD), ("flt", w.DWORD), ("pk", ctypes.c_size_t),
                    ("ws", ctypes.c_size_t), ("q1", ctypes.c_size_t),
                    ("q2", ctypes.c_size_t), ("q3", ctypes.c_size_t),
                    ("q4", ctypes.c_size_t), ("pf", ctypes.c_size_t),
                    ("pf2", ctypes.c_size_t)]

    k, p = ctypes.windll.kernel32, ctypes.windll.Psapi
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    p.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(M), w.DWORD]
    s = k.CreateToolhelp32Snapshot(2, 0)
    if s == -1:
        return []
    o, e = [], E()
    e.size = ctypes.sizeof(e)
    try:
        if not k.Process32FirstW(s, ctypes.byref(e)):
            return []
        while True:
            n, pid = str(e.exe), int(e.pid)
            if pid > 4 and n.lower() not in IGN:
                h = k.OpenProcess(0x0410, False, pid)  # QUERY_INFO | VM_READ
                if h:
                    try:
                        m = M()
                        m.cb = ctypes.sizeof(m)
                        if p.GetProcessMemoryInfo(h, ctypes.byref(m), m.cb):
                            o.append((limpio(n), round(m.ws / MB, 1)))
                    finally:
                        k.CloseHandle(h)
            if not k.Process32NextW(s, ctypes.byref(e)):
                break
    except Exception:
        pass
    finally:
        k.CloseHandle(s)
    return sorted(o, key=lambda x: x[1], reverse=True)[:top]


def procesos_pesados(top=3):
    top = max(1, min(5, int(top or 3)))
    if psutil is not None:
        try:
            o = []
            for x in psutil.process_iter(["name", "memory_info"]):
                try:
                    i = x.info
                    n = str(i.get("name") or "")
                    if n.lower() in IGN:
                        continue
                    rss = getattr(i.get("memory_info"), "rss", 0) or 0
                    o.append((limpio(n), round(float(rss) / MB, 1)))
                except Exception:
                    continue
            return sorted(o, key=lambda x: x[1], reverse=True)[:top]
        except Exception:
            pass
    try:
        return proc_win(top)
    except Exception:
        return []


def responder_telemetria(texto):
    t = norm(texto)
    if not t or any(c in t for c in CON):
        return None
    if (any(c in t for c in ("consumiendo", "trabando", "ralentiza", "procesos"))
            or _palabra(t, "usa mas", "mas memoria", "mas cpu")):
        ps = procesos_pesados(3)
        if not ps:
            return "No veo procesos pesados en este momento."
        lista = ", ".join(f"{n} ({m} MB)" for n, m in ps)
        return f"Los que más RAM están usando ahora: {lista}."
    if "bateria" in t:
        b = estado_bateria()
        if not b["disponible"]:
            return "No detecto batería; la laptop está en corriente."
        extra = ""
        if b["segundos_restantes"] and not b["cargando"]:
            mins = max(1, int(b["segundos_restantes"] // 60))
            extra = f" Te quedan unos {mins} minutos."
        return (f"Batería al {b['porcentaje']}%, "
                f"{'cargando' if b['cargando'] else 'descargando'}.{extra}")
    if any(c in t for c in ("disco", "almacenamiento", "espacio", "unidad c", "ssd")):
        d = estado_disco()
        if d["libre_gb"] is None:
            return "No pude leer el espacio del disco ahora."
        return (f"En la unidad principal tienes {d['libre_gb']:.0f} GB libres de "
                f"{d['total_gb']:.0f} GB, {d['usado_pct']}% ocupado.")
    if _palabra(t, "laptop", "sistema", "ram", "memoria", "cpu",
                "procesador", "como va", "compu", "computador", "computadora", "pc"):
        return estado_sistema()["texto"]
    return None
