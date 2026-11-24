"""Motor seguro de cálculo matemático local para Lyris (evaluación segura AST).

Verifica operaciones exactas, teoría de números, álgebra y estadística en < 50 ms.
"""
import ast
import math
import re
import statistics
from typing import Any, Optional

_MAX_EXP = 1000
_MAX_FAC = 1000

_FUNCIONES = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin,
    "acos": math.acos, "atan": math.atan, "sqrt": math.sqrt, "log": math.log,
    "log10": math.log10, "log2": math.log2, "exp": math.exp, "factorial": math.factorial,
    "gcd": math.gcd, "lcm": getattr(math, "lcm", math.gcd), "comb": getattr(math, "comb", None),
    "perm": getattr(math, "perm", None), "abs": abs, "round": round, "min": min, "max": max,
}
_CONSTANTES = {"pi": math.pi, "e": math.e, "tau": math.tau}

_NODOS = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UAdd, ast.USub, ast.List, ast.Tuple, ast.Load,
)


def _eval_nodo(n: ast.AST) -> Any:
    if isinstance(n, ast.Expression):
        return _eval_nodo(n.body)
    if isinstance(n, ast.Constant):
        if isinstance(n.value, (int, float, complex)):
            return n.value
        raise ValueError("Constante no numérica")
    if isinstance(n, ast.Name):
        nid = n.id.lower()
        if nid in _CONSTANTES:
            return _CONSTANTES[nid]
        raise ValueError(f"Identificador no permitido: {n.id}")
    if isinstance(n, ast.UnaryOp):
        v = _eval_nodo(n.operand)
        return +v if isinstance(n.op, ast.UAdd) else (-v if isinstance(n.op, ast.USub) else None)
    if isinstance(n, ast.BinOp):
        l, r = _eval_nodo(n.left), _eval_nodo(n.right)
        op = n.op
        if isinstance(op, ast.Add): return l + r
        if isinstance(op, ast.Sub): return l - r
        if isinstance(op, ast.Mult): return l * r
        if isinstance(op, ast.Div): return l / r
        if isinstance(op, ast.FloorDiv): return l // r
        if isinstance(op, ast.Mod): return l % r
        if isinstance(op, ast.Pow):
            if abs(r) > _MAX_EXP: raise ValueError("Exponente excede límite")
            return l ** r
        raise ValueError("Operador binario no permitido")
    if isinstance(n, ast.Call):
        if not isinstance(n.func, ast.Name): raise ValueError("Llamada no permitida")
        fn_name = n.func.id.lower()
        if fn_name not in _FUNCIONES or _FUNCIONES[fn_name] is None:
            raise ValueError(f"Función no permitida: {fn_name}")
        args = [_eval_nodo(a) for a in n.args]
        if fn_name == "factorial" and (not args or args[0] > _MAX_FAC):
            raise ValueError("Factorial excede límite")
        return _FUNCIONES[fn_name](*args)
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_eval_nodo(e) for e in n.elts]
    raise ValueError("Nodo no permitido")


def evaluar_expresion(expr: str) -> Any:
    """Evalúa de forma segura una expresión en string sin eval()."""
    if not expr or not isinstance(expr, str):
        raise ValueError("Expresión vacía")
    s = expr.strip()
    if "__" in s or ";" in s or "\\" in s:
        raise ValueError("Patrón inseguro")
    s = re.sub(r"(?<=\d|\))\s*\^\s*(?=\d|\()", "**", s)
    m_pct = re.match(r"^(\d+(?:\.\d+)?)\s*%\s*(?:de|\*)\s*(\d+(?:\.\d+)?)$", s, re.I)
    if m_pct:
        return (float(m_pct.group(1)) / 100.0) * float(m_pct.group(2))
    tree = ast.parse(s, mode="eval")
    for n in ast.walk(tree):
        if not isinstance(n, _NODOS):
            raise ValueError("AST no permitido")
    return _eval_nodo(tree.body)


def es_primo(n: int) -> bool:
    """Determina si n es primo exacto."""
    if not isinstance(n, int) or n < 2: return False
    if n in (2, 3): return True
    if n % 2 == 0 or n % 3 == 0: return False
    i, w = 5, 2
    while i * i <= n:
        if n % i == 0: return False
        i += w
        w = 6 - w
    return True


def factores_primos(n: int) -> list[int]:
    """Lista de factores primos de n con multiplicidad."""
    if not isinstance(n, int) or n < 2: return []
    res, d = [], 2
    while d * d <= n:
        while n % d == 0:
            res.append(d)
            n //= d
        d += 1 if d == 2 else 2
    if n > 1: res.append(n)
    return res


def divisores_primos(n: int) -> list[int]:
    """Divisores primos únicos de n."""
    return sorted(list(set(factores_primos(n))))


def determinante_matriz(matriz: list[list[float]]) -> float:
    """Determinante 2x2 y 3x3 en Python puro."""
    if not isinstance(matriz, (list, tuple)) or not matriz:
        raise ValueError("Matriz inválida")
    k = len(matriz)
    if any(len(f) != k for f in matriz): raise ValueError("Matriz no cuadrada")
    if k == 1: return float(matriz[0][0])
    if k == 2: return float(matriz[0][0] * matriz[1][1] - matriz[0][1] * matriz[1][0])
    if k == 3:
        a, b, c = matriz[0]; d, e, f = matriz[1]; g, h, i = matriz[2]
        return float(a*(e*i - f*h) - b*(d*i - f*g) + c*(d*h - e*g))
    raise ValueError("Solo 2x2 o 3x3")


