# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup — catálogo, esquemas, volumen y tablas de operación
# MAGIC
# MAGIC Se ejecuta **una vez** (es idempotente: se puede repetir sin efectos).
# MAGIC
# MAGIC | Esquema | Contenido |
# MAGIC |---|---|
# MAGIC | `bronze` | Datos tal como llegan + volumen `raw` con los ficheros originales por fecha de carga |
# MAGIC | `silver` | Datos normalizados y **aceptados** |
# MAGIC | `quarantine` | Filas en **revisión** o **rechazadas**, con su motivo |
# MAGIC | `gold` | Indicadores listos para el dashboard |
# MAGIC | `ops` | `run_log` (ejecuciones) y `quality_results` (controles) |
# MAGIC | `ref` | Datos de referencia mantenidos a mano (calificación DOCa Rioja) |
# MAGIC
# MAGIC Requisito previo: la API key de AEMET en el secret scope `caso-practico`
# MAGIC (notebook heredado `00_setup_secrets`).

# COMMAND ----------

from common import CATALOG, SCHEMAS, tabla

try:
    spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
except Exception as exc:  # noqa: BLE001
    raise RuntimeError(
        f"No se pudo crear el catálogo {CATALOG}: {exc}\n"
        "Si Free Edition no lo permite, cambia CATALOG = 'workspace' en pipeline/common.py y vuelve a ejecutar."
    )

for s in SCHEMAS:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{s}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.bronze.raw")
print("Catálogo, esquemas y volumen listos:", CATALOG, SCHEMAS)

# COMMAND ----------

# MAGIC %md ## Tablas de operación (se crean vacías para que el dashboard no falle antes de la primera carga)

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {tabla('ops', 'run_log')} (
  run_id string, paso string, fuente string, estado string, inicio string, fin string,
  filas_entrada long, filas_salida long, detalle string)
COMMENT 'Una fila por paso y fuente de cada ejecución del pipeline'
""")
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {tabla('ops', 'quality_results')} (
  run_id string, ts string, control string, tabla string, nivel string, ok boolean,
  valor double, umbral string, detalle string)
COMMENT 'Resultado de cada control de calidad en cada ejecución'
""")
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {tabla('ops', 'source_files')} (
  run_id string, fuente string, url string, sha256 string, bytes long, ruta_raw string, ts string)
COMMENT 'Ficheros descargados de cada fuente, con su huella para detectar si han cambiado'
""")
print("Tablas ops listas")

# COMMAND ----------

# MAGIC %md ## Datos de referencia: calificaciones DOCa Rioja
# MAGIC Fuente oficial: Consejo Regulador DOCa Rioja. El CSV `ref/doca_calificaciones.csv`
# MAGIC se rellena **a mano** desde la web oficial y se versiona en Git (D-04).

# COMMAND ----------

import os
import pandas as pd

ruta_ref = os.path.join(os.path.dirname(os.getcwd()), "ref", "doca_calificaciones.csv")
doca = pd.read_csv(ruta_ref, dtype=str, comment="#").dropna(how="all")
print(f"{len(doca)} añadas en {ruta_ref}")
if len(doca):
    (spark.createDataFrame(doca).write.mode("overwrite").option("overwriteSchema", "true")
     .saveAsTable(tabla("ref", "doca_calificaciones")))
    print("ref.doca_calificaciones actualizada")
else:
    print("AVISO: el CSV de calificaciones DOCa está vacío; rellénalo desde la fuente oficial.")
