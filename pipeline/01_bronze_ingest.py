# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze — Ingesta real de AEMET y MITECO
# MAGIC
# MAGIC **En una frase:** descarga los datos de las dos fuentes reales y los guarda **tal cual
# MAGIC llegan**, sin tocarlos, marcando de dónde y cuándo vino cada fila.
# MAGIC
# MAGIC Cambios respecto al pipeline heredado (ver `docs/diagnostico.md`):
# MAGIC - **Sin datos de ejemplo ni sintéticos.** Si una fuente falla, se registra el error en
# MAGIC   `ops.run_log` y el notebook termina en error: no se publica nada nuevo (hallazgos 1-2).
# MAGIC - **Origen marcado en cada fila:** `_source`, `_ingest_ts`, `_run_id` (y `_source_sha256` en MITECO).
# MAGIC - **Fichero original conservado** en el volumen `bronze.raw`, una carpeta por fecha de carga.
# MAGIC - **Incremental:** AEMET pide solo los días nuevos (con 10 días de solape para recoger
# MAGIC   correcciones); MITECO solo se carga si el fichero ha cambiado (huella SHA-256).
# MAGIC - **Control de esquema:** si falta una columna esperada, la fuente se detiene (hallazgo 8).
# MAGIC
# MAGIC **Por qué todo en texto:** en bronze se guarda todo como texto para no perder información
# MAGIC (por ejemplo, "308,00" con coma o "Ip" en la lluvia). La conversión a números se hace en silver.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 1 · Instalar la librería para leer ficheros Access
# MAGIC MITECO publica su base de datos en formato Microsoft Access (`.mdb`). `access-parser` permite
# MAGIC leerlo desde Python. Se fija la versión (0.0.6) para que el resultado sea reproducible.

# COMMAND ----------

# MAGIC %pip install access-parser==0.0.6

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 2 · Reiniciar Python
# MAGIC Tras instalar una librería, Databricks necesita reiniciar Python para poder importarla
# MAGIC (INC-03: sin esto aparecía un aviso y la importación podía fallar).

# COMMAND ----------

# Reinicia Python para que la librería recién instalada se pueda importar
dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 3 · Importar librerías y preparar la ejecución
# MAGIC - Importa las librerías y la configuración compartida (`common.py`) y las reglas (`transforms.py`).
# MAGIC - **`RUN_ID`**: identificador de esta ejecución. Si la lanza el Job, es el id del Job; si se
# MAGIC   ejecuta a mano, se genera uno "manual". Con él se puede rastrear cada fila hasta su carga.
# MAGIC - **`INGEST_TS`**: hora de la carga, la misma para todas las filas de esta ejecución.
# MAGIC - **`errores`**: lista donde se apuntan los fallos de cada fuente para decidir al final.

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

RUN_ID = resolver_run_id(dbutils)   # id de la ejecución (Job o manual)
HOY = dt.date.today()
INGEST_TS = ahora()                 # sello de tiempo común a toda la carga
errores = []                        # fallos por fuente; se revisan en la última celda
print("run_id:", RUN_ID)

# COMMAND ----------

