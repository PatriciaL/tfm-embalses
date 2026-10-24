# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver — Normalización, deduplicación con criterio y cuarentena
# MAGIC
# MAGIC **En una frase:** convierte los datos en bruto en datos limpios y fiables, y lo que no
# MAGIC está claro lo aparta a cuarentena **con su motivo**, sin tirar nada.
# MAGIC
# MAGIC Las reglas de limpieza viven en `transforms.py` y tienen pruebas automáticas en `tests/`:
# MAGIC así se puede comprobar que funcionan sin necesidad de Databricks.
# MAGIC
# MAGIC | Problema heredado (diagnóstico) | Solución aquí |
# MAGIC |---|---|
# MAGIC | H4 · filas descartadas sin rastro | Cada fila acaba **aceptada** (silver) o en **revisión / rechazada** (quarantine, con motivo) |
# MAGIC | H5 · coma decimal → `null` | `parse_decimal_es` ("308,00" → 308.0) y `Ip` → 0,0 mm con bandera |
# MAGIC | H6 · deduplicación arbitraria | Una fila por clave: la de la **ingesta más reciente** |
# MAGIC | H7 · lluvia duplicada en cada ejecución | Silver se **reconstruye** desde bronze: el resultado es idéntico aunque se repita |
# MAGIC
# MAGIC **Los tres estados de una fila:**
# MAGIC - **aceptado** → va a silver y se usa en los indicadores.
# MAGIC - **revision** → dato dudoso (por ejemplo, lluvia "Acum", acumulada de varios días): se aparta para revisarlo.
# MAGIC - **rechazado** → dato imposible o sin fecha/embalse: se aparta con el motivo.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 1 · Funciones de trabajo
# MAGIC - **`a_spark`**: pasa la tabla de pandas a Spark convirtiendo los vacíos en nulos de verdad
# MAGIC   (pandas usa `NaN`/`pd.NA`, que Spark no entiende bien).
# MAGIC - **`escribir`**: guarda una tabla **sobrescribiéndola** entera. Por eso silver se puede
# MAGIC   repetir sin duplicar: siempre se reconstruye desde bronze completo.
# MAGIC - **`procesar`**: el proceso completo para una fuente:
# MAGIC   1. Lee todo bronze.
# MAGIC   2. **Normaliza** con la función de `transforms.py` (convierte comas decimales, fechas,
# MAGIC      calcula el % de capacidad y asigna a cada fila su estado y motivo).
# MAGIC   3. **Deduplica:** si la misma clave (embalse + fecha, o estación + fecha) aparece varias
# MAGIC      veces, se queda la de la ingesta más reciente. Las filas sin clave no se deduplican
# MAGIC      (no se pueden comparar) y siguen su camino hacia cuarentena.
# MAGIC   4. Separa: aceptadas → `silver`; el resto → `quarantine`, con el `run_id` que las apartó.
# MAGIC   5. Apunta en `ops.run_log` cuántas filas hay en cada estado y los motivos más frecuentes.

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
    # overwrite: la tabla se reconstruye entera en cada ejecución (idempotente)
    sdf.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(tabla(schema, nombre))


def procesar(fuente, tabla_bronze, normalizar, claves, nombre_silver):
    inicio = ahora()
    # 1. Leer bronze completo
    raw = spark.read.table(tabla("bronze", tabla_bronze)).toPandas()
    # 2. Normalizar y clasificar cada fila (aceptado / revision / rechazado)
    norm = normalizar(raw)

    # 3. Deduplicar solo las filas que tienen clave; las demás pasan tal cual
    con_clave = norm.dropna(subset=claves)
    sin_clave = norm[norm[claves].isna().any(axis=1)]
    norm = pd.concat([dedup_ultima_ingesta(con_clave, claves), sin_clave], ignore_index=True)
    norm["motivo"] = norm["motivo"].fillna("")          # evita columnas sin tipo si no hay cuarentena

    # 4. Separar aceptadas (silver) del resto (quarantine)
    sdf = a_spark(norm)
    aceptado = sdf.filter(F.col("estado") == "aceptado").drop("estado", "motivo")
    cuarentena = sdf.filter(F.col("estado") != "aceptado").withColumn("_run_id_cuarentena", F.lit(RUN_ID))
    escribir(aceptado, nombre_silver, "silver")
    escribir(cuarentena, nombre_silver, "quarantine")

    # 5. Registrar el recuento por estado y los 10 motivos más frecuentes
    conteo = {k: int(v) for k, v in norm["estado"].value_counts().items()}
    motivos = {k: int(v) for k, v in norm.loc[norm["estado"] != "aceptado", "motivo"].value_counts().head(10).items()}
    n_ok = conteo.get("aceptado", 0)
    log_paso(spark, RUN_ID, "02_silver", fuente, "OK", inicio, len(raw), n_ok,
             {"filas_bronze": len(raw), "tras_dedup": len(norm), "estados": conteo, "motivos": motivos})
    return conteo


# COMMAND ----------

# MAGIC %md
# MAGIC ## Embalses del Ebro (MITECO) · clave: embalse + fecha
# MAGIC ### Celda 2 · Procesar los embalses
# MAGIC Aplica `procesar` a los datos de MITECO. Resultado: `silver.embalses_ebro` (una fila por
# MAGIC embalse y semana, con volumen, capacidad y % de capacidad) y `quarantine.embalses_ebro`.
# MAGIC Muestra cuántas filas han quedado en cada estado.

# COMMAND ----------

print("embalses_ebro:", procesar("miteco", "miteco_embalses", normalizar_miteco, ["embalse", "fecha"], "embalses_ebro"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Clima de Logroño (AEMET 9170) · clave: estación + fecha
# MAGIC ### Celda 3 · Procesar el clima
# MAGIC Lo mismo para AEMET. Resultado: `silver.clima_logrono` (una fila por día con lluvia y
# MAGIC temperaturas) y `quarantine.clima_logrono`. La lluvia "Ip" (inapreciable) se guarda como
# MAGIC 0,0 mm y se marca con `prec_inapreciable = True`, para no confundirla con un día sin dato.

# COMMAND ----------

print("clima_logrono:", procesar("aemet", "aemet_diario", normalizar_aemet, ["estacion_id", "fecha"], "clima_logrono"))
