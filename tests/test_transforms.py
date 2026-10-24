"""Pruebas de las transformaciones. Ejecutar con: pytest -q tests/"""
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import transforms as t  # noqa: E402


# ---- Coma decimal (hallazgo 5 del diagnóstico) ---------------------------
def test_decimal_coma():
    assert t.parse_decimal_es("308,00") == 308.0
    assert t.parse_decimal_es("1.319,5") == 1319.5
    assert t.parse_decimal_es("13,2") == 13.2


def test_decimal_punto_y_numeros():
    assert t.parse_decimal_es("13.2") == 13.2
    assert t.parse_decimal_es(5) == 5.0
    assert t.parse_decimal_es("1.533") == 1533.0  # separador de miles sin decimales


def test_decimal_no_numerico():
    for v in [None, "", "abc", "nan"]:
        assert math.isnan(t.parse_decimal_es(v))


def test_precipitacion_inapreciable():
    assert t.parse_precipitacion("Ip") == (0.0, True)
    assert t.parse_precipitacion("2,4") == (2.4, False)
    valor, flag = t.parse_precipitacion("Acum")
    assert math.isnan(valor) and flag is False


# ---- Control de esquema (hallazgo 8) -------------------------------------
def test_schema_detecta_renombrado():
    cols = ["FECHA", "AMBITO", "EMBALSE_NOMBRE", "AGUA_TOTAL", "AGUA_ACTUAL", "ELECTRICO_FLAG"]
    r = t.check_schema(cols, t.MITECO_COLUMNAS)
    assert not r["ok"] and r["faltan"] == ["AMBITO_NOMBRE"] and r["nuevas"] == ["AMBITO"]


# ---- Reglas de calidad (hallazgo 4: nada se descarta sin rastro) ----------
def _raw_miteco(**over):
    base = {"FECHA": "2026-10-20 00:00:00", "AMBITO_NOMBRE": "Ebro", "EMBALSE_NOMBRE": "Mequinenza",
            "AGUA_TOTAL": "1.533,00", "AGUA_ACTUAL": "800,50", "ELECTRICO_FLAG": "1.",
            "_ingest_ts": "2026-10-24T18:00:00"}
    base.update(over)
    return base


def test_miteco_estados():
    raw = pd.DataFrame([
        _raw_miteco(),
        _raw_miteco(EMBALSE_NOMBRE="A", AGUA_ACTUAL="-1,0"),
        _raw_miteco(EMBALSE_NOMBRE="B", AGUA_ACTUAL="1.600,00"),
        _raw_miteco(EMBALSE_NOMBRE="C", FECHA="no es fecha"),
    ])
    out = t.normalizar_miteco(raw)
    assert list(out["estado"]) == ["aceptado", "rechazado", "revision", "rechazado"]
    assert out.loc[0, "volumen_hm3"] == 800.5 and out.loc[0, "pct_capacidad"] == 52.22
    assert out.loc[0, "electrico"]
    assert out["motivo"].notna().sum() == 3  # cada fila no aceptada lleva su motivo


def test_aemet_estados():
    raw = pd.DataFrame([
        {"fecha": "2026-10-01", "indicativo": "9170", "prec": "Ip", "tmax": "22,9", "tmin": "14,9", "tmed": "18,9", "_ingest_ts": "x"},
        {"fecha": "2026-10-02", "indicativo": "9170", "prec": "0,0", "tmax": "10,0", "tmin": "14,0", "tmed": "12,0", "_ingest_ts": "x"},
        {"fecha": "2026-10-03", "indicativo": "9170", "prec": "1,0", "tmax": "25,5", "tmin": "17,0", "tmed": None, "_ingest_ts": "x"},
    ])
    out = t.normalizar_aemet(raw)
    assert list(out["estado"]) == ["aceptado", "revision", "rechazado"]
    assert out.loc[0, "prec_inapreciable"] and out.loc[0, "prec_mm"] == 0.0


# ---- Deduplicación con criterio (hallazgo 6) ------------------------------
def test_dedup_se_queda_con_la_ingesta_mas_reciente():
    df = pd.DataFrame([
        {"embalse": "X", "fecha": "2026-10-20", "volumen_hm3": 10.0, "_ingest_ts": "2026-10-21"},
        {"embalse": "X", "fecha": "2026-10-20", "volumen_hm3": 11.0, "_ingest_ts": "2026-10-28"},
        {"embalse": "Y", "fecha": "2026-10-20", "volumen_hm3": 5.0, "_ingest_ts": "2026-10-21"},
    ])
    out = t.dedup_ultima_ingesta(df, ["embalse", "fecha"])
    assert len(out) == 2
    assert out.loc[out.embalse == "X", "volumen_hm3"].item() == 11.0


def test_dedup_es_idempotente():
    df = pd.DataFrame([{"k": 1, "_ingest_ts": "a"}, {"k": 1, "_ingest_ts": "b"}])
    una = t.dedup_ultima_ingesta(df, ["k"])
    dos = t.dedup_ultima_ingesta(pd.concat([una, una]), ["k"])
    assert una.equals(dos)


# ---- Indicador de campaña -------------------------------------------------
def test_winkler():
    assert t.grados_dia_winkler(pd.Series([8.0, 10.0, 15.5, 20.0])) == 15.5
    assert t.region_winkler(1500) == "II"
    assert t.region_winkler(2500) == "V (cálida)"


def test_campana_solo_abril_octubre():
    fechas = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    clima = pd.DataFrame({"fecha": fechas, "prec_mm": 1.0, "tmed": 20.0})
    reserva = pd.DataFrame({"fecha": fechas[::7], "pct_capacidad": 50.0})
    out = t.campana_vitivinicola(clima, reserva).iloc[0]
    assert out["dias_con_dato"] == 214
    assert out["lluvia_campana_mm"] == 214.0
    assert out["winkler_gdd"] == 2140.0
    assert out["completitud_pct"] == 100.0
    assert out["reserva_media_pct"] == 50.0
