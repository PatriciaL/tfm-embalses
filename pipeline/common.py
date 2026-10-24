"""Configuración y utilidades de operación compartidas por los notebooks.

Se importa desde los notebooks de esta misma carpeta (Git folder de Databricks).
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

# ---- Configuración ---------------------------------------------------------
CATALOG = "tfm_embalses"          # si Free Edition no deja crear catálogos: "workspace"
SCHEMAS = ["bronze", "silver", "gold", "quarantine", "ops", "ref"]
VOLUME_RAW = f"/Volumes/{CATALOG}/bronze/raw"   # ficheros originales, una carpeta por fecha de carga

SECRET_SCOPE = "caso-practico"
SECRET_AEMET = "aemet_api_key"

AEMET_ESTACION = "9170"           # Logroño Aeropuerto (D-10)
AEMET_DESDE = "2000-01-01"        # inicio de la carga histórica
MITECO_PAGINA = "https://www.miteco.gob.es/es/agua/temas/evaluacion-de-los-recursos-hidricos/boletin-hidrologico.html"
MITECO_TABLA = "T_Datos Embalses 1988-2026"
CUENCA_FILTRO = "ebro"            # se compara en minúsculas con AMBITO_NOMBRE

ORDEN_CALIDAD = ["critica", "aviso"]


def tabla(schema: str, nombre: str) -> str:
    return f"{CATALOG}.{schema}.{nombre}"


def ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def resolver_run_id(dbutils) -> str:
    """run_id del Job ({{job.run_id}}) o uno nuevo si se ejecuta a mano."""
    try:
        dbutils.widgets.text("run_id", "")
        rid = dbutils.widgets.get("run_id")
    except Exception:  # noqa: BLE001
        rid = ""
    return rid or f"manual-{dt.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


# ---- Conversión pandas -> Spark (todo como texto en bronze) ----------------
def a_spark_texto(spark, pdf):
    """Bronze guarda los valores tal como llegan, como texto, con nulos reales.

    Evita los problemas de inferencia de tipos con pd.NA y no altera el dato de origen.
    """
    from pyspark.sql.types import StringType, StructField, StructType

    columnas = [str(c) for c in pdf.columns]
    filas = [[None if (v is None or (not isinstance(v, str) and pd_isna(v))) else str(v) for v in fila]
             for fila in pdf.itertuples(index=False, name=None)]
    esquema = StructType([StructField(c, StringType(), True) for c in columnas])
    return spark.createDataFrame(filas, esquema)


def pd_isna(v) -> bool:
    try:
        import pandas as pd
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


# ---- Registro de ejecuciones ----------------------------------------------
def log_paso(spark, run_id: str, paso: str, fuente: str, estado: str, inicio: str,
             filas_entrada: int | None = None, filas_salida: int | None = None,
             detalle: dict | str | None = None) -> None:
    """Añade una fila a ops.run_log. Estados: OK, OK_SIN_CAMBIOS, OK_SIN_DATOS, ERROR."""
    if isinstance(detalle, dict):
        detalle = json.dumps(detalle, ensure_ascii=False, default=str)
    fila = [(run_id, paso, fuente, estado, inicio, ahora(),
             filas_entrada, filas_salida, detalle)]
    esquema = ("run_id string, paso string, fuente string, estado string, inicio string, fin string, "
               "filas_entrada long, filas_salida long, detalle string")
    spark.createDataFrame(fila, esquema).write.mode("append").saveAsTable(tabla("ops", "run_log"))
    print(f"[{paso}] {fuente}: {estado} | in={filas_entrada} out={filas_salida} | {detalle or ''}")


def log_calidad(spark, run_id: str, resultados: list[dict]) -> None:
    """Añade los resultados de las comprobaciones a ops.quality_results."""
    if not resultados:
        return
    filas = [(run_id, ahora(), r["control"], r["tabla"], r["nivel"], bool(r["ok"]),
              float(r["valor"]) if r.get("valor") is not None else None,
              r.get("umbral"), r.get("detalle")) for r in resultados]
    esquema = ("run_id string, ts string, control string, tabla string, nivel string, ok boolean, "
               "valor double, umbral string, detalle string")
    spark.createDataFrame(filas, esquema).write.mode("append").saveAsTable(tabla("ops", "quality_results"))
