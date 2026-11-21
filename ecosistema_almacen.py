"""Persistencia atómica independiente para credenciales y dispositivos del ecosistema."""
from copy import deepcopy
from pathlib import Path
import json, os, tempfile, threading


class AlmacenEcosistema:
    def __init__(self, ruta=None):
        self.ruta = Path(ruta) if ruta else Path(__file__).with_name("ecosistema_dispositivos.json")
        self._lock = threading.RLock()

    def cargar(self):
        with self._lock:
            if not self.ruta.exists():
                return {"version": 1, "dispositivos": {}, "emparejamientos": {}, "preferencias": {}}
            try:
                data = json.loads(self.ruta.read_text(encoding="utf-8"))
                if (not isinstance(data, dict) or data.get("version") != 1 or
                        not isinstance(data.get("dispositivos"), dict) or
                        not isinstance(data.get("emparejamientos"), dict)):
                    raise ValueError("esquema de almacén inválido")
                data.setdefault("preferencias", {})
                if not isinstance(data["preferencias"], dict): raise ValueError("preferencias inválidas")
                return deepcopy(data)
            except Exception as exc:
                raise ValueError("almacén del ecosistema ilegible; no se sobrescribió") from exc

    def guardar(self, data):
        if (not isinstance(data, dict) or data.get("version") != 1 or
                not isinstance(data.get("dispositivos"), dict) or
                not isinstance(data.get("emparejamientos"), dict) or
                not isinstance(data.get("preferencias", {}), dict)):
            raise ValueError("esquema de almacén inválido")
        with self._lock:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            tmp = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.ruta.parent,
                                                 prefix=".ecosistema-", suffix=".tmp", delete=False) as f:
                    tmp = f.name
                    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
                    f.flush(); os.fsync(f.fileno())
                os.replace(tmp, self.ruta)
                return True
            except Exception:
                if tmp and os.path.exists(tmp):
                    try: os.remove(tmp)
                    except OSError: pass
                return False

    def actualizar(self, mutador):
        with self._lock:
            data = self.cargar()
            result = mutador(data)
            if not self.guardar(data):
                raise OSError("no se pudo persistir el almacén del ecosistema")
            return result
