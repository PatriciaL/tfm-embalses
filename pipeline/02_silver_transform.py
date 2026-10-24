# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver — Normalización, deduplicación con criterio y cuarentena
# MAGIC
# MAGIC Las transformaciones viven en `transforms.py` y tienen pruebas en `tests/`.
# MAGIC
# MAGIC | Problema heredado (diagnóstico) | Solución aquí |
# MAGIC |---|---|
# MAGIC | H4 · filas descartadas sin rastro | Cada fila acaba **aceptada** (silver) o en **revisión / rechazada** (quarantine, con motivo) |
# MAGIC | H5 · coma decimal → `null` | `parse_decimal_es` ("308,00" → 308.0) y `Ip` → 0,0 mm con bandera |
# MAGIC | H6 · deduplicación arbitraria | Una fila por clave: la de la **ingesta más reciente** |
# MAGIC | H7 · lluvia duplicada en cada ejecución | Silver se **reconstruye** desde bronze: el resultado es idéntico aunque se repita |

# COMMAND ----------

import pandas as pd
from pyspark.sql import functions as F

from common import ahora, log_paso, resolver_run_id, tabla
from transforms import dedup_ultima_ingesta, normalizar_aemet, normalizar_miteco

RUN_ID = resolver_run_id(dbutils)


def a_spark(pdf: pd.DataFrame):
    """pandas -> Spark con nulos reales (sin pd.NA ni NaN en columnas de texto)."""
    limpio = pdf.astype(object).where(pdf.notna(), None)
    return spark.createDataFrame(limpio)


def escribir(sdf, nombre: str, schema: str):
    sdf.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(tabla(schema, nombre))


def procesar(fuente, tabla_bronze, normalizar, claves, nombre_silver):
    inicio = ahora()
    raw = spark.read.table(tabla("bronze", tabla_bronze)).toPandas()
    norm = normalizar(raw)

    con_clave = norm.dropna(subset=claves)
    sin_clave = norm[norm[claves].isna().any(axis=1)]
    norm = pd.concat([dedup_ultima_ingesta(con_clave, claves), sin_clave], ignore_index=True)
    norm["motivo"] = norm["motivo"].fillna("")          # evita columnas sin tipo si no hay cuarentena

    sdf = a_spark(norm)
    aceptado = sdf.filter(F.col("estado") == "aceptado").drop("estado", "motivo")
    cuarentena = sdf.filter(F.col("estado") != "aceptado").withColumn("_run_id_cuarentena", F.lit(RUN_ID))
    escribir(aceptado, nombre_silver, "silver")
    escribir(cuarentena, nombre_silver, "quarantine")

    conteo = {k: int(v) for k, v in norm["estado"].value_counts().items()}
    motivos = {k: int(v) for k, v in norm.loc[norm["estado"] != "aceptado", "motivo"].value_counts().head(10).items()}
    n_ok = conteo.get("aceptado", 0)
    log_paso(spark, RUN_ID, "02_silver", fuente, "OK", inicio, len(raw), n_ok,
             {"filas_bronze": len(raw), "tras_dedup": len(norm), "estados": conteo, "motivos": motivos})
    return conteo


# COMMAND ----------

# MAGIC %md ## Embalses del Ebro (MITECO) · clave: embalse + fecha

# COMMAND ----------

print("embalses_ebro:", procesar("miteco", "miteco_embalses", normalizar_miteco, ["embalse", "fecha"], "embalses_ebro"))

# COMMAND ----------

# MAGIC %md ## Clima de Logroño (AEMET 9170) · clave: estación + fecha

# COMMAND ----------

print("clima_logrono:", procesar("aemet", "aemet_diario", normalizar_aemet, ["estacion_id", "fecha"], "clima_logrono"))
