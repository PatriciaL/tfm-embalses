# Job `tfm_embalses_diario`

Se crea desde la interfaz: *Jobs & Pipelines → Create → Job*.

| Ajuste | Valor |
|---|---|
| Nombre | `tfm_embalses_diario` |
| Parámetro del job | `run_id` = `{{job.run_id}}` (lo heredan todas las tareas) |
| Programación | Diaria, 07:37 Europe/Madrid |
| Cómputo | Serverless |
| Notificaciones | Correo a la autora si falla |

## Tareas (en cadena: cada una depende de la anterior)

| # | Tarea | Notebook | Si falla |
|---|---|---|---|
| 1 | `bronze` | `pipeline/01_bronze_ingest` | Fuente caída o esquema cambiado: el Job se detiene, silver/gold quedan con la última versión buena |
| 2 | `silver` | `pipeline/02_silver_transform` | — |
| 3 | `calidad` | `pipeline/03_quality_checks` | Control crítico fallido: **gold no se publica** |
| 4 | `gold` | `pipeline/04_gold_publish` | — |

`00_setup` no forma parte del Job: se ejecuta una vez a mano.

## Qué esperar en la operación diaria
- **AEMET:** carga los días nuevos (con 10 días de solape). AEMET publica con unos días de retraso: es normal que algunos días no haya datos nuevos (`OK_SIN_DATOS`).
- **MITECO:** publica una vez por semana (normalmente con fecha de martes). El resto de días el fichero no cambia y se registra `OK_SIN_CAMBIOS`: es evidencia de que el pipeline comprueba y no duplica.
