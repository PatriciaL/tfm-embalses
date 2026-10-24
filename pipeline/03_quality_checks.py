# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Calidad — controles repetibles con resultado registrado
# MAGIC
# MAGIC **En una frase:** es el "semáforo" antes de publicar. Comprueba que los datos de silver son
# MAGIC fiables y, si algo grave falla, **impide que lleguen al dashboard**.
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
# MAGIC
# MAGIC **Por qué dos niveles:** un dato duplicado o inventado invalida los indicadores (crítico);
# MAGIC un dato algo antiguo o un salto raro merece atención, pero los indicadores siguen siendo válidos (aviso).

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 1 · Preparar los controles
# MAGIC - **`control(...)`**: apunta el resultado de un control (nombre, tabla, nivel, si pasa, valor
# MAGIC   medido y umbral) y lo imprime con ✔ o ✘.
# MAGIC - **`escalar(sql)`**: ejecuta una consulta que devuelve un solo número.
# MAGIC - Se definen los nombres de las seis tablas que se revisan (bronze, silver y quarantine de cada fuente).

# COMMAND ----------

import datetime as dt

from common import log_calidad, resolver_run_id, tabla
from transforms import FUENTES_PERMITIDAS

RUN_ID = resolver_run_id(dbutils)
resultados = []   # aquí se acumulan todos los controles; se guardan juntos al final


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

# MAGIC %md
# MAGIC ## Controles críticos
# MAGIC ### Celda 2 · Los 9 controles que bloquean la publicación
# MAGIC 1. **Unicidad (×2):** cuenta las claves repetidas en silver (embalse + fecha; estación + fecha).
# MAGIC    Debe ser 0: si hubiera duplicados, la reserva o la lluvia se sumarían dos veces.
# MAGIC 2. **Sin datos sintéticos (×2):** cuenta filas cuyo `_source` no es una fuente real permitida
# MAGIC    (`miteco_bd_embalses`, `aemet_opendata`). Debe ser 0. Es la garantía de que no se cuela
# MAGIC    ningún dato de ejemplo como los del pipeline heredado.
# MAGIC 3. **Rango del % de capacidad:** un embalse no puede estar por debajo del 0 % ni por encima del 100 %.
# MAGIC 4. **Silver no vacía (×2):** tiene que haber algo que publicar.
# MAGIC 5. **Conciliación (×2):** la prueba de que **no se pierde ninguna fila**. Toma todas las claves
# MAGIC    válidas de bronze y busca las que no están ni en silver ni en quarantine (`LEFT ANTI JOIN`
# MAGIC    = "dame las de la izquierda que no tienen pareja a la derecha"). Debe salir 0.
# MAGIC    Las fechas se leen con `try_cast` para que un texto raro no rompa la consulta.

# COMMAND ----------

# 1. Unicidad: claves repetidas en silver
dup = escalar(f"SELECT count(*) FROM (SELECT embalse, fecha FROM {S_EMB} GROUP BY 1,2 HAVING count(*)>1)")
control("unicidad_embalses", S_EMB, "critica", dup == 0, dup, "= 0", "claves (embalse, fecha) repetidas")

dup = escalar(f"SELECT count(*) FROM (SELECT estacion_id, fecha FROM {S_CLI} GROUP BY 1,2 HAVING count(*)>1)")
control("unicidad_clima", S_CLI, "critica", dup == 0, dup, "= 0", "claves (estacion_id, fecha) repetidas")

# 2. Sin datos sintéticos: solo fuentes reales permitidas
permitidas = ",".join(f"'{f}'" for f in FUENTES_PERMITIDAS)
for t in (S_EMB, S_CLI):
    n = escalar(f"SELECT count(*) FROM {t} WHERE _source IS NULL OR _source NOT IN ({permitidas})")
    control("sin_datos_sinteticos", t, "critica", n == 0, n, "= 0", "filas sin fuente real identificada")

# 3. Rango físico del % de capacidad
n = escalar(f"SELECT count(*) FROM {S_EMB} WHERE pct_capacidad < 0 OR pct_capacidad > 100 OR pct_capacidad IS NULL")
control("rango_pct_capacidad", S_EMB, "critica", n == 0, n, "= 0", "filas fuera de 0-100 %")

