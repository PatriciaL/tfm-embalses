# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze — Ingesta real de AEMET y MITECO
# MAGIC
# MAGIC Cambios respecto al pipeline heredado (ver `docs/diagnostico.md`):
# MAGIC - **Sin datos de ejemplo ni sintéticos.** Si una fuente falla, se registra el error en
# MAGIC   `ops.run_log` y el notebook termina en error: no se publica nada nuevo (hallazgos 1-2).
# MAGIC - **Origen marcado en cada fila:** `_source`, `_ingest_ts`, `_run_id` (y `_source_sha256` en MITECO).
# MAGIC - **Fichero original conservado** en el volumen `bronze.raw`, una carpeta por fecha de carga.
# MAGIC - **Incremental:** AEMET pide solo los días nuevos (con 10 días de solape para recoger
# MAGIC   correcciones); MITECO solo se carga si el fichero ha cambiado (huella SHA-256).
# MAGIC - **Control de esquema:** si falta una columna esperada, la fuente se detiene (hallazgo 8).

# COMMAND ----------

# MAGIC %pip install access-parser==0.0.6

# COMMAND ----------

import datetime as dt
import hashlib
import io
import json
import os
import re
import time
import zipfile
from urllib.parse import urljoin

import pandas as pd
import requests
from access_parser import AccessParser

from common import (AEMET_DESDE, AEMET_ESTACION, CUENCA_FILTRO, MITECO_PAGINA, SECRET_AEMET,
                    SECRET_SCOPE, VOLUME_RAW, a_spark_texto, ahora, log_paso, resolver_run_id, tabla)
from transforms import AEMET_COLUMNAS, MITECO_COLUMNAS, check_schema

RUN_ID = resolver_run_id(dbutils)
HOY = dt.date.today()
INGEST_TS = ahora()
errores = []
print("run_id:", RUN_ID)

# COMMAND ----------

# MAGIC %md ## AEMET OpenData — valores climatológicos diarios, estación 9170 (Logroño Aeropuerto)

# COMMAND ----------

AEMET_URL = ("https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos/"
             "fechaini/{ini}T00:00:00UTC/fechafin/{fin}T23:59:59UTC/estacion/{est}")


def aemet_get(url, key, intentos=3):
    """Patrón de la API: 1ª llamada -> metadatos con URL 'datos'; 2ª -> JSON real."""
    for i in range(intentos):
        meta = requests.get(url, params={"api_key": key}, timeout=30).json()
        estado = meta.get("estado")
        if estado == 200:
            return requests.get(meta["datos"], timeout=60).json()
        if estado == 404:                      # "No hay datos que satisfagan esos criterios"
            return []
        if estado == 429:                      # límite de peticiones por minuto
            time.sleep(60)
            continue
        raise RuntimeError(f"AEMET estado {estado}: {meta.get('descripcion')}")
    raise RuntimeError("AEMET: límite de peticiones superado tras varios reintentos")


def tabla_existe(nombre):
    return spark.catalog.tableExists(nombre)


inicio = ahora()
try:
    key = dbutils.secrets.get(scope=SECRET_SCOPE, key=SECRET_AEMET)
    destino = tabla("bronze", "aemet_diario")
    if tabla_existe(destino):
        ultima = spark.sql(f"SELECT max(try_cast(substr(fecha, 1, 10) AS DATE)) FROM {destino}").first()[0]
        desde = (ultima - dt.timedelta(days=10)) if ultima else dt.date.fromisoformat(AEMET_DESDE)
    else:
        desde = dt.date.fromisoformat(AEMET_DESDE)

    registros, tramos = [], 0
    ini = desde
    while ini <= HOY:
        fin = min(ini + dt.timedelta(days=179), HOY)          # tramos de 180 días
        datos = aemet_get(AEMET_URL.format(ini=ini, fin=fin, est=AEMET_ESTACION), key)
        if datos:
            ruta = f"{VOLUME_RAW}/aemet/{HOY}/{ini}_{fin}.json"
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "w") as f:
                json.dump(datos, f, ensure_ascii=False)
            registros.extend(datos)
        tramos += 1
        ini = fin + dt.timedelta(days=1)
        time.sleep(1.5)                                      # cortesía con la API

    if not registros:
        log_paso(spark, RUN_ID, "01_bronze", "aemet", "OK_SIN_DATOS", inicio, 0, 0,
                 {"desde": str(desde), "hasta": str(HOY), "tramos": tramos})
    else:
        df = pd.DataFrame(registros)
        esquema = check_schema(list(df.columns), AEMET_COLUMNAS)
        if not esquema["ok"]:
            raise RuntimeError(f"Esquema AEMET inesperado: faltan {esquema['faltan']}")
        df = df.assign(_source="aemet_opendata", _ingest_ts=INGEST_TS, _run_id=RUN_ID)
        (a_spark_texto(spark, df).write.mode("append").option("mergeSchema", "true").saveAsTable(destino))
        log_paso(spark, RUN_ID, "01_bronze", "aemet", "OK", inicio, len(registros), len(df),
                 {"desde": str(desde), "hasta": str(HOY), "tramos": tramos,
                  "columnas_nuevas": esquema["nuevas"]})
