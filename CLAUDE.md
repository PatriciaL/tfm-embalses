# Contexto para Claude Code · TFM Embalses

Proyecto: TFM de Patricia Lafuente (Jxpert IA Aplicada, Track Data). Entrega el **30/10/2026**.
Caso: condiciones hídricas y climáticas de la campaña en La Rioja frente a las añadas DOCa.
Plataforma: Databricks Free Edition (serverless), catálogo `tfm_embalses`. Idioma del código y docs: español.

## Reglas
- **Nunca** introducir datos de ejemplo, sintéticos ni fallbacks silenciosos: si una fuente falla, se registra en `ops.run_log` y se detiene.
- Toda fila de bronze lleva `_source`, `_ingest_ts`, `_run_id`.
- Ninguna fila se descarta sin rastro: o va a silver (aceptado) o a quarantine (revisión / rechazado, con motivo).
- La lógica de transformación va en `pipeline/transforms.py` con su prueba en `tests/`. Ejecutar `pytest -q tests/` antes de cada commit.
- No escribir secretos en el repositorio: la key de AEMET está en el secret scope `caso-practico`.
- Cada cambio relevante hecho con IA se registra en `docs/ai_log.md` (fecha, herramienta, entrada, salida, verificación, decisión humana).
- Las decisiones van a `docs/decisiones.md`; las capturas e incidencias, a `docs/evidencias.md`.

## Límites de Free Edition a recordar
- Respuestas HTTP cortadas a 8 MiB → descargar por tramos (`Range`).
- Salida a internet restringida a dominios de confianza (AEMET y MITECO sí funcionan).
- Máximo 5 tareas de Job concurrentes; apps paradas a las 24 h.
