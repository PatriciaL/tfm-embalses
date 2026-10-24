# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Setup — catálogo, esquemas, volumen y tablas de operación
# MAGIC
# MAGIC **En una frase:** prepara "la casa" donde vivirán los datos antes de cargar nada.
# MAGIC
# MAGIC Se ejecuta **una vez** (es idempotente: si lo repites no rompe ni duplica nada, porque
# MAGIC todo usa `IF NOT EXISTS` o sobrescribe).
# MAGIC
# MAGIC | Esquema | Contenido |
# MAGIC |---|---|
# MAGIC | `bronze` | Datos tal como llegan + volumen `raw` con los ficheros originales por fecha de carga |
# MAGIC | `silver` | Datos normalizados y **aceptados** |
# MAGIC | `quarantine` | Filas en **revisión** o **rechazadas**, con su motivo |
# MAGIC | `gold` | Indicadores listos para el dashboard |
# MAGIC | `ops` | `run_log` (ejecuciones), `quality_results` (controles) y `source_files` (ficheros descargados) |
# MAGIC | `ref` | Datos de referencia mantenidos a mano (calificación DOCa Rioja) |
# MAGIC
# MAGIC **Analogía:** el catálogo es el edificio, cada esquema es una planta (bronze = almacén de
# MAGIC entrada, silver = taller, gold = escaparate, ops = oficina de control) y cada tabla un armario.
# MAGIC
# MAGIC Requisito previo: la API key de AEMET guardada en el secret scope `caso-practico`
# MAGIC (notebook heredado `00_setup_secrets`). La key nunca aparece en el código.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 1 · Crear catálogo, esquemas y volumen
# MAGIC - Crea el catálogo `tfm_embalses` (si ya existe, no hace nada).
# MAGIC - Crea dentro los seis esquemas de la tabla de arriba.
# MAGIC - Crea el **volumen** `bronze.raw`: una carpeta gestionada por Unity Catalog donde se
# MAGIC   guardan los ficheros originales (JSON de AEMET, ZIP de MITECO) tal cual se descargan.
# MAGIC   Así siempre se puede volver a la fuente original si hay dudas.
# MAGIC - Si Free Edition no dejara crear catálogos, el error explica qué cambiar.

# COMMAND ----------

# Nombres centralizados en common.py: si cambian, cambian en un solo sitio
from common import CATALOG, SCHEMAS, tabla

try:
    spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
except Exception as exc:  # noqa: BLE001
    # Error explicado en lugar de un fallo críptico
    raise RuntimeError(
        f"No se pudo crear el catálogo {CATALOG}: {exc}\n"
        "Si Free Edition no lo permite, cambia CATALOG = 'workspace' en pipeline/common.py y vuelve a ejecutar."
    )

# Un esquema por capa: bronze, silver, quarantine, gold, ops, ref
for s in SCHEMAS:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{s}")
# Carpeta para los ficheros originales descargados
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.bronze.raw")
print("Catálogo, esquemas y volumen listos:", CATALOG, SCHEMAS)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 2 · Tablas de operación (`ops`)
# MAGIC Son el "cuaderno de bitácora" del pipeline. Se crean vacías desde el principio para que el
# MAGIC dashboard no falle antes de la primera carga.
# MAGIC - **`run_log`**: una fila por paso y fuente en cada ejecución (¿cuándo empezó y acabó?,
# MAGIC   ¿salió bien?, ¿cuántas filas entraron y salieron?).
# MAGIC - **`quality_results`**: el resultado de cada control de calidad (valor medido, umbral, OK o no).
# MAGIC - **`source_files`**: cada fichero descargado con su **huella SHA-256**, que sirve para saber
# MAGIC   si MITECO ha publicado un fichero nuevo o es el mismo de la última vez.

# COMMAND ----------

# Registro de ejecuciones: quién hizo qué, cuándo y con qué resultado
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {tabla('ops', 'run_log')} (
  run_id string, paso string, fuente string, estado string, inicio string, fin string,
  filas_entrada long, filas_salida long, detalle string)
COMMENT 'Una fila por paso y fuente de cada ejecución del pipeline'
""")
# Resultados de los controles de calidad del notebook 03
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {tabla('ops', 'quality_results')} (
  run_id string, ts string, control string, tabla string, nivel string, ok boolean,
  valor double, umbral string, detalle string)
COMMENT 'Resultado de cada control de calidad en cada ejecución'
""")
# Ficheros descargados y su huella (para detectar cambios en la fuente)
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {tabla('ops', 'source_files')} (
  run_id string, fuente string, url string, sha256 string, bytes long, ruta_raw string, ts string)
COMMENT 'Ficheros descargados de cada fuente, con su huella para detectar si han cambiado'
""")
print("Tablas ops listas")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 3 · Cargar las calificaciones oficiales DOCa Rioja (`ref`)
# MAGIC - Lee el CSV `ref/doca_calificaciones.csv` del repositorio: una fila por añada con su
# MAGIC   calificación oficial (Excelente, Muy buena…) y la URL de donde se tomó.
# MAGIC - Se rellena **a mano** desde la web del Consejo Regulador y se versiona en Git (D-04, D-14):
# MAGIC   cambia una vez al año, no merece una ingesta automática.
# MAGIC - Lo sube a la tabla `ref.doca_calificaciones`, sobrescribiendo la versión anterior.
# MAGIC - Se lee todo como texto (`dtype=str`) para no alterar ningún valor; las líneas que empiezan
# MAGIC   por `#` son comentarios del CSV y se ignoran.

# COMMAND ----------

import os
import pandas as pd

# El notebook está en pipeline/; el CSV en ref/ (una carpeta por encima)
ruta_ref = os.path.join(os.path.dirname(os.getcwd()), "ref", "doca_calificaciones.csv")
doca = pd.read_csv(ruta_ref, dtype=str, comment="#").dropna(how="all")
print(f"{len(doca)} añadas en {ruta_ref}")
if len(doca):
    (spark.createDataFrame(doca).write.mode("overwrite").option("overwriteSchema", "true")
     .saveAsTable(tabla("ref", "doca_calificaciones")))
    print("ref.doca_calificaciones actualizada")
else:
    # No se inventan calificaciones: si el CSV está vacío, solo se avisa
    print("AVISO: el CSV de calificaciones DOCa está vacío; rellénalo desde la fuente oficial.")
