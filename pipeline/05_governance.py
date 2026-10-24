# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Gobierno — clasificación, documentación y exposición mínima
# MAGIC
# MAGIC Se ejecuta **una vez** (y de nuevo si cambian tablas). Es idempotente.
# MAGIC
# MAGIC | Aspecto | Qué se hace | Dónde se ve |
# MAGIC |---|---|---|
# MAGIC | Clasificación | Etiquetas `clasificacion`, `capa`, `fuente`, `datos_personales` en cada tabla | Catalog Explorer › tabla › Tags |
# MAGIC | Documentación | Comentario de tabla y de las columnas clave | Catalog Explorer › tabla › Overview |
# MAGIC | Exposición | El dashboard solo lee `gold` y `ops` (permiso `SELECT`), nunca bronze ni quarantine | `SHOW GRANTS` (al final) |
# MAGIC | Linaje | Unity Catalog lo registra solo al ejecutar los notebooks | Catalog Explorer › tabla › Lineage |
# MAGIC
# MAGIC **Datos personales:** ninguna fuente contiene datos personales (embalses, meteorología y
# MAGIC calificaciones de añada). Se declara explícitamente con la etiqueta `datos_personales = no`
# MAGIC y como límite en la memoria: la propagación de supresión/consentimiento no aplica.

# COMMAND ----------

from common import CATALOG, tabla

dbutils.widgets.text("principal_app", "", "Service principal de la app (opcional)")
PRINCIPAL_APP = dbutils.widgets.get("principal_app").strip()

TABLAS = {
    # (schema, tabla): (capa, fuente, comentario)
    ("bronze", "miteco_embalses"): ("bronze", "MITECO", "Reserva semanal de embalses de la cuenca del Ebro tal como la publica MITECO (BD-Embalses, sin validar). Texto sin transformar, append."),
    ("bronze", "aemet_diario"): ("bronze", "AEMET", "Valores climatológicos diarios de la estación 9170 (Logroño Aeropuerto) tal como los devuelve AEMET OpenData. Texto sin transformar, append."),
    ("silver", "embalses_ebro"): ("silver", "MITECO", "Embalses del Ebro normalizados y aceptados: una fila por embalse y fecha (ingesta más reciente)."),
    ("silver", "clima_logrono"): ("silver", "AEMET", "Clima diario de Logroño normalizado y aceptado: una fila por estación y fecha."),
    ("quarantine", "embalses_ebro"): ("quarantine", "MITECO", "Filas de embalses en revisión o rechazadas, con su motivo. Se reconstruye en cada ejecución."),
    ("quarantine", "clima_logrono"): ("quarantine", "AEMET", "Días de clima en revisión o rechazados, con su motivo. Se reconstruye en cada ejecución."),
    ("gold", "reserva_ebro_semanal"): ("gold", "MITECO", "Reserva agregada de la cuenca del Ebro por semana (suma de embalses)."),
    ("gold", "reserva_embalses_actual"): ("gold", "MITECO", "Última lectura disponible de cada embalse del Ebro."),
    ("gold", "campana_vitivinicola"): ("gold", "AEMET+MITECO+DOCa", "Indicador de campaña (abril-octubre): lluvia, grados-día de Winkler, reserva media y calificación DOCa."),
    ("gold", "kpis"): ("gold", "AEMET+MITECO", "KPIs de cabecera del dashboard, con su nota y la ejecución que los generó."),
    ("ops", "run_log"): ("ops", "pipeline", "Una fila por paso y fuente de cada ejecución: estado, filas y detalle."),
    ("ops", "quality_results"): ("ops", "pipeline", "Resultado de cada control de calidad en cada ejecución."),
    ("ops", "source_files"): ("ops", "pipeline", "Ficheros descargados de cada fuente con su huella SHA-256."),
    ("ref", "doca_calificaciones"): ("ref", "Consejo Regulador DOCa Rioja", "Calificación oficial de cada añada, mantenida a mano con su URL de origen."),
}

COMENTARIOS_COLUMNA = {
    ("silver", "embalses_ebro"): {
        "pct_capacidad": "Volumen / capacidad × 100. Validado entre 0 y 100.",
        "capacidad_hm3": "AGUA_TOTAL de MITECO, en hm³ (convertida desde coma decimal).",
        "volumen_hm3": "AGUA_ACTUAL de MITECO, en hm³ (convertida desde coma decimal).",
        "_source": "Fuente de origen de la fila (solo fuentes reales permitidas).",
    },
    ("silver", "clima_logrono"): {
        "prec_mm": "Precipitación diaria en mm. 'Ip' (inapreciable) se guarda como 0,0.",
        "prec_inapreciable": "True si AEMET publicó 'Ip' para ese día.",
        "tmed": "Temperatura media diaria (ºC). Base del índice de Winkler.",
    },
    ("gold", "campana_vitivinicola"): {
        "winkler_gdd": "Suma de max(tmed - 10, 0) del 1 de abril al 31 de octubre (grados-día ºC).",
        "completitud_pct": "Días con temperatura válida sobre los 214 de la campaña.",
        "calificacion": "Calificación oficial DOCa Rioja (nula en la campaña en curso).",
    },
}

def sql_txt(x: str) -> str:
    return x.replace("\\", "\\\\").replace("'", "\\'")


resultado = []
for (schema, nombre), (capa, fuente, comentario) in TABLAS.items():
    t = tabla(schema, nombre)
    if not spark.catalog.tableExists(t):
        resultado.append((t, "no existe (aún)"))
        continue
    spark.sql(f"COMMENT ON TABLE {t} IS '{sql_txt(comentario)}'")
    try:
        spark.sql(f"""ALTER TABLE {t} SET TAGS (
            'clasificacion' = 'publico', 'capa' = '{capa}', 'fuente' = '{fuente}',
            'datos_personales' = 'no', 'proyecto' = 'tfm_embalses')""")
        estado = "comentario + etiquetas"
    except Exception as exc:  # noqa: BLE001
        estado = f"comentario (etiquetas no disponibles: {type(exc).__name__})"
    for col, txt in COMENTARIOS_COLUMNA.get((schema, nombre), {}).items():
        spark.sql(f"ALTER TABLE {t} ALTER COLUMN {col} COMMENT '{sql_txt(txt)}'")
    resultado.append((t, estado))

display(spark.createDataFrame(resultado, "tabla string, gobierno string"))

# COMMAND ----------

# MAGIC %md ## Exposición mínima para el dashboard
# MAGIC La app de Streamlit se ejecuta con su propio *service principal*. Se le da acceso de solo
# MAGIC lectura a `gold`, `ops` y `ref`, y **ninguno** a `bronze` ni `quarantine`.
# MAGIC Escribe su identificador en el widget `principal_app` (se ve en Compute › Apps › tu app › Authorization)
# MAGIC y vuelve a ejecutar esta celda.

# COMMAND ----------

if PRINCIPAL_APP:
    p = f"`{PRINCIPAL_APP}`"
    spark.sql(f"GRANT USE CATALOG ON CATALOG {CATALOG} TO {p}")
    for schema in ("gold", "ops", "ref"):
        spark.sql(f"GRANT USE SCHEMA, SELECT ON SCHEMA {CATALOG}.{schema} TO {p}")
    print(f"Permisos de lectura concedidos a {PRINCIPAL_APP} en gold, ops y ref")
    for schema in ("gold", "ops", "ref", "bronze", "quarantine"):
        print(f"\n--- {schema} ---")
        display(spark.sql(f"SHOW GRANTS ON SCHEMA {CATALOG}.{schema}"))
else:
    print("Sin principal de la app todavía: se configura después de crear la app (F6).")
