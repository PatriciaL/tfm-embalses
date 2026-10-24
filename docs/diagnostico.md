# F0 · Diagnóstico del pipeline de embalses

**TFM Jxpert IA · Track Data** · Revisión del 24/10/2026 sobre el export `kinedrik_caso_practico_embalses.zip` (notebooks de agosto de 2026).
Método: lectura del código y de los CSV de `sample_data/`. **No se ha ejecutado nada**: lo que depende de la ejecución está marcado como *a verificar*.

---

## 1. Qué hay

| Pieza | Qué hace | Estado |
|---|---|---|
| `00_setup_secrets` | Guarda la API key de AEMET en el secret scope `caso-practico` | ✅ Correcto: la key no queda en el código |
| `00b_setup_catalog` | Crea el catálogo `embalses_caso_practico` y los esquemas `bronze`, `silver`, `gold` | ✅ Correcto |
| `01_bronze_ingest` | Ingesta de 6 fuentes en `bronze.*`, en modo append, con `_ingest_date` y `_source` | ⚠️ Ver hallazgos 1–3 |
| `02_silver_transform` | Unifica los embalses en `silver.embalses` (embalse, fecha, cuenca, volumen, capacidad, %), valida rangos y copia lluvia, añadas y producciones | ⚠️ Ver hallazgos 4–8 |
| `03_gold_aggregate` | `gold.capacidad_embalses` (última lectura), `gold.indice_estres_hidrico` (año × cuenca) y `gold.kpis_proyecto` (4 KPIs) | ⚠️ Ver hallazgos 9–11 |
| `04–06_model_*` | XGBoost de nivel de embalse, clasificador agua→añada de Rioja y regresión agua→huerta, con MLflow | ⏸️ Fuera del núcleo del TFM (hallazgo 12) |
| `sample_data/` | 5 CSV de ejemplo (SAIH, MITECO, Canal, DOCa, MAPA) | Datos inventados de julio de 2026 |

Lo que **no** está en el export: definición del Job, README, repositorio Git, tests, tabla de log de ejecuciones, tabla de resultados de calidad, cuarentena, y la "skill" `query_gold.py` y el Power BI que mencionan los notebooks.

## 2. Hallazgos

### Fuentes (lo más grave)

1. **El pipeline funciona casi siempre con datos de ejemplo, sin decirlo.** SAIH Ebro, MITECO, Canal de Isabel II y MAPA intentan URLs marcadas `# VERIFICAR`, que con toda probabilidad no existen. Si fallan, cargan el CSV de `sample_data/`, y solo lo dejan escrito en un `print`. DOCa Rioja lee siempre el CSV. En la tabla bronze no queda ninguna marca que distinga un dato real de uno de ejemplo. *A verificar en la primera ejecución.*
2. **AEMET inventa datos cuando falla.** Si la API no responde, se inserta una lectura sintética de **0,0 mm de lluvia**. Ese cero llega a `silver.lluvia` y al índice de estrés hídrico como si fuera una observación real. Es el error de calidad más serio del código.
3. **Cada ejecución vuelve a cargar los mismos CSV de ejemplo** con una `_ingest_date` nueva. Bronze crece con copias idénticas, y operar varios días no aporta datos nuevos.

### Silver

4. **Las filas que no pasan la validación se descartan sin rastro.** `validate()` las filtra y solo imprime cuántas son. No existe cuarentena ni registro del motivo, y la guía pide separar aceptados, en revisión y rechazados.
5. **No se tratan los decimales con coma.** `cast(DoubleType)` sobre "1.319,5" devuelve `null`, y la fila se pierde en la validación sin ningún aviso. **Confirmado el 24/10** con los datos reales: MITECO ("308,00") y AEMET ("13,2") usan coma decimal (evidencia E-05).
6. **La deduplicación es arbitraria.** `dropDuplicates(["embalse","fecha"])` se queda con una fila cualquiera:
   - en SAIH, que es horario, la del día puede ser la de cualquier hora;
   - El Atazar, Santillana y Pinilla llegan a la vez por MITECO y por Canal con la misma fecha, y gana una fuente al azar;
   - las copias de bronze de distintos días de ingesta no tienen criterio de "la más reciente".