except Exception as exc:  # noqa: BLE001
    errores.append(("aemet", exc))
    log_paso(spark, RUN_ID, "01_bronze", "aemet", "ERROR", inicio, detalle=f"{type(exc).__name__}: {exc}"[:1000])

# COMMAND ----------

# MAGIC %md ## MITECO — histórico BD-Embalses (Access), filtrado a la cuenca del Ebro
# MAGIC La descarga se hace en tramos de 4 MiB: Free Edition corta las respuestas a 8 MiB (INC-02).

# COMMAND ----------

def descargar_por_tramos(url, tramo=4 * 1024 * 1024):
    total = int(requests.head(url, timeout=30, allow_redirects=True).headers["Content-Length"])
    partes, pos = [], 0
    while pos < total:
        fin = min(pos + tramo, total) - 1
        r = requests.get(url, headers={"Range": f"bytes={pos}-{fin}"}, timeout=120)
        r.raise_for_status()
        partes.append(r.content)
        pos = fin + 1
    contenido = b"".join(partes)
    if len(contenido) != total:
        raise RuntimeError(f"Descarga incompleta: {len(contenido)} de {total} bytes")
    return contenido


inicio = ahora()
try:
    html = requests.get(MITECO_PAGINA, timeout=30).text
    url_zip = urljoin(MITECO_PAGINA, re.search(r'href="([^"]*BD-Embalses[^"]*\.zip)"', html, re.I).group(1))
    contenido = descargar_por_tramos(url_zip)
    sha = hashlib.sha256(contenido).hexdigest()

    previo = spark.sql(f"""
        SELECT sha256 FROM {tabla('ops', 'source_files')}
        WHERE fuente = 'miteco' ORDER BY ts DESC LIMIT 1""").collect()
    if previo and previo[0][0] == sha:
        log_paso(spark, RUN_ID, "01_bronze", "miteco", "OK_SIN_CAMBIOS", inicio, 0, 0,
                 {"sha256": sha[:12], "nota": "MITECO no ha publicado datos nuevos desde la última carga"})
    else:
        ruta_zip = f"{VOLUME_RAW}/miteco/{HOY}/BD-Embalses.zip"
        os.makedirs(os.path.dirname(ruta_zip), exist_ok=True)
        with open(ruta_zip, "wb") as f:
            f.write(contenido)

        zipfile.ZipFile(io.BytesIO(contenido)).extract("BD-Embalses.mdb", "/tmp")
        db = AccessParser("/tmp/BD-Embalses.mdb")
        nombre_tabla = next(t for t in db.catalog if t.startswith("T_Datos Embalses"))
        raw = pd.DataFrame(db.parse_table(nombre_tabla))

        esquema = check_schema(list(raw.columns), MITECO_COLUMNAS)
        if not esquema["ok"]:
            raise RuntimeError(f"Esquema MITECO inesperado: faltan {esquema['faltan']}")

        ambitos = sorted(raw["AMBITO_NOMBRE"].dropna().astype(str).unique())
        ebro = raw[raw["AMBITO_NOMBRE"].astype(str).str.lower().str.contains(CUENCA_FILTRO)]
        if ebro.empty:
            raise RuntimeError(f"Ninguna fila de la cuenca '{CUENCA_FILTRO}'. Ámbitos recibidos: {ambitos}")

        df = ebro.assign(_source="miteco_bd_embalses", _ingest_ts=INGEST_TS,
                                          _run_id=RUN_ID, _source_sha256=sha)
        (a_spark_texto(spark, df).write.mode("append").option("mergeSchema", "true")
         .saveAsTable(tabla("bronze", "miteco_embalses")))

        spark.createDataFrame(
            [(RUN_ID, "miteco", url_zip, sha, len(contenido), ruta_zip, ahora())],
            "run_id string, fuente string, url string, sha256 string, bytes long, ruta_raw string, ts string",
        ).write.mode("append").saveAsTable(tabla("ops", "source_files"))

        log_paso(spark, RUN_ID, "01_bronze", "miteco", "OK", inicio, len(raw), len(df),
                 {"tabla_origen": nombre_tabla, "sha256": sha[:12], "fecha_max": str(ebro["FECHA"].max()),
                  "embalses_ebro": int(ebro["EMBALSE_NOMBRE"].nunique()), "ambitos": ambitos,
                  "columnas_nuevas": esquema["nuevas"]})
except Exception as exc:  # noqa: BLE001
    errores.append(("miteco", exc))
    log_paso(spark, RUN_ID, "01_bronze", "miteco", "ERROR", inicio, detalle=f"{type(exc).__name__}: {exc}"[:1000])

# COMMAND ----------

# MAGIC %md ## Resultado
# MAGIC Si alguna fuente ha fallado, el notebook termina en **error** y el Job no continúa:
# MAGIC silver y gold se quedan con la última versión buena (nada parcial llega al dashboard).

# COMMAND ----------

if errores:
    raise RuntimeError("Fuentes con error: " + "; ".join(f"{f}: {e}" for f, e in errores))
print("Bronze completado sin errores. run_id:", RUN_ID)
