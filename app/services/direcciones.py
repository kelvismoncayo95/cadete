"""Texto de direcciones: normalizar lo que escribe la gente y separar calle, número y esquina.

Es código puro (sin base de datos) para poder usarlo también en el cargador de datos (geocoder/cargar.py):
los nombres de las calles se normalizan IGUAL al cargarlos y al buscarlos.
"""
import re
import unicodedata

ABREVIATURAS = {
    "av": "avenida", "avda": "avenida", "bv": "bulevar", "bvar": "bulevar", "blvr": "bulevar",
    "gral": "general", "cnel": "coronel", "dr": "doctor", "dra": "doctora", "pte": "presidente",
    "cap": "capitan", "tte": "teniente", "brig": "brigadier", "ing": "ingeniero", "arq": "arquitecto",
    "prof": "profesor", "gob": "gobernador", "cmte": "comandante", "sgto": "sargento", "psje": "pasaje",
}
RELLENO_DEL_NUMERO = {"n", "nro", "num", "numero", "no"}   # «Colonia nº 1234», «Rondeau nro. 1571»


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos, con las abreviaturas expandidas y sin la palabra «calle» inicial."""
    t = unicodedata.normalize("NFD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    palabras = re.sub(r"[^a-z0-9]+", " ", t).split()
    palabras = [ABREVIATURAS.get(p, p) for p in palabras]
    if len(palabras) > 1 and palabras[0] == "calle":
        palabras = palabras[1:]
    return " ".join(palabras)


def parsear(texto: str) -> tuple[str, int | None, str | None]:
    """(calle, número, otra calle). «Av. 18 de Julio 1500» → número; «Colonia esq. Ejido» → esquina."""
    t = normalizar(texto)
    m = re.match(r"^(.*?)\s+(\d{1,5})$", t)
    if m:
        calle = m.group(1).split()
        while calle and calle[-1] in RELLENO_DEL_NUMERO:
            calle.pop()
        if calle:
            return " ".join(calle), int(m.group(2)), None
    partes = re.split(r"\s+(?:esq|esquina|y)\s+", t, maxsplit=1)
    if len(partes) == 2 and partes[0] and partes[1]:
        return partes[0], None, partes[1]
    return t, None, None
