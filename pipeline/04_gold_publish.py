# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Gold — Indicadores para el dashboard
# MAGIC
# MAGIC **En una frase:** a partir de los datos limpios de silver, calcula las tablas y cifras que
# MAGIC enseña el dashboard. Es "el escaparate".
# MAGIC
# MAGIC Solo se ejecuta si `03_quality_checks` no ha encontrado fallos críticos.
# MAGIC
# MAGIC | Tabla | Grano | Uso |
# MAGIC |---|---|---|
# MAGIC | `gold.reserva_ebro_semanal` | semana | Evolución de la reserva de la cuenca (suma de embalses) |
# MAGIC | `gold.reserva_embalses_actual` | embalse | Última lectura de cada embalse |
# MAGIC | `gold.campana_vitivinicola` | año (campaña abr-oct) | Lluvia, grados-día de Winkler y reserva media frente a la calificación DOCa |
# MAGIC | `gold.kpis` | KPI | Cifras de cabecera del dashboard |
# MAGIC
# MAGIC Corrige los hallazgos 9-11: el índice ya no mezcla cuencas (todo es Ebro / La Rioja),
# MAGIC no hay KPIs de relleno y las horas desde la última carga se calculan desde `ops.run_log`.
# MAGIC
# MAGIC Todas las tablas gold se **sobrescriben** en cada ejecución: siempre reflejan silver tal como está.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 1 · Preparación
# MAGIC Importa lo necesario y define `guardar`, que escribe una tabla en gold sobrescribiéndola.

# COMMAND ----------

import datetime as dt

import pandas as pd

from common import ahora, log_paso, resolver_run_id, tabla
from transforms import campana_vitivinicola

RUN_ID = resolver_run_id(dbutils)
inicio = ahora()


def guardar(sdf, nombre):
    sdf.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(tabla("gold", nombre))


S_EMB, S_CLI = tabla("silver", "embalses_ebro"), tabla("silver", "clima_logrono")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 2 · Reserva del Ebro (semanal y por embalse)
# MAGIC - **`reserva_ebro_semanal`**: para cada semana, suma el agua de todos los embalses del Ebro
# MAGIC   y su capacidad, y calcula el % de llenado de la cuenca. Ojo: es **suma de volúmenes /
# MAGIC   suma de capacidades**, no la media de porcentajes (así un embalse pequeño no pesa igual que uno grande).
# MAGIC - **`reserva_embalses_actual`**: la última lectura de cada embalse (`row_number` ordena las
# MAGIC   fechas de cada embalse de la más reciente a la más antigua y se queda con la primera).

# COMMAND ----------

# Reserva de la cuenca por semana: suma de volúmenes / suma de capacidades
reserva = spark.sql(f"""
  SELECT fecha,
         count(DISTINCT embalse)                         AS n_embalses,
         round(sum(volumen_hm3), 1)                      AS volumen_hm3,
         round(sum(capacidad_hm3), 1)                    AS capacidad_hm3,
         round(sum(volumen_hm3) / sum(capacidad_hm3) * 100, 2) AS pct_capacidad
  FROM {S_EMB} GROUP BY fecha ORDER BY fecha""")
guardar(reserva, "reserva_ebro_semanal")

# Última lectura de cada embalse
actual = spark.sql(f"""
  SELECT embalse, fecha, capacidad_hm3, volumen_hm3, pct_capacidad, electrico
  FROM (SELECT *, row_number() OVER (PARTITION BY embalse ORDER BY fecha DESC) AS rn FROM {S_EMB})
  WHERE rn = 1""")
guardar(actual, "reserva_embalses_actual")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Indicador de campaña vitícola (D-06)
# MAGIC ### Celda 3 · Una fila por campaña (1 de abril – 31 de octubre)
# MAGIC Es el corazón del caso del vino. Para cada año calcula (función `campana_vitivinicola` de `transforms.py`):
# MAGIC - **Lluvia de la campaña** (mm) en Logroño.
# MAGIC - **Índice de Winkler** (grados-día): cada día se suma lo que la temperatura media supera
# MAGIC   los 10 ºC (por debajo de 10 ºC la vid apenas crece). Más grados-día = campaña más cálida.
# MAGIC - **Reserva media del Ebro** durante la campaña.
# MAGIC - **Completitud**: % de días con temperatura válida sobre los 214 de la campaña (si faltan
# MAGIC   días, el Winkler sale más bajo de lo real; esta columna lo deja a la vista).
# MAGIC
# MAGIC Después le **pega la calificación oficial DOCa** de cada añada (`merge` por año, como un
# MAGIC BUSCARV) y marca la campaña del año actual como "en curso", porque aún no ha terminado ni
# MAGIC tiene calificación. Este paso usa pandas, por eso el linaje automático no lo dibuja (D-17).

# COMMAND ----------