# MAGIC %md
# MAGIC ## AEMET OpenData — valores climatológicos diarios, estación 9170 (Logroño Aeropuerto)
# MAGIC
# MAGIC ### Celda 4 · Descargar el clima diario de Logroño
# MAGIC **Cómo funciona la API de AEMET (dos pasos):**
# MAGIC 1. Se pide la URL con la API key → AEMET responde con un "sobre" (metadatos) que contiene
# MAGIC    un enlace temporal en el campo `datos`.
# MAGIC 2. Se descarga ese enlace → ahí están los datos reales en JSON.
# MAGIC
# MAGIC **Respuestas que se tratan:** `200` = OK · `404` = no hay datos para esas fechas (no es un
# MAGIC error) · `429` = demasiadas peticiones, se espera 60 s y se reintenta · cualquier otra = error.
# MAGIC
# MAGIC **Qué hace la celda, paso a paso:**
# MAGIC 1. Lee la API key del secret scope (nunca escrita en el código).
# MAGIC 2. **Decide desde qué fecha pedir:** si ya hay datos, desde la última fecha menos 10 días
# MAGIC    (por si AEMET corrigió algún día reciente); si no, desde el 1/1/2000.
# MAGIC 3. Pide los datos en **tramos de 180 días** (AEMET no deja pedir periodos muy largos) y
# MAGIC    espera 1,5 s entre peticiones para no saturar la API.
# MAGIC 4. Guarda cada respuesta original como JSON en el volumen `raw`.
# MAGIC 5. Comprueba que llegan las columnas esperadas (fecha, indicativo, prec, tmax, tmin, tmed).
# MAGIC 6. Añade las columnas de trazabilidad y **añade** (append) las filas a `bronze.aemet_diario`.
# MAGIC 7. Apunta el resultado en `ops.run_log`. Si algo falla, apunta el error y sigue con MITECO.
# MAGIC
# MAGIC Las filas repetidas por el solape de 10 días no son un problema: silver se queda con la más reciente.

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
    # 1. API key desde el secret scope
    key = dbutils.secrets.get(scope=SECRET_SCOPE, key=SECRET_AEMET)
    destino = tabla("bronze", "aemet_diario")

    # 2. Carga incremental: desde la última fecha cargada menos 10 días de solape
    if tabla_existe(destino):
        ultima = spark.sql(f"SELECT max(try_cast(substr(fecha, 1, 10) AS DATE)) FROM {destino}").first()[0]
        desde = (ultima - dt.timedelta(days=10)) if ultima else dt.date.fromisoformat(AEMET_DESDE)
    else:
        desde = dt.date.fromisoformat(AEMET_DESDE)   # primera carga: histórico completo

    # 3-4. Descarga por tramos y copia del JSON original en el volumen
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
        # Sin días nuevos: no es un error, se registra como tal
        log_paso(spark, RUN_ID, "01_bronze", "aemet", "OK_SIN_DATOS", inicio, 0, 0,
                 {"desde": str(desde), "hasta": str(HOY), "tramos": tramos})
    else:
        df = pd.DataFrame(registros)
        # 5. Control de esquema: si falta una columna, se detiene la fuente
        esquema = check_schema(list(df.columns), AEMET_COLUMNAS)
        if not esquema["ok"]:
            raise RuntimeError(f"Esquema AEMET inesperado: faltan {esquema['faltan']}")
        # 6. Trazabilidad por fila y escritura en bronze (append, todo como texto)
        df = df.assign(_source="aemet_opendata", _ingest_ts=INGEST_TS, _run_id=RUN_ID)
        (a_spark_texto(spark, df).write.mode("append").option("mergeSchema", "true").saveAsTable(destino))
        # 7. Registro de la ejecución
        log_paso(spark, RUN_ID, "01_bronze", "aemet", "OK", inicio, len(registros), len(df),
                 {"desde": str(desde), "hasta": str(HOY), "tramos": tramos,
                  "columnas_nuevas": esquema["nuevas"]})
except Exception as exc:  # noqa: BLE001
    # Se apunta el error pero no se detiene aún: así MITECO también se intenta
    errores.append(("aemet", exc))
    log_paso(spark, RUN_ID, "01_bronze", "aemet", "ERROR", inicio, detalle=f"{type(exc).__name__}: {exc}"[:1000])

# COMMAND ----------

# MAGIC %md
# MAGIC ## MITECO — histórico BD-Embalses (Access), filtrado a la cuenca del Ebro
# MAGIC
# MAGIC ### Celda 5 · Descargar y cargar los embalses del Ebro
# MAGIC **El problema:** el ZIP de MITECO pesa más de 8 MiB y Free Edition corta las respuestas a
# MAGIC 8 MiB (INC-02). **La solución:** pedirlo en trozos de 4 MiB con la cabecera HTTP `Range`
# MAGIC ("dame los bytes del X al Y") y unirlos. Al final se comprueba que el tamaño cuadra.
# MAGIC
# MAGIC **Qué hace la celda, paso a paso:**
# MAGIC 1. Lee la página de MITECO y busca el enlace al ZIP `BD-Embalses` (así, si cambia el
# MAGIC    nombre del fichero, se sigue encontrando).
# MAGIC 2. Lo descarga por tramos y calcula su **huella SHA-256** (una especie de DNI del fichero:
# MAGIC    si cambia un solo byte, cambia la huella).
# MAGIC 3. **Compara con la huella de la última carga.** Si es igual, MITECO no ha publicado nada
# MAGIC    nuevo: se registra `OK_SIN_CAMBIOS` y no se carga nada (evita duplicar 700.000 filas).
# MAGIC 4. Si es distinta: guarda el ZIP en el volumen, extrae el `.mdb` y lee la tabla de datos
# MAGIC    (la que empieza por `T_Datos Embalses`).
# MAGIC 5. Comprueba el esquema (FECHA, AMBITO_NOMBRE, EMBALSE_NOMBRE, AGUA_TOTAL, AGUA_ACTUAL…).
# MAGIC 6. **Filtra la cuenca del Ebro** (el fichero trae toda España). Si no queda ninguna fila,
# MAGIC    se para y muestra qué cuencas llegaron, para poder diagnosticarlo.
# MAGIC 7. Añade la trazabilidad (incluida la huella) y escribe en `bronze.miteco_embalses`.
# MAGIC 8. Apunta el fichero en `ops.source_files` y el resultado en `ops.run_log`.

