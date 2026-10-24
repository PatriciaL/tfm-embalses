# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Gold — Indicadores para el dashboard
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

reserva = spark.sql(f"""
  SELECT fecha,
         count(DISTINCT embalse)                         AS n_embalses,
         round(sum(volumen_hm3), 1)                      AS volumen_hm3,
         round(sum(capacidad_hm3), 1)                    AS capacidad_hm3,
         round(sum(volumen_hm3) / sum(capacidad_hm3) * 100, 2) AS pct_capacidad
  FROM {S_EMB} GROUP BY fecha ORDER BY fecha""")
guardar(reserva, "reserva_ebro_semanal")

actual = spark.sql(f"""
  SELECT embalse, fecha, capacidad_hm3, volumen_hm3, pct_capacidad, electrico
  FROM (SELECT *, row_number() OVER (PARTITION BY embalse ORDER BY fecha DESC) AS rn FROM {S_EMB})
  WHERE rn = 1""")
guardar(actual, "reserva_embalses_actual")

# COMMAND ----------

# MAGIC %md ## Indicador de campaña vitícola (D-06)

# COMMAND ----------

clima_pd = spark.read.table(S_CLI).select("fecha", "prec_mm", "tmed").toPandas()
reserva_pd = reserva.select("fecha", "pct_capacidad").toPandas()
campana = campana_vitivinicola(clima_pd, reserva_pd)

ref = tabla("ref", "doca_calificaciones")
if spark.catalog.tableExists(ref):
    doca = spark.read.table(ref).select("anyada", "calificacion").toPandas()
    doca["anyo"] = doca["anyada"].astype(int)
    campana = campana.merge(doca[["anyo", "calificacion"]], on="anyo", how="left")
else:
    campana["calificacion"] = None
campana["calificacion"] = campana["calificacion"].astype(object).where(campana["calificacion"].notna(), None)
campana["campana_en_curso"] = campana["anyo"] == dt.date.today().year

guardar(spark.createDataFrame(campana.astype(object).where(campana.notna(), None)), "campana_vitivinicola")
print(campana.tail(5).to_string())

# COMMAND ----------

# MAGIC %md ## KPIs de cabecera

# COMMAND ----------

r = reserva_pd.sort_values("fecha")
ultima_fecha, ultimo_pct = r["fecha"].iloc[-1], float(r["pct_capacidad"].iloc[-1])
anterior_pct = float(r["pct_capacidad"].iloc[-2]) if len(r) > 1 else None
hace_un_anyo = r[pd.to_datetime(r["fecha"]) <= pd.to_datetime(ultima_fecha) - pd.Timedelta(days=364)]
pct_anyo_ant = float(hace_un_anyo["pct_capacidad"].iloc[-1]) if len(hace_un_anyo) else None

anyo = dt.date.today().year
fila_campana = campana[campana["anyo"] == anyo]
lluvia_campana = float(fila_campana["lluvia_campana_mm"].iloc[0]) if len(fila_campana) else None
winkler = float(fila_campana["winkler_gdd"].iloc[0]) if len(fila_campana) else None

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