# 4. Hay datos que publicar
for t in (S_EMB, S_CLI):
    n = escalar(f"SELECT count(*) FROM {t}")
    control("silver_no_vacia", t, "critica", n > 0, n, "> 0")

# 5. Conciliación: toda clave de bronze aparece en silver o en quarantine (no se pierde nada)
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

# MAGIC %md
# MAGIC ## Avisos
# MAGIC ### Celda 3 · Los 5 controles que avisan pero no bloquean
# MAGIC 1. **Frescura MITECO:** días desde el último dato de embalses. MITECO publica cada semana,
# MAGIC    así que más de 14 días indica que algo se ha atascado.
# MAGIC 2. **Frescura AEMET:** días desde el último dato de clima. AEMET publica con unos días de
# MAGIC    retraso; el umbral es 10 días.
# MAGIC 3. **Ratio de cuarentena (×2):** % de filas apartadas sobre el total. Si supera el 5 %,
# MAGIC    probablemente la fuente ha cambiado de formato y conviene mirarlo.
# MAGIC 4. **Salto semanal de la reserva:** compara el % de la reserva del Ebro de la última semana
# MAGIC    con el de la anterior (`lag` = "el valor de la fila anterior"). Más de 10 puntos en una
# MAGIC    semana es físicamente raro y puede indicar un error de carga.

# COMMAND ----------

hoy = dt.date.today()
# 1-2. Frescura: antigüedad del último dato de cada fuente
ult = escalar(f"SELECT max(fecha) FROM {S_EMB}")
dias = (hoy - ult).days if ult else 999
control("frescura_miteco", S_EMB, "aviso", dias <= 14, dias, "<= 14 días", f"último dato {ult}")

ult = escalar(f"SELECT max(fecha) FROM {S_CLI}")
dias = (hoy - ult).days if ult else 999
control("frescura_aemet", S_CLI, "aviso", dias <= 10, dias, "<= 10 días", f"último dato {ult}")

# 3. Ratio de cuarentena = cuarentena / (silver + cuarentena)
for s, q, nombre in ((S_EMB, Q_EMB, "embalses"), (S_CLI, Q_CLI, "clima")):
    n_s, n_q = escalar(f"SELECT count(*) FROM {s}"), escalar(f"SELECT count(*) FROM {q}")
    ratio = round(n_q / (n_s + n_q) * 100, 2) if (n_s + n_q) else 0.0
    control(f"ratio_cuarentena_{nombre}", q, "aviso", ratio <= 5, ratio, "<= 5 %", f"{n_q} de {n_s + n_q} filas")

# 4. Salto semanal: diferencia de % de reserva entre la última semana y la anterior
salto = escalar(f"""
  WITH r AS (SELECT fecha, sum(volumen_hm3)/sum(capacidad_hm3)*100 AS pct FROM {S_EMB} GROUP BY fecha),
       d AS (SELECT fecha, abs(pct - lag(pct) OVER (ORDER BY fecha)) AS dif FROM r)
  SELECT dif FROM d ORDER BY fecha DESC LIMIT 1""")
salto = round(salto, 2) if salto is not None else 0.0
control("salto_semanal_reserva", S_EMB, "aviso", salto <= 10, salto, "<= 10 puntos",
        "variación de la reserva del Ebro respecto a la semana anterior")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Celda 4 · Guardar resultados y decidir
# MAGIC - Guarda los 14 resultados en `ops.quality_results` (se ven en el dashboard, pestaña "Salud del pipeline").
# MAGIC - Resume cuántos críticos y avisos han fallado.
# MAGIC - **Si falla algún crítico, el notebook termina en error**: el Job se detiene y el notebook 04
# MAGIC   no se ejecuta, así que el dashboard sigue mostrando la última versión buena.

# COMMAND ----------

log_calidad(spark, RUN_ID, resultados)
criticos = [r["control"] for r in resultados if r["nivel"] == "critica" and not r["ok"]]
avisos = [r["control"] for r in resultados if r["nivel"] == "aviso" and not r["ok"]]
print(f"{len(resultados)} controles | críticos fallidos: {criticos} | avisos: {avisos}")
if criticos:
    raise RuntimeError(f"Controles críticos fallidos: {criticos}. Gold NO se publica en esta ejecución.")
