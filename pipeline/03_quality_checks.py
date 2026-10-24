# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Calidad — controles repetibles con resultado registrado
# MAGIC
# MAGIC Cada control se guarda en `ops.quality_results` con su valor, umbral y resultado.
# MAGIC - **critica**: si falla, el notebook termina en error y **gold no se publica**.
# MAGIC - **aviso**: se registra y aparece en el dashboard, pero no bloquea.
# MAGIC
# MAGIC | Control | Qué comprueba | Nivel |
# MAGIC |---|---|---|
# MAGIC | unicidad_embalses / unicidad_clima | Una fila por clave en silver | critica |
# MAGIC | sin_datos_sinteticos | Toda fila viene de una fuente real permitida (hallazgo 2) | critica |
# MAGIC | rango_pct_capacidad | % de capacidad entre 0 y 100 en silver | critica |
# MAGIC | silver_no_vacia | Hay datos que publicar | critica |
# MAGIC | conciliacion_bronze_* | Ninguna clave de bronze se pierde: está en silver o en quarantine | critica |
# MAGIC | frescura_* | Antigüedad del último dato | aviso |
# MAGIC | ratio_cuarentena_* | % de filas no aceptadas ≤ 5 % | aviso |
# MAGIC | salto_semanal_reserva | Variación semanal de la reserva del Ebro ≤ 10 puntos | aviso |

# COMMAND ----------

import datetime as dt

from common import log_calidad, resolver_run_id, tabla
from transforms import FUENTES_PERMITIDAS

RUN_ID = resolver_run_id(dbutils)
resultados = []


def control(nombre, tabla_obj, nivel, ok, valor=None, umbral=None, detalle=None):
    resultados.append({"control": nombre, "tabla": tabla_obj, "nivel": nivel, "ok": bool(ok),
                       "valor": valor, "umbral": umbral, "detalle": detalle})
    print(f"{'✔' if ok else '✘'} [{nivel}] {nombre}: valor={valor} umbral={umbral} {detalle or ''}")


def escalar(sql):
    return spark.sql(sql).first()[0]


S_EMB, S_CLI = tabla("silver", "embalses_ebro"), tabla("silver", "clima_logrono")
Q_EMB, Q_CLI = tabla("quarantine", "embalses_ebro"), tabla("quarantine", "clima_logrono")
B_EMB, B_CLI = tabla("bronze", "miteco_embalses"), tabla("bronze", "aemet_diario")

# COMMAND ----------

# MAGIC %md ## Controles críticos

# COMMAND ----------

dup = escalar(f"SELECT count(*) FROM (SELECT embalse, fecha FROM {S_EMB} GROUP BY 1,2 HAVING count(*)>1)")
control("unicidad_embalses", S_EMB, "critica", dup == 0, dup, "= 0", "claves (embalse, fecha) repetidas")

dup = escalar(f"SELECT count(*) FROM (SELECT estacion_id, fecha FROM {S_CLI} GROUP BY 1,2 HAVING count(*)>1)")
control("unicidad_clima", S_CLI, "critica", dup == 0, dup, "= 0", "claves (estacion_id, fecha) repetidas")

permitidas = ",".join(f"'{f}'" for f in FUENTES_PERMITIDAS)
for t in (S_EMB, S_CLI):
    n = escalar(f"SELECT count(*) FROM {t} WHERE _source IS NULL OR _source NOT IN ({permitidas})")
    control("sin_datos_sinteticos", t, "critica", n == 0, n, "= 0", "filas sin fuente real identificada")

n = escalar(f"SELECT count(*) FROM {S_EMB} WHERE pct_capacidad < 0 OR pct_capacidad > 100 OR pct_capacidad IS NULL")
control("rango_pct_capacidad", S_EMB, "critica", n == 0, n, "= 0", "filas fuera de 0-100 %")

for t in (S_EMB, S_CLI):
    n = escalar(f"SELECT count(*) FROM {t}")
    control("silver_no_vacia", t, "critica", n > 0, n, "> 0")