def producto_escalar(v1: list[float], v2: list[float]) -> float:
    if len(v1) != len(v2) or not v1: raise ValueError("Dimensión incompatible")
    return float(sum(a * b for a, b in zip(v1, v2)))


def estadistica_rapida(datos: list[float]) -> dict:
    if not datos: raise ValueError("Datos vacíos")
    return {
        "promedio": statistics.mean(datos),
        "mediana": statistics.median(datos),
        "desviacion_estandar": statistics.stdev(datos) if len(datos) > 1 else 0.0,
    }


def _extraer_matriz(texto: str) -> Optional[list[list[float]]]:
    m = re.search(r"\[\s*(\[\s*[-0-9.,\s]+\s*\](?:\s*,\s*\[\s*[-0-9.,\s]+\s*\])*)\s*\]", texto)
    if m:
        try:
            p = ast.literal_eval(m.group(0))
            if isinstance(p, list) and all(isinstance(f, list) for f in p):
                return [[float(x) for x in f] for f in p]
        except Exception: pass
    return None


def precalcular_contexto(texto: str) -> str:
    """Extrae y calcula de forma segura operaciones numéricas o algebraicas exactas."""
    t = str(texto or "").strip()
    if not t: return ""
    try:
        # 1. Determinante
        if "determinante" in t.lower():
            mat = _extraer_matriz(t)
            if mat:
                det = determinante_matriz(mat)
                res_fmt = int(det) if det.is_integer() else round(det, 6)
                return (
                    "CÁLCULO VERIFICADO EN PYTHON LOCAL (usa este resultado exacto, no lo recalcules de cabeza):\n"
                    f"Determinante de la matriz {mat} = {res_fmt}"
                )
        # 2. Divisores / factores primos
        m_div = re.search(r"(?:divisores\s+primos|factores\s+primos)\s+(?:de\s+)?(\d+)", t, re.I)
        if m_div:
            n = int(m_div.group(1))
            if 2 <= n <= 10**12:
                f = factores_primos(n)
                u = sorted(list(set(f)))
                return (
                    "CÁLCULO VERIFICADO EN PYTHON LOCAL (usa este resultado exacto, no lo recalcules de cabeza):\n"
                    f"Descomposición en factores primos de {n}: {f} (divisores primos únicos: {u})"
                )
        # 3. Test de primalidad
        m_pri = re.search(r"(?:es\s+primo(?:\s+el)?\s+(\d+)|\b(\d+)\s+es\s+primo)\b", t, re.I)
        if m_pri:
            n = int(m_pri.group(1) or m_pri.group(2))
            if 0 <= n <= 10**12:
                veredicto = "SÍ es primo" if es_primo(n) else "NO es primo"
                return (
                    "CÁLCULO VERIFICADO EN PYTHON LOCAL (usa este resultado exacto, no lo recalcules de cabeza):\n"
                    f"El número {n} {veredicto}."
                )
        # 4. Porcentaje
        m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:de|\*)\s*(\d+(?:\.\d+)?)", t, re.I)
        if m_pct:
            p_raw, tot_raw = m_pct.group(1), m_pct.group(2)
            p, tot = float(p_raw), float(tot_raw)
            p_fmt = int(p) if p.is_integer() else p
            tot_fmt = int(tot) if tot.is_integer() else tot
            res = (p / 100.0) * tot
            res_fmt = int(res) if res.is_integer() else round(res, 6)
            return (
                "CÁLCULO VERIFICADO EN PYTHON LOCAL (usa este resultado exacto, no lo recalcules de cabeza):\n"
                f"{p_fmt}% de {tot_fmt} = {res_fmt}"
            )
        # 5. Expresiones aritméticas / funciones math
        pat = re.search(
            r"(?:cu[aá]nto\s+es|calcula|calculame|resolver|resuelve|operaci[oó]n:?)?\s*"
            r"([0-9\.\s\+\-\*\/\^\(\)]*(?:sqrt|log|exp|sin|cos|tan|factorial)\s*\([0-9\.\s\+\-\*\/\^a-z]+\)"
            r"[0-9\.\s\+\-\*\/\^\(\)]*|[0-9\.]+\s*[\+\-\*\/\^]\s*[0-9\.\s\+\-\*\/\^\(\)]+)",
            t, re.I)
        if pat:
            cand = pat.group(1).strip().rstrip("?.,; ")
            if any(c.isdigit() for c in cand) and len(cand) >= 3:
                res = evaluar_expresion(cand)
                if isinstance(res, (int, float)):
                    res_fmt = int(res) if isinstance(res, float) and res.is_integer() else (round(res, 8) if isinstance(res, float) else res)
                    return (
                        "CÁLCULO VERIFICADO EN PYTHON LOCAL (usa este resultado exacto, no lo recalcules de cabeza):\n"
                        f"{cand} = {res_fmt}"
                    )
    except Exception:
        pass
    return ""