# Pasar a pandas los datos necesarios y calcular el indicador por año
clima_pd = spark.read.table(S_CLI).select("fecha", "prec_mm", "tmed").toPandas()
reserva_pd = reserva.select("fecha", "pct_capacidad").toPandas()
campana = campana_vitivinicola(clima_pd, reserva_pd)

# Añadir la calificación oficial DOCa de cada añada (si la tabla de referencia existe)
ref = tabla("ref", "doca_calificaciones")
if spark.catalog.tableExists(ref):
    doca = spark.read.table(ref).select("anyada", "calificacion").toPandas()
    doca["anyo"] = doca["anyada"].astype(int)
    campana = campana.merge(doca[["anyo", "calificacion"]], on="anyo", how="left")
else:
    campana["calificacion"] = None
campana["calificacion"] = campana["calificacion"].astype(object).where(campana["calificacion"].notna(), None)
# La campaña de este año sigue abierta
campana["campana_en_curso"] = campana["anyo"] == dt.date.today().year

guardar(spark.createDataFrame(campana.astype(object).where(campana.notna(), None)), "campana_vitivinicola")
print(campana.tail(5).to_string())

# COMMAND ----------

# MAGIC %md
# MAGIC ## KPIs de cabecera
# MAGIC ### Celda 4 · Las cifras grandes de arriba del dashboard
# MAGIC | KPI | Cómo se calcula |
# MAGIC |---|---|
# MAGIC | `reserva_ebro_pct` | % de la última semana disponible |
# MAGIC | `variacion_semanal_pts` | Última semana menos la anterior (en puntos) |
# MAGIC | `variacion_anual_pts` | Última semana menos la misma semana del año pasado (364 días = 52 semanas exactas, mismo día de la semana) |
# MAGIC | `lluvia_campana_mm` | Lluvia de la campaña en curso |
# MAGIC | `winkler_campana_gdd` | Grados-día de la campaña en curso |
# MAGIC | `horas_desde_carga_miteco` | Horas desde la última carga **real** de MITECO, leídas de `ops.run_log` (no inventadas, hallazgo 11) |
# MAGIC
# MAGIC Si algún valor no se puede calcular (por ejemplo, falta la semana anterior), se guarda vacío
# MAGIC en lugar de rellenarlo. Cada KPI lleva una nota explicativa y el `run_id` que lo generó.
# MAGIC Al final se apunta el paso en `ops.run_log`.

# COMMAND ----------

r = reserva_pd.sort_values("fecha")
# Última semana y la anterior
ultima_fecha, ultimo_pct = r["fecha"].iloc[-1], float(r["pct_capacidad"].iloc[-1])
anterior_pct = float(r["pct_capacidad"].iloc[-2]) if len(r) > 1 else None
# Misma semana del año anterior (364 días atrás o antes)
hace_un_anyo = r[pd.to_datetime(r["fecha"]) <= pd.to_datetime(ultima_fecha) - pd.Timedelta(days=364)]
pct_anyo_ant = float(hace_un_anyo["pct_capacidad"].iloc[-1]) if len(hace_un_anyo) else None

# Lluvia y Winkler de la campaña en curso
anyo = dt.date.today().year
fila_campana = campana[campana["anyo"] == anyo]
lluvia_campana = float(fila_campana["lluvia_campana_mm"].iloc[0]) if len(fila_campana) else None
winkler = float(fila_campana["winkler_gdd"].iloc[0]) if len(fila_campana) else None

# Horas desde la última carga de MITECO con datos nuevos (estado OK en run_log)
ult_ok = spark.sql(f"""
  SELECT max(fin) FROM {tabla('ops', 'run_log')}
  WHERE paso = '01_bronze' AND fuente = 'miteco' AND estado = 'OK'""").first()[0]
horas = None
if ult_ok:
    horas = round((dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ult_ok)).total_seconds() / 3600, 1)

kpis = [
    ("reserva_ebro_pct", ultimo_pct, f"semana del {ultima_fecha}"),
    ("variacion_semanal_pts", round(ultimo_pct - anterior_pct, 2) if anterior_pct is not None else None, "frente a la semana anterior"),
    ("variacion_anual_pts", round(ultimo_pct - pct_anyo_ant, 2) if pct_anyo_ant is not None else None, "frente a la misma semana del año anterior"),
    ("lluvia_campana_mm", lluvia_campana, f"Logroño, 1 abr - hoy ({anyo})"),
    ("winkler_campana_gdd", winkler, f"Logroño, 1 abr - hoy ({anyo})"),
    ("horas_desde_carga_miteco", horas, "última carga de MITECO con datos nuevos"),
]
guardar(spark.createDataFrame([(k, v, n, RUN_ID, ahora()) for k, v, n in kpis],
                              "kpi string, valor double, nota string, run_id string, actualizado string"), "kpis")
for k in kpis:
    print(k)

log_paso(spark, RUN_ID, "04_gold", "todas", "OK", inicio, None, len(campana),
         {"ultima_semana_reserva": str(ultima_fecha), "anyos_campana": int(len(campana))})