7. **`silver.lluvia` no es idempotente.** Se escribe en modo append sin deduplicar, así que cada reejecución duplica la lluvia y distorsiona la lluvia acumulada.
8. **Un cambio de nombre de columna en origen rompe el pipeline** con un error genérico. No hay comprobación de esquema esperado.

### Gold

9. **El índice de estrés hídrico mezcla cuencas.** La lluvia es de una sola estación (Logroño, Ebro) y se une solo por año, de modo que se aplica también a la cuenca del Tajo. Además, con un solo año de datos la normalización min–max devuelve 0,5 constante.
10. **`estres_hidrico_actual` está mal calculado.** El `orderBy(...).agg(avg)` hace la media de todos los años, no del último.
11. **Hay KPIs de relleno.** `horas_desde_ultima_ejecucion` vale siempre 0,0 y `mae_modelo_nivel` vale -1 hasta que corre el notebook 04.

### Modelos

12. Con los datos de ejemplo, los modelos 05 y 06 no encuentran años comunes (el índice solo tiene 2026 y las añadas van de 2015 a 2024) y no entrenan; el 04 tiene muy pocas filas. Los propios notebooks lo avisan. Para el TFM no aportan evidencia de calidad ni de operación.

## 3. Lo que está bien y se aprovecha

- Arquitectura medallion sobre Unity Catalog con tablas Delta registradas, consultables por SQL y por el dashboard.
- Bronze en append con fecha de ingesta y fuente: base correcta para la trazabilidad y para demostrar cargas sucesivas.
- Secretos fuera del código.
- Parámetro `run_date` y rutas absolutas, ya pensados para ejecutarse como Job.
- Documentación honesta en los propios notebooks sobre qué está verificado y qué no.

## 4. Fuente real disponible

MITECO publica en la página del Boletín Hidrológico un histórico descargable (`BD-Embalses.zip`, en Excel) con la capacidad y la reserva semanal de **cada embalse peninsular de más de 5 hm³ desde 1988**, más un documento de modelo de datos. Está marcado como provisional y sin validar. Fuente: [MITECO · Boletín hidrológico](https://www.miteco.gob.es/es/agua/temas/evaluacion-de-los-recursos-hidricos/boletin-hidrologico.html).

Encaja con el TFM: es real, se actualiza cada semana, cubre todas las cuencas y su propia advertencia de datos sin validar justifica la capa de calidad.
*A verificar en F3:* que la descarga funciona desde Databricks Free Edition (salida a internet) y la estructura real del Excel.

## 5. Huecos frente a la guía del TFM

| Requisito de la guía | Estado actual |
|---|---|
| Normalización trazable | Parcial: sin coma decimal, sin control de esquema, deduplicación arbitraria |
| Aceptados / revisión / rechazados | ❌ No existe |
| Controles repetibles con resultado registrado | ❌ Solo un filtro con `print` |
| Gobierno (clasificación, exposición, linaje) | ❌ Nada explícito; los datos son públicos y sin datos personales |
| Operación: ejecuciones fechadas, logs e incidencias | ❌ Sin Job versionado ni tabla de ejecuciones |
| Repositorio reproducible | ❌ Solo existe en el workspace |
| Registro de IA y ROI | ❌ Por empezar |

## 6. Propuesta de alcance (para decidir en F1)

1. **Núcleo:** MITECO real (histórico y actualización semanal) más AEMET real. El resto de fuentes quedan como límite declarado o se retiran.
2. **Primeras correcciones:** eliminar el fallback silencioso y el dato sintético de AEMET (una fuente que falla genera una incidencia, no datos), marcar el origen de cada fila, coma decimal, deduplicación con criterio, lluvia idempotente y control de esquema.
3. **Capas nuevas:** `quarantine`, `ops.run_log`, `ops.quality_results` y parada de la publicación en gold si falla una regla crítica.
4. **Gold:** corregir el KPI de estrés, calcular las horas desde la última ejecución a partir de `run_log` y limitar el índice a la cuenca del Ebro, donde está la estación de lluvia, o declararlo como límite.
5. **Modelos 04–06:** fuera del alcance, mencionados como trabajo previo.

> Los hallazgos 1, 2, 4 y 6 son buen material para la memoria: el diagnóstico de un pipeline heredado que "funcionaba" pero producía datos no verificables es justo lo que la guía pide demostrar.
