# TFM · Agua y viñedo en La Rioja

**Trabajo Fin de Máster · Jxpert IA Aplicada · Track 9 · IA aplicada a Data Management**
Autora: Patricia Lafuente · Vía caso (proyecto propio)

Pregunta de negocio: **¿cómo están las condiciones hídricas y climáticas de la campaña en La Rioja
comparadas con añadas anteriores?**

El punto de partida es un pipeline de embalses heredado que *parecía* funcionar pero cargaba datos de
ejemplo y datos sintéticos sin avisar (ver [`docs/diagnostico.md`](docs/diagnostico.md)). Este repositorio
lo convierte en un pipeline **con datos reales, controlado y operable**.

## Fuentes

| Fuente | Qué aporta | Frecuencia | Acceso |
|---|---|---|---|
| **AEMET OpenData** · estación 9170 Logroño Aeropuerto | Lluvia y temperaturas diarias | Diaria | API REST con key gratuita |
| **MITECO** · BD-Embalses (Boletín Hidrológico) | Reserva semanal de los embalses de la cuenca del Ebro desde 1988 | Semanal | ZIP con base de datos Access |
| **DOCa Rioja** · calificación de añadas | Referencia para contrastar las campañas | Anual | CSV mantenido a mano en `ref/` |

## Arquitectura

```
AEMET API ─┐                                   ┌─ silver.embalses_ebro ─┐
           ├─▶ bronze (texto, append, origen) ─┤                        ├─▶ 03 calidad ─▶ gold ─▶ app Streamlit
MITECO ZIP ┘   + volumen raw por fecha          └─ silver.clima_logrono ─┘     │
                                                  quarantine.* (motivo)        └─▶ ops.quality_results
                       ops.run_log · ops.source_files  ◀── cada paso registra su ejecución
```

| Notebook | Qué hace |
|---|---|
| `pipeline/00_setup.py` | Catálogo `tfm_embalses`, esquemas, volumen `raw`, tablas `ops` y referencia DOCa (una vez) |
| `pipeline/01_bronze_ingest.py` | Ingesta incremental real. Sin fallbacks: si una fuente falla, se registra y el Job se detiene |
| `pipeline/02_silver_transform.py` | Coma decimal, `Ip`, deduplicación por ingesta más reciente, aceptado / revisión / rechazado |
| `pipeline/03_quality_checks.py` | Controles críticos (bloquean gold) y avisos, guardados en `ops.quality_results` |
| `pipeline/04_gold_publish.py` | Reserva del Ebro, indicador de campaña vitícola (Winkler), KPIs |
| `pipeline/05_governance.py` | Comentarios, etiquetas de clasificación y permisos de solo lectura para la app (una vez) |
| `app/` | Dashboard Streamlit como Databricks App: campaña frente a DOCa y salud del pipeline |

Las transformaciones están en `pipeline/transforms.py` (pandas puro) y se prueban en local.

## Reproducir

**Requisitos:** cuenta de Databricks (vale Free Edition) y API key gratuita de AEMET
(https://opendata.aemet.es/centrodedescargas/altaUsuario).

1. En Databricks: *Workspace → Create → Git folder* con la URL de este repositorio.
2. Guarda la key de AEMET en el secret scope `caso-practico`, clave `aemet_api_key`
   (notebook `00_setup_secrets` del proyecto heredado, o la CLI de Databricks).
3. Ejecuta `pipeline/00_setup.py` una vez.
4. Ejecuta en orden `01` → `02` → `03` → `04`, o crea el Job descrito en [`jobs/job_tfm_embalses.md`](jobs/job_tfm_embalses.md).
   La primera ejecución carga el histórico (AEMET desde 2000, MITECO desde 1988) y tarda unos minutos.

5. Ejecuta `pipeline/05_governance.py` y despliega la app (ver [`app/README.md`](app/README.md)).

**Pruebas en local:**

```bash
pip install -r requirements.txt pytest
pytest -q tests/
```

## Documentación del TFM

| Documento | Contenido |
|---|---|
| [`docs/diagnostico.md`](docs/diagnostico.md) | Estado del pipeline heredado: 12 hallazgos |
| [`docs/decisiones.md`](docs/decisiones.md) | Decisiones con motivo y evidencia |
| [`docs/evidencias.md`](docs/evidencias.md) | Índice de capturas e incidencias |
| [`docs/ai_log.md`](docs/ai_log.md) | Registro de uso de IA |

## Límites conocidos

- MITECO marca su histórico como **provisional y sin validar**: por eso existe la capa de calidad.
- Una sola estación meteorológica (Logroño) representa el clima de la DOCa.
- La calificación DOCa se mantiene a mano: hay que añadir cada añada nueva.
- Databricks Free Edition corta las descargas a 8 MiB (se descarga por tramos) y apaga las apps a las 24 h.
