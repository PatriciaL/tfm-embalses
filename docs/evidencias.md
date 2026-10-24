# Índice de evidencias · TFM Embalses

Cada captura se guarda en Drive › TFM Embalses › 03_Evidencias_capturas con el nombre indicado. El pie responde a lo que pide la guía (§5): qué se ve, qué demuestra y en qué fecha o ejecución se obtuvo.

| # | Archivo | Fecha | Pie | Sección de la memoria |
|---|---|---|---|---|
| E-01 | `2026-10-24_conectividad_fuentes.png` | 24/10/2026 18:00 | Prueba de conectividad desde Databricks Free Edition: los dominios de AEMET y MITECO son accesibles (MITECO 200; el 404 de AEMET corresponde a la raíz de la API, no a un bloqueo). Justifica mantener la ingesta dentro de Databricks (D-09). | 2 · Fuentes |
| E-02 | `2026-10-24_incidencia_aemet_estacion_miteco_8MiB.png` | 24/10/2026 18:12 | Primera prueba de descarga real. AEMET responde autenticado pero sin datos para la estación 9170X heredada del notebook original; la descarga del histórico de MITECO se corta a los 8.388.608 bytes (8 MiB) de unos 10,4 MB. Se registran como incidencias INC-01 e INC-02. | 5 · Operación |
| E-03 | `2026-10-24_resolucion_aemet_estaciones_miteco_tramos.png` | 24/10/2026 18:27 | Resolución de INC-01 e INC-02. El inventario oficial de AEMET muestra que el indicativo de Logroño Aeropuerto es **9170** (no 9170X). El histórico de MITECO se descarga completo (10.377.727 bytes) en tres tramos HTTP Range de 4 MiB (respuestas 206); el ZIP contiene `BD-Embalses.mdb` (Access). | 5 · Operación |
| E-04 | `2026-10-24_dependencia_access_parser.png` | 24/10/2026 18:29 | Instalación de `access-parser` 0.0.6 para leer el histórico de MITECO en formato Access (.mdb). Databricks la añade al entorno del notebook, de modo que la dependencia queda declarada para el Job y para reproducir el trabajo. *Apoyo: usar solo si falta espacio para justificar la reproducibilidad.* | 3 · Método |
| E-05 | `2026-10-24_fuentes_reales_miteco_mdb_aemet_9170.png` | 24/10/2026 18:30 | Primera lectura de datos reales. MITECO: tabla `T_Datos Embalses 1988-2026` con 723.842 filas (FECHA, AMBITO_NOMBRE, EMBALSE_NOMBRE, AGUA_TOTAL, AGUA_ACTUAL, ELECTRICO_FLAG), de 1987-10-06 a **2026-10-20**: el fichero se actualiza cada semana. Los volúmenes usan **coma decimal** ("308,00"), lo que confirma el hallazgo 5 del diagnóstico. AEMET 9170: estado 200, 20 días con lluvia y temperaturas, también con coma decimal. | 2 · Fuentes |
| E-06 | `2026-10-24_bronze_primera_carga_miteco.png` | 24/10/2026 18:58 | Primera carga real de bronze con el pipeline nuevo. MITECO: 723.842 filas leídas, **125.127 filas de la cuenca del Ebro** escritas (84 embalses), último dato 20/10/2026, sin columnas nuevas. La lista de ámbitos confirma que el nombre de la cuenca es exactamente "Ebro". | 5 · Operación |
| E-07 | `2026-10-24_bronze_primera_carga_fin.png` | 24/10/2026 18:58 | El notebook de bronze termina **sin errores** en la ejecución `manual-20261024-165849-779392`: ninguna fuente ha caído al fallback (ya no existe). | 5 · Operación |
| E-08 | `2026-10-24_bronze_primera_carga_aemet.png` | 24/10/2026 18:58 | Carga histórica de AEMET (estación 9170) en 55 tramos de 180 días: **9.790 registros diarios** del 01/01/2000 al 24/10/2026, en unos 4 minutos. La cifra coincide exactamente con los días entre el 01/01/2000 y el 20/10/2026, lo que sugiere serie completa y unos 4 días de retraso de publicación (*a confirmar en silver*). AEMET devuelve 22 campos más de los esperados (humedad, presión, viento, sol…): se conservan en bronze, no se usan. | 5 · Operación |

## Incidencias

| # | Fecha | Incidencia | Causa | Resolución | Estado |
|---|---|---|---|---|---|
| INC-01 | 24/10 | AEMET no devuelve datos para la estación 9170X | Probable indicativo erróneo heredado del notebook original | Inventario oficial: el indicativo correcto es 9170 (Logroño Aeropuerto). Evidencia E-03 | Resuelta 24/10 |
| INC-02 | 24/10 | La descarga de BD-Embalses.zip se corta a los 8 MiB | Probable límite de tamaño de respuesta en la salida de Free Edition | Descarga por tramos HTTP Range de 4 MiB: el servidor los acepta (206) y el ZIP llega íntegro. Evidencia E-03 | Resuelta 24/10 |
| INC-03 | 24/10 | Aviso de Databricks: reiniciar Python tras instalar `access-parser` | `%pip` instala la librería pero la sesión no la recarga sola | Se añade `dbutils.library.restartPython()` tras la instalación (commit 5f0d84b). En la ejecución manual no llegó a bloquear | Resuelta 24/10 |
