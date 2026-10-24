# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Gobierno — clasificación, documentación y exposición mínima
# MAGIC
# MAGIC **En una frase:** pone "etiqueta y manual de instrucciones" a cada tabla y decide quién
# MAGIC puede ver qué.
# MAGIC
# MAGIC Se ejecuta **una vez** (y de nuevo si cambian tablas). Es idempotente. No forma parte del Job diario.
# MAGIC
# MAGIC | Aspecto | Qué se hace | Dónde se ve |
# MAGIC |---|---|---|
# MAGIC | Clasificación | Etiquetas `clasificacion`, `capa`, `fuente`, `datos_personales` en cada tabla | Catalog Explorer › tabla › Tags |
# MAGIC | Documentación | Comentario de tabla y de las columnas clave | Catalog Explorer › tabla › Overview |
# MAGIC | Exposición | El dashboard solo lee `gold`, `ops` y `ref` (permiso `SELECT`), nunca bronze ni quarantine | `SHOW GRANTS` (al final) |
# MAGIC | Linaje | Unity Catalog lo registra solo al ejecutar los notebooks | Catalog Explorer › tabla › Lineage |
# MAGIC
# MAGIC **Datos personales:** ninguna fuente contiene datos personales (embalses, meteorología y
# MAGIC calificaciones de añada). Se declara explícitamente con la etiqueta `datos_personales = no`
# MAGIC y como límite en la memoria: la propagación de supresión/consentimiento no aplica.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 1 · Comentarios y etiquetas de las 14 tablas
# MAGIC - **`TABLAS`**: el inventario de todas las tablas del proyecto con su capa, su fuente y una
# MAGIC   descripción en lenguaje claro. Es, en la práctica, el catálogo de datos del proyecto.
# MAGIC - **`COMENTARIOS_COLUMNA`**: explicación de las columnas que más dudas generan (cómo se
# MAGIC   calcula el % de capacidad, qué significa "Ip", cómo se calcula Winkler…).
# MAGIC - **`sql_txt`**: escapa comillas y barras para que un texto con apóstrofo no rompa el SQL.
# MAGIC - **El bucle**, para cada tabla que exista:
# MAGIC   1. Le pone su comentario (`COMMENT ON TABLE`).
# MAGIC   2. Le pone las etiquetas (`SET TAGS`): `clasificacion = publico`, `capa`, `fuente`,
# MAGIC      `datos_personales = no` y `proyecto`. Si la plataforma no admite etiquetas, lo anota y sigue.
# MAGIC   3. Comenta sus columnas clave.
# MAGIC - Al final muestra una tabla resumen con lo aplicado a cada tabla.
# MAGIC - El widget `principal_app` se usa en la celda 2.

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
    # Escapa barras y comillas simples para usar el texto dentro de '...' en SQL
    return x.replace("\\", "\\\\").replace("'", "\\'")


resultado = []
for (schema, nombre), (capa, fuente, comentario) in TABLAS.items():
    t = tabla(schema, nombre)
    if not spark.catalog.tableExists(t):
        resultado.append((t, "no existe (aún)"))
        continue
    # 1. Comentario de la tabla
    spark.sql(f"COMMENT ON TABLE {t} IS '{sql_txt(comentario)}'")
    # 2. Etiquetas de clasificación
    try:
        spark.sql(f"""ALTER TABLE {t} SET TAGS (
            'clasificacion' = 'publico', 'capa' = '{capa}', 'fuente' = '{fuente}',
            'datos_personales' = 'no', 'proyecto' = 'tfm_embalses')""")
        estado = "comentario + etiquetas"
    except Exception as exc:  # noqa: BLE001
        estado = f"comentario (etiquetas no disponibles: {type(exc).__name__})"
    # 3. Comentarios de las columnas clave
    for col, txt in COMENTARIOS_COLUMNA.get((schema, nombre), {}).items():
        spark.sql(f"ALTER TABLE {t} ALTER COLUMN {col} COMMENT '{sql_txt(txt)}'")
    resultado.append((t, estado))

display(spark.createDataFrame(resultado, "tabla string, gobierno string"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Exposición mínima para el dashboard
# MAGIC ### Celda 2 · Permisos de solo lectura para la app
# MAGIC La app de Streamlit se ejecuta con su propio *service principal* (un "usuario técnico" que
# MAGIC no es una persona). Principio de **mínimo privilegio**: se le da acceso de solo lectura a
# MAGIC `gold`, `ops` y `ref`, y **ninguno** a `bronze` ni `quarantine` (datos sin validar).
# MAGIC 1. Concede `USE CATALOG` (poder entrar en el catálogo).
# MAGIC 2. Concede `USE SCHEMA` + `SELECT` (entrar y leer) en gold, ops y ref.
# MAGIC 3. Muestra los permisos de los cinco esquemas para comprobarlo.
# MAGIC
# MAGIC Escribe su identificador en el widget `principal_app` y vuelve a ejecutar esta celda.
# MAGIC Si el widget está vacío, la celda no hace nada.
# MAGIC
# MAGIC **Ojo (INC-06):** el identificador correcto es el que Unity Catalog muestra para la app
# MAGIC (coincide con el *App ID* de la ficha de la app), no el nombre visible. Verifica siempre con
# MAGIC `SHOW GRANTS ON CATALOG tfm_embalses`: un GRANT sin error no garantiza el permiso. Alternativa
# MAGIC fiable (la que se usó finalmente): Catalog Explorer › Permissions › Grant, buscando la app por su nombre.

# COMMAND ----------

if PRINCIPAL_APP:
    p = f"`{PRINCIPAL_APP}`"
    # 1. Entrar en el catálogo
    spark.sql(f"GRANT USE CATALOG ON CATALOG {CATALOG} TO {p}")
    # 2. Entrar y leer solo en gold, ops y ref
    for schema in ("gold", "ops", "ref"):
        spark.sql(f"GRANT USE SCHEMA, SELECT ON SCHEMA {CATALOG}.{schema} TO {p}")
    print(f"Permisos de lectura concedidos a {PRINCIPAL_APP} en gold, ops y ref")
    # 3. Comprobación: bronze y quarantine no deben mostrar permisos para la app
    for schema in ("gold", "ops", "ref", "bronze", "quarantine"):
        print(f"\n--- {schema} ---")
        display(spark.sql(f"SHOW GRANTS ON SCHEMA {CATALOG}.{schema}"))
else:
    print("Sin principal de la app todavía: se configura después de crear la app (F6).")
