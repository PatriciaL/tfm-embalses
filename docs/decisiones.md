# Registro de decisiones · TFM Embalses

Cada decisión con su motivo y su evidencia. Fuente de las secciones 2–3 de la memoria.

| # | Fecha | Decisión | Motivo | Evidencia / estado |
|---|---|---|---|---|
| D-01 | 24/10 | Vía caso, proyecto propio, sobre el pipeline de embalses de agosto | Ya existe la fuente y la arquitectura; la guía pide centrarse en normalización, calidad, gobierno y operación | Guía §2 |
| D-02 | 24/10 | Partir del diagnóstico F0 como punto de partida del caso | Documenta el estado heredado; cada hallazgo se convierte en mejora con evidencia de antes y después | `diagnostico.md`, IA-001 |
| D-03 | 24/10 | **Caso del vino:** "condiciones hídricas y climáticas de la campaña en La Rioja frente a añadas anteriores" | Pregunta de negocio clara con fuentes reales; elimina la mezcla Ebro/Tajo (hallazgo 9) | Decisión de Patri |
| D-04 | 24/10 | Fuentes núcleo: **AEMET** (estación de Logroño, diaria) y **MITECO** (embalses del Ebro, histórico desde 1988 y semanal). **DOCa Rioja** como dato de referencia en CSV versionado | Son las únicas fuentes reales y operables; la DOCa cambia una vez al año | Conectividad comprobada el 24/10 (captura) |
| D-05 | 24/10 | Fuera: SAIH Ebro, Canal de Isabel II, MAPA | URLs sin verificar y sin relación con el vino | Límite declarado |
| D-06 | 24/10 | Sustituir los modelos 04–06 por un **indicador de campaña vitícola**: lluvia acumulada, grados-día (Winkler) y nivel de embalses del Ebro, contrastado de forma descriptiva con la calificación DOCa | Explicable y verificable; los modelos no entrenaban con los datos disponibles y la guía no puntúa el modelado | Decisión de Patri |
| D-07 | 24/10 | Dashboard en **Streamlit como Databricks App**, con una pestaña de negocio y otra de salud del pipeline | Código en el repo (reproducible), datos en vivo y evidencia de operación | Free Edition: máx. 3 apps, se paran a las 24 h |
| D-08 | 24/10 | Repositorio en **GitHub** (cuenta de Patri), conectado a Databricks | Requisito de repositorio reproducible | Hecho: github.com/PatriciaL/tfm-embalses, Git folder en Databricks |
| D-09 | 24/10 | Ingesta dentro de Databricks (sin GitHub Actions) | Prueba de conectividad: AEMET y MITECO responden desde Free Edition | Captura `2026-10-24_conectividad_fuentes` |
| D-10 | 24/10 | Estación AEMET **9170 · Logroño Aeropuerto** como referencia climática | Estación principal de La Rioja, en el valle del Ebro y en zona de viñedo; el 9170X heredado no existe | Inventario AEMET (E-03) |
| D-11 | 24/10 | Descarga de MITECO por tramos HTTP Range de 4 MiB | Free Edition corta las respuestas a 8 MiB; el servidor admite Range | INC-02, E-03 |
| D-12 | 24/10 | MITECO: usar la tabla `T_Datos Embalses 1988-2026` filtrada por cuenca (AMBITO_NOMBRE = Ebro); volumen = AGUA_ACTUAL, capacidad = AGUA_TOTAL. Carga histórica completa una vez y después incremental por FECHA | Datos reales y semanales hasta el 20/10/2026; la próxima actualización (~27/10) cae dentro del plazo del TFM y servirá como carga real observada | E-05 |
| D-13 | 24/10 | Normalizar la coma decimal en silver para MITECO y AEMET | Confirmado con datos reales: ambas fuentes usan coma decimal (hallazgo 5) | E-05 |
| D-14 | 24/10 | Referencia DOCa: tabla oficial del Consejo Regulador (2001–2025) con columna `tipo_fuente`; 2000 de fuente secundaria, marcada | Trazabilidad del dato de referencia; el CSV de ejemplo heredado tenía 6 de 10 añadas mal | IA-003 |
| D-15 | 24/10 | Filtro de cuenca: AMBITO_NOMBRE = "Ebro" (84 embalses) | La lista completa de ámbitos de MITECO confirma el nombre exacto y que no hay otro ámbito que lo contenga | E-06 |
| D-16 | 24/10 | Job diario `tfm_embalses_diario` a las 07:37, 4 tareas en cadena con "All succeeded" | Operación desatendida y fechada; si falla un paso no se publica nada parcial | E-16 |
| D-17 | 24/10 | Aceptar como límite que el linaje automático de Unity Catalog no enlaza tablas en los pasos con pandas (silver y campaña) | Reescribir esos pasos en Spark no compensa con el plazo; la trazabilidad por fila (_source, _ingest_ts, _run_id) y ops.run_log cubren el requisito | E-20 |
| D-18 | 24/10 | Repositorio GitHub **público** | La app necesita leer el código; sin secretos en el repo (revisado); el tribunal puede acceder sin permisos | INC-05 |

## Abiertas

- Leer las 723.842 filas con access-parser es lento: valorar filtrar por cuenca antes de pasar a Spark.
