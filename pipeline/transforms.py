"""Transformaciones puras (pandas) del pipeline TFM Embalses.

Sin dependencias de Spark ni de Databricks: se prueban en local con `pytest tests/`.
Los notebooks de `pipeline/` se encargan solo de leer y escribir tablas.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Esquemas esperados en origen (control de cambios de nombre de columna)
# --------------------------------------------------------------------------
MITECO_COLUMNAS = ["FECHA", "AMBITO_NOMBRE", "EMBALSE_NOMBRE", "AGUA_TOTAL", "AGUA_ACTUAL", "ELECTRICO_FLAG"]
AEMET_COLUMNAS = ["fecha", "indicativo", "prec", "tmax", "tmin", "tmed"]

FUENTES_PERMITIDAS = {"miteco_bd_embalses", "aemet_opendata"}


def check_schema(columnas: list[str], esperadas: list[str]) -> dict:
    """Compara las columnas recibidas con las esperadas.

    Devuelve las que faltan y las nuevas. Si falta alguna esperada, el pipeline
    debe parar esa fuente: es el síntoma típico de un cambio de nombre en origen.
    """
    recibidas = set(columnas)
    return {
        "faltan": sorted(set(esperadas) - recibidas),
        "nuevas": sorted(recibidas - set(esperadas)),
        "ok": set(esperadas).issubset(recibidas),
    }


# --------------------------------------------------------------------------
# Parseo de números en formato español
# --------------------------------------------------------------------------
_NUM_ES = re.compile(r"^-?[\d.]*,\d+$|^-?\d{1,3}(\.\d{3})+$")


def parse_decimal_es(valor) -> float:
    """Convierte '1.319,5' -> 1319.5, '308,00' -> 308.0, '13.2' -> 13.2.

    Devuelve NaN si el valor no es numérico. 'Ip' (precipitación inapreciable)
    NO se trata aquí: ver `parse_precipitacion`.
    """
    if valor is None:
        return math.nan
    if isinstance(valor, (int, float, np.integer, np.floating)):
        return float(valor)
    s = str(valor).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return math.nan
    if "," in s or _NUM_ES.match(s):
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return math.nan


def parse_precipitacion(valor) -> tuple[float, bool]:
    """AEMET publica 'Ip' para precipitación inapreciable (< 0,1 mm).

    Se convierte a 0,0 mm y se marca con una bandera para no perder la información.
    'Acum' (dato acumulado de varios días) se deja como NaN: no es un valor diario.
    """
    if isinstance(valor, str) and valor.strip().lower() == "ip":
        return 0.0, True
    return parse_decimal_es(valor), False


# --------------------------------------------------------------------------
# Normalización + reglas de calidad (aceptado / revisión / rechazado)
# --------------------------------------------------------------------------
def _clasificar(df: pd.DataFrame, reglas: list[tuple[str, str, pd.Series]]) -> pd.DataFrame:
    """Aplica reglas en orden. Cada regla: (estado, motivo, máscara de fallo).

    La primera regla que falla decide el estado de la fila. 'rechazado' tiene
    prioridad sobre 'revision' porque las reglas se pasan en ese orden.
    """
    df = df.copy()
    df["estado"] = "aceptado"
    df["motivo"] = None
    for estado, motivo, mascara in reglas:
        sel = mascara.fillna(True) & (df["estado"] == "aceptado")
        df.loc[sel, "estado"] = estado
        df.loc[sel, "motivo"] = motivo
    return df


def normalizar_miteco(raw: pd.DataFrame) -> pd.DataFrame:
    """Bronze MITECO (strings) -> esquema silver con estado de calidad."""
    df = pd.DataFrame(
        {
            "embalse": raw["EMBALSE_NOMBRE"].astype("string").str.strip(),
            "cuenca": raw["AMBITO_NOMBRE"].astype("string").str.strip(),
            "fecha": pd.to_datetime(raw["FECHA"], errors="coerce").dt.date,
            "capacidad_hm3": raw["AGUA_TOTAL"].map(parse_decimal_es),
            "volumen_hm3": raw["AGUA_ACTUAL"].map(parse_decimal_es),
            "electrico": raw["ELECTRICO_FLAG"].map(parse_decimal_es).fillna(0).astype(int) == 1,
        }
    )
    for col in [c for c in raw.columns if c.startswith("_")]:
        df[col] = raw[col].values
    df["pct_capacidad"] = (df["volumen_hm3"] / df["capacidad_hm3"] * 100).round(2)

    reglas = [
        ("rechazado", "fecha nula o no parseable", df["fecha"].isna()),
        ("rechazado", "embalse nulo", df["embalse"].isna() | (df["embalse"] == "")),
        ("rechazado", "capacidad no numérica o <= 0", ~(df["capacidad_hm3"] > 0)),
        ("rechazado", "volumen no numérico o negativo", ~(df["volumen_hm3"] >= 0)),
        ("revision", "volumen supera la capacidad", df["volumen_hm3"] > df["capacidad_hm3"]),
    ]
    return _clasificar(df, reglas)


def normalizar_aemet(raw: pd.DataFrame) -> pd.DataFrame:
    """Bronze AEMET (strings) -> esquema silver con estado de calidad."""
    prec = raw["prec"].map(parse_precipitacion)
    df = pd.DataFrame(
        {
            "estacion_id": raw["indicativo"].astype("string").str.strip(),
            "fecha": pd.to_datetime(raw["fecha"], errors="coerce").dt.date,
            "prec_mm": prec.map(lambda t: t[0]),
            "prec_inapreciable": prec.map(lambda t: t[1]),
            "tmax": raw["tmax"].map(parse_decimal_es),
            "tmin": raw["tmin"].map(parse_decimal_es),
            "tmed": raw["tmed"].map(parse_decimal_es),
        }
    )
    for col in [c for c in raw.columns if c.startswith("_")]:
        df[col] = raw[col].values

    reglas = [
        ("rechazado", "fecha nula o no parseable", df["fecha"].isna()),
        ("rechazado", "tmed no numérica", df["tmed"].isna()),
        ("rechazado", "temperatura fuera de rango físico (-30..50 ºC)",
         ~df["tmed"].between(-30, 50) | ~df["tmax"].fillna(0).between(-30, 50) | ~df["tmin"].fillna(0).between(-30, 50)),
        ("rechazado", "precipitación negativa", df["prec_mm"] < 0),
        ("revision", "tmin mayor que tmax", df["tmin"] > df["tmax"]),
        ("revision", "precipitación no numérica (p. ej. 'Acum')", df["prec_mm"].isna()),
        ("revision", "precipitación diaria > 150 mm", df["prec_mm"] > 150),
    ]
    return _clasificar(df, reglas)


def dedup_ultima_ingesta(df: pd.DataFrame, claves: list[str], orden: str = "_ingest_ts") -> pd.DataFrame:
    """Una fila por clave: la de la ingesta más reciente (criterio explícito).

    Sustituye al dropDuplicates arbitrario del pipeline heredado (hallazgo 6).
    """
    if df.empty:
        return df
    return (
        df.sort_values(orden, ascending=False, kind="mergesort")
        .drop_duplicates(subset=claves, keep="first")
        .sort_values(claves)
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------
# Indicador de campaña vitícola
# --------------------------------------------------------------------------
MESES_CAMPANA = range(4, 11)  # 1 de abril a 31 de octubre (ciclo vegetativo, hemisferio norte)
DIAS_CAMPANA = 214


def grados_dia_winkler(tmed: pd.Series) -> float:
    """Índice de Winkler: suma de max(tmed - 10 ºC, 0) en el periodo."""
    return float((tmed - 10).clip(lower=0).sum())


def campana_vitivinicola(clima: pd.DataFrame, reserva: pd.DataFrame) -> pd.DataFrame:
    """Indicadores por campaña (abril-octubre).

    clima:   silver AEMET aceptado (fecha, prec_mm, tmed)
    reserva: reserva agregada de la cuenca (fecha, pct_capacidad)
    """
    c = clima.copy()
    c["fecha"] = pd.to_datetime(c["fecha"])
    c = c[c["fecha"].dt.month.isin(MESES_CAMPANA)]
    c["anyo"] = c["fecha"].dt.year
    clima_anual = c.groupby("anyo").agg(
        lluvia_campana_mm=("prec_mm", "sum"),
        winkler_gdd=("tmed", grados_dia_winkler),
        dias_con_dato=("tmed", "count"),
    )
    clima_anual["completitud_pct"] = (clima_anual["dias_con_dato"] / DIAS_CAMPANA * 100).round(1)

    r = reserva.copy()
    r["fecha"] = pd.to_datetime(r["fecha"])
    r = r[r["fecha"].dt.month.isin(MESES_CAMPANA)]
    r["anyo"] = r["fecha"].dt.year
    reserva_anual = r.groupby("anyo").agg(reserva_media_pct=("pct_capacidad", "mean"))

    out = clima_anual.join(reserva_anual, how="outer").reset_index()
    out["lluvia_campana_mm"] = out["lluvia_campana_mm"].round(1)
    out["winkler_gdd"] = out["winkler_gdd"].round(0)
    out["reserva_media_pct"] = out["reserva_media_pct"].round(1)
    out["region_winkler"] = out["winkler_gdd"].map(region_winkler)
    return out


def region_winkler(gdd: float) -> str | None:
    """Clasificación clásica de Winkler (grados-día ºC)."""
    if gdd is None or (isinstance(gdd, float) and math.isnan(gdd)):
        return None
    if gdd < 1390:
        return "I (fresca)"
    if gdd < 1670:
        return "II"
    if gdd < 1940:
        return "III"
    if gdd < 2220:
        return "IV"
    return "V (cálida)"