# COMMAND ----------

def descargar_por_tramos(url, tramo=4 * 1024 * 1024):
    # Tamaño total del fichero (sin descargarlo)
    total = int(requests.head(url, timeout=30, allow_redirects=True).headers["Content-Length"])
    partes, pos = [], 0
    while pos < total:
        fin = min(pos + tramo, total) - 1
        # Pide solo los bytes pos..fin
        r = requests.get(url, headers={"Range": f"bytes={pos}-{fin}"}, timeout=120)
        r.raise_for_status()
        partes.append(r.content)
        pos = fin + 1
    contenido = b"".join(partes)
    # Comprobación: si falta algún trozo, error (nunca un fichero a medias)
    if len(contenido) != total:
        raise RuntimeError(f"Descarga incompleta: {len(contenido)} de {total} bytes")
    return contenido


inicio = ahora()
try:
    # 1. Localizar el enlace al ZIP en la página de MITECO
    html = requests.get(MITECO_PAGINA, timeout=30).text
    url_zip = urljoin(MITECO_PAGINA, re.search(r'href="([^"]*BD-Embalses[^"]*\.zip)"', html, re.I).group(1))
    # 2. Descargar por tramos y calcular la huella
    contenido = descargar_por_tramos(url_zip)
    sha = hashlib.sha256(contenido).hexdigest()

    # 3. ¿Es el mismo fichero que la última vez?
    previo = spark.sql(f"""
        SELECT sha256 FROM {tabla('ops', 'source_files')}
        WHERE fuente = 'miteco' ORDER BY ts DESC LIMIT 1""").collect()
    if previo and previo[0][0] == sha:
        log_paso(spark, RUN_ID, "01_bronze", "miteco", "OK_SIN_CAMBIOS", inicio, 0, 0,
                 {"sha256": sha[:12], "nota": "MITECO no ha publicado datos nuevos desde la última carga"})
    else:
        # 4. Guardar el ZIP original y leer la base de datos Access
        ruta_zip = f"{VOLUME_RAW}/miteco/{HOY}/BD-Embalses.zip"
        os.makedirs(os.path.dirname(ruta_zip), exist_ok=True)
        with open(ruta_zip, "wb") as f:
            f.write(contenido)

        zipfile.ZipFile(io.BytesIO(contenido)).extract("BD-Embalses.mdb", "/tmp")
        db = AccessParser("/tmp/BD-Embalses.mdb")
        nombre_tabla = next(t for t in db.catalog if t.startswith("T_Datos Embalses"))
        raw = pd.DataFrame(db.parse_table(nombre_tabla))

        # 5. Control de esquema
        esquema = check_schema(list(raw.columns), MITECO_COLUMNAS)
        if not esquema["ok"]:
            raise RuntimeError(f"Esquema MITECO inesperado: faltan {esquema['faltan']}")

        # 6. Quedarse solo con la cuenca del Ebro
        ambitos = sorted(raw["AMBITO_NOMBRE"].dropna().astype(str).unique())
        ebro = raw[raw["AMBITO_NOMBRE"].astype(str).str.lower().str.contains(CUENCA_FILTRO)]
        if ebro.empty:
            raise RuntimeError(f"Ninguna fila de la cuenca '{CUENCA_FILTRO}'. Ámbitos recibidos: {ambitos}")

        # 7. Trazabilidad por fila (incluida la huella del fichero) y escritura en bronze
        df = ebro.assign(_source="miteco_bd_embalses", _ingest_ts=INGEST_TS,
                                          _run_id=RUN_ID, _source_sha256=sha)
        (a_spark_texto(spark, df).write.mode("append").option("mergeSchema", "true")
         .saveAsTable(tabla("bronze", "miteco_embalses")))

        # 8. Registrar el fichero descargado (su huella se compara en la próxima ejecución)
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

# MAGIC %md
# MAGIC ## Resultado
# MAGIC ### Celda 6 · Decidir si la ingesta ha ido bien
# MAGIC Si alguna fuente ha fallado, el notebook termina en **error** y el Job no continúa:
# MAGIC silver y gold se quedan con la última versión buena (nada parcial llega al dashboard).
# MAGIC El motivo exacto del fallo queda en `ops.run_log` y se ve en la pestaña "Salud del pipeline".

# COMMAND ----------

if errores:
    raise RuntimeError("Fuentes con error: " + "; ".join(f"{f}: {e}" for f, e in errores))
print("Bronze completado sin errores. run_id:", RUN_ID)
