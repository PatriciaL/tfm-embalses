# Registro de uso de IA · TFM Embalses

Campos según la guía del TFM (§7). Solo se registran los intercambios que afectaron a decisiones, código, modelo, reglas o resultados.

---

## IA-001 · Diagnóstico del pipeline heredado

| Campo | Contenido |
|---|---|
| **Fecha y tarea** | 24/10/2026, 17:35–17:46. Diagnosticar el estado de los notebooks del caso de embalses (agosto de 2026) frente a los requisitos del TFM. |
| **Herramienta o modelo** | Claude (Claude Opus 5.5) en claude.ai, proyecto "JAKALA IA". |
| **Entrada relevante** | Export ZIP de la carpeta `kinedrik_caso_practico_embalses` (9 notebooks y 5 CSV de ejemplo) y la guía del TFM. Petición: inventariar qué hace cada notebook, qué fuentes son reales o de ejemplo, qué tablas genera, qué funciona y qué falta frente a la guía. Sin secretos: la API key de AEMET está en un secret scope y no aparece en el código. Sin datos personales. |
| **Salida utilizada** | Documento `diagnostico.md`, con 12 hallazgos en fuentes, silver, gold y modelos, lo aprovechable, una fuente real candidata (histórico BD-Embalses de MITECO) y una propuesta de alcance. Se incorpora completo como documento de trabajo y fuente de las secciones 2–3 de la memoria. |
| **Verificación** | Hecha: revisión humana del documento (24/10, 17:49). Pendiente: (a) confirmar en la primera ejecución los hallazgos marcados "a verificar", en especial el 1 (fallback a CSV) y el 5 (coma decimal), con captura de los mensajes del log; (b) comprobar la estructura real del Excel de MITECO en F3. |
| **Decisión humana** | Aceptado el diagnóstico completo como base del alcance. La propuesta de alcance (§6) queda pendiente de decisión en F1. |

**Para el ROI:** diagnóstico asistido de unos 15 minutos de IA más unos 5 de revisión humana. La línea base manual está sin medir: estimación de 2–3 horas para leer 9 notebooks y cruzarlos con la guía (*estimación, a declarar como supuesto*).

## IA-002 · Primera versión del pipeline nuevo

| Campo | Contenido |
|---|---|
| **Fecha y tarea** | 24/10/2026, 18:40–19:10. Escribir la primera versión del pipeline con fuentes reales (AEMET 9170 y MITECO Ebro), cuarentena, controles de calidad, gold del indicador de campaña y operación registrada. |
| **Herramienta o modelo** | Claude (Claude Opus 5.5) en claude.ai, con acceso de escritura al repositorio `PatriciaL/tfm-embalses`. |
| **Entrada relevante** | Diagnóstico F0, decisiones D-01 a D-13 y resultados reales de las pruebas de conectividad y lectura (E-01 a E-05). Sin secretos ni datos personales. |
| **Salida utilizada** | Notebooks `00`–`04`, módulo `transforms.py` (lógica pura) y `common.py` (configuración y registro), 11 pruebas unitarias, README, CLAUDE.md, definición del Job y CSV de referencia DOCa con 3 añadas (2021–2023) tomadas de prensa y pendientes de verificar en la fuente oficial. |
| **Verificación** | Hecha: las 11 pruebas pasan en local (`pytest`), cubriendo coma decimal, `Ip`, control de esquema, estados de calidad, deduplicación, idempotencia y Winkler. Primera ejecución completa en Databricks el 24/10 (18:58–19:15): bronze, silver, 14 controles de calidad superados y gold publicado (evidencias E-06 a E-15). Única corrección necesaria: reinicio de Python tras `%pip` (INC-03). |
| **Decisión humana** | Aceptado tras la ejecución en la plataforma. Pendiente de contrastar con bibliografía que los valores de Winkler de Logroño (≈1.950–2.380 en 2022–2026) son coherentes. |

**Hallazgo lateral:** las calificaciones DOCa del CSV de ejemplo heredado no coinciden con la tabla oficial del Consejo Regulador: **6 de sus 10 añadas (2015–2024) son erróneas** (2016, 2017, 2018, 2019, 2021 y 2022). Refuerza el hallazgo 1: los datos de ejemplo eran inventados.

## IA-003 · Calificaciones oficiales DOCa Rioja

| Campo | Contenido |
|---|---|
| **Fecha y tarea** | 24/10/2026, 18:55. Completar `ref/doca_calificaciones.csv` con la calificación oficial de cada añada. |
| **Herramienta o modelo** | Claude (Claude Opus 5.5) con búsqueda web. |
| **Entrada relevante** | Petición de buscar la tabla oficial del Consejo Regulador. Sin datos personales. |
| **Salida utilizada** | 2001–2025 desde la web oficial (riojawine.com/es/doca-rioja/anadas/); 2000 desde una fuente secundaria (anadas-do.com), marcada con `tipo_fuente = secundaria` porque la web oficial no la mostraba en la primera página. |
| **Verificación** | Automática: los datos 2001–2025 se leyeron directamente de la página oficial; cada fila conserva su URL de origen para poder auditarla. Sin contraste manual adicional. |
| **Decisión humana** | 24/10, 18:54: aceptado tal cual por prioridad de tiempo. Límite declarado: la añada 2000 procede de una fuente secundaria. |