# Conciliación: toda clave de bronze aparece en silver o en quarantine (no se pierde nada)
perdidas = escalar(f"""
  SELECT count(*) FROM (SELECT DISTINCT trim(EMBALSE_NOMBRE) AS embalse, try_cast(substr(FECHA, 1, 10) AS DATE) AS fecha FROM {B_EMB}
                        WHERE try_cast(substr(FECHA, 1, 10) AS DATE) IS NOT NULL AND trim(EMBALSE_NOMBRE) <> '') b
  LEFT ANTI JOIN (SELECT embalse, fecha FROM {S_EMB} UNION SELECT embalse, fecha FROM {Q_EMB}) s
  ON b.embalse = s.embalse AND b.fecha = s.fecha""")
control("conciliacion_bronze_embalses", B_EMB, "critica", perdidas == 0, perdidas, "= 0",
        "claves de bronze que no están ni en silver ni en quarantine")

perdidas = escalar(f"""
  SELECT count(*) FROM (SELECT DISTINCT trim(indicativo) AS estacion_id, try_cast(substr(fecha, 1, 10) AS DATE) AS fecha FROM {B_CLI}
                        WHERE try_cast(substr(fecha, 1, 10) AS DATE) IS NOT NULL) b
  LEFT ANTI JOIN (SELECT estacion_id, fecha FROM {S_CLI} UNION SELECT estacion_id, fecha FROM {Q_CLI}) s
  ON b.estacion_id = s.estacion_id AND b.fecha = s.fecha""")
control("conciliacion_bronze_clima", B_CLI, "critica", perdidas == 0, perdidas, "= 0",
        "claves de bronze que no están ni en silver ni en quarantine")

# COMMAND ----------

# MAGIC %md ## Avisos

# COMMAND ----------

hoy = dt.date.today()
ult = escalar(f"SELECT max(fecha) FROM {S_EMB}")
dias = (hoy - ult).days if ult else 999
control("frescura_miteco", S_EMB, "aviso", dias <= 14, dias, "<= 14 días", f"último dato {ult}")

ult = escalar(f"SELECT max(fecha) FROM {S_CLI}")
dias = (hoy - ult).days if ult else 999
control("frescura_aemet", S_CLI, "aviso", dias <= 10, dias, "<= 10 días", f"último dato {ult}")

for s, q, nombre in ((S_EMB, Q_EMB, "embalses"), (S_CLI, Q_CLI, "clima")):
    n_s, n_q = escalar(f"SELECT count(*) FROM {s}"), escalar(f"SELECT count(*) FROM {q}")
    ratio = round(n_q / (n_s + n_q) * 100, 2) if (n_s + n_q) else 0.0
    control(f"ratio_cuarentena_{nombre}", q, "aviso", ratio <= 5, ratio, "<= 5 %", f"{n_q} de {n_s + n_q} filas")

salto = escalar(f"""
  WITH r AS (SELECT fecha, sum(volumen_hm3)/sum(capacidad_hm3)*100 AS pct FROM {S_EMB} GROUP BY fecha),
       d AS (SELECT fecha, abs(pct - lag(pct) OVER (ORDER BY fecha)) AS dif FROM r)
  SELECT dif FROM d ORDER BY fecha DESC LIMIT 1""")
salto = round(salto, 2) if salto is not None else 0.0
control("salto_semanal_reserva", S_EMB, "aviso", salto <= 10, salto, "<= 10 puntos",
        "variación de la reserva del Ebro respecto a la semana anterior")

# COMMAND ----------

log_calidad(spark, RUN_ID, resultados)
criticos = [r["control"] for r in resultados if r["nivel"] == "critica" and not r["ok"]]
avisos = [r["control"] for r in resultados if r["nivel"] == "aviso" and not r["ok"]]
print(f"{len(resultados)} controles | críticos fallidos: {criticos} | avisos: {avisos}")
if criticos:
    raise RuntimeError(f"Controles críticos fallidos: {criticos}. Gold NO se publica en esta ejecución.")
