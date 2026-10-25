---
name: pipeline-datos-controlado
description: Construir o auditar un pipeline de datos medallion con fuentes reales, trazabilidad, cuarentena, controles de calidad, operación registrada y registro de uso de IA.
---

# Pipeline de datos controlado

Guía para llevar un flujo de datos de "parece que funciona" a **real, controlado y operable**, trabajando con IA de forma trazable. Destilada del TFM "Agua y viñedo en La Rioja" (Databricks, AEMET, MITECO), pero aplicable a cualquier plataforma.

Úsala cuando haya que: crear un pipeline nuevo desde fuentes externas, auditar uno heredado, preparar un caso de data management para un TFM o una auditoría, o añadir calidad y gobierno a un flujo que ya existe.

## Principios (no negociables)

1. **Nunca datos de ejemplo, sintéticos ni respaldos silenciosos.** Si una fuente falla, se registra el error y el paso se detiene. Nada parcial llega al consumo.
2. **Trazabilidad por fila en la capa de entrada:** `_source`, `_ingest_ts`, `_run_id` (y la huella del fichero si la fuente es un fichero).
3. **Ninguna fila se descarta sin rastro:** o va a la capa limpia (aceptada) o a cuarentena (revisión / rechazada) con su motivo.
4. **La lógica de transformación es pura y está probada:** funciones separadas del notebook, con pruebas unitarias que se ejecutan antes de cada commit.
5. **Sin secretos en el código ni en el repositorio:** gestor de secretos de la plataforma.
6. **La IA propone; la persona decide y verifica.** Cada cambio relevante hecho con IA se registra con su verificación.

## Flujo de trabajo

Trabajar **una fase cada vez**, cerrando cada una con su evidencia antes de pasar a la siguiente. No escribir código antes de la fase 0.

### Fase 0 · Diagnóstico (si hay algo heredado)
- Inventariar cada notebook o script: qué lee, qué escribe, qué fuentes son reales y cuáles de ejemplo.
- Buscar especialmente: respaldos silenciosos a ficheros de ejemplo, valores inventados ante fallos (p. ej. lluvia = 0), filas descartadas sin rastro, deduplicación arbitraria, parsing que convierte en nulo (coma decimal), KPIs de relleno.
- Salida: `docs/diagnostico.md` con hallazgos numerados (H1, H2…), cada uno marcado como confirmado o "a verificar".

### Fase 1 · Fuentes
- Probar la conectividad **desde la plataforma de ejecución**, no solo en local (las restricciones de red y de tamaño de respuesta cambian).
- Inventariar: formato, frecuencia de publicación, columnas, separador decimal, códigos especiales (p. ej. `Ip`, `Acum`), límites de la API, histórico disponible.
- Verificar identificadores (estaciones, códigos) contra el inventario oficial de la fuente.
- Los datos de referencia que cambian poco (una vez al año) van en un CSV versionado con la URL de origen de cada fila.

### Fase 2 · Entrada (bronze)
- Guardar **todo como texto**, en modo append, más las columnas de trazabilidad.
- Conservar el fichero o respuesta original en un almacenamiento de ficheros, una carpeta por fecha de carga.
- Carga incremental: pedir desde la última fecha cargada menos un solape (p. ej. 10 días) para recoger correcciones; para ficheros completos, comparar la huella SHA-256 y no recargar si no ha cambiado (`OK_SIN_CAMBIOS`).
- Control de esquema: si falta una columna esperada, detener la fuente; si aparecen columnas nuevas, registrarlas.
- Acumular los errores por fuente y fallar al final, para que todas las fuentes se intenten.

### Fase 3 · Limpieza (silver) y cuarentena
- Normalizar en funciones puras: tipos, decimales, fechas, códigos especiales (con bandera, p. ej. `prec_inapreciable`).
- Clasificar cada fila: `aceptado` / `revision` / `rechazado` + `motivo`.
- Deduplicar por clave quedándose con la **ingesta más reciente** (criterio explícito, no arbitrario).
- **Reconstruir** silver y cuarentena desde bronze en cada ejecución (sobrescribir): el resultado es idempotente.

### Fase 4 · Calidad
Cada control guarda nombre, tabla, nivel, valor, umbral y resultado en una tabla de resultados.

| Control | Nivel |
|---|---|
| Unicidad de clave en la capa limpia | crítico |
| Sin datos sintéticos: todo `_source` pertenece a la lista de fuentes permitidas | crítico |
| Rango físico de las métricas (p. ej. 0–100 %) | crítico |
| Capa limpia no vacía | crítico |
| Conciliación: ninguna clave de bronze falta en limpia ∪ cuarentena (`LEFT ANTI JOIN`) | crítico |
| Frescura del último dato frente a la frecuencia de publicación | aviso |
| Ratio de cuarentena ≤ umbral (p. ej. 5 %) | aviso |
| Salto anómalo entre periodos | aviso |

Si falla un control crítico, el paso termina en error y **no se publica** la capa de consumo.

### Fase 5 · Consumo (gold)
- Agregar con criterio explícito (p. ej. suma de volúmenes / suma de capacidades, no media de porcentajes).
- KPIs calculados desde datos y registros reales; si no se puede calcular, valor nulo, nunca relleno.
- Cada KPI con una nota explicativa y el `run_id` que lo generó.

### Fase 6 · Operación
- Job programado con las tareas en cadena y dependencia "todas correctas".
- Tabla de registro de ejecuciones: `run_id, paso, fuente, estado, inicio, fin, filas_entrada, filas_salida, detalle`.
- Registrar cada incidencia real (INC-01…) con causa y resolución. Las ejecuciones fechadas son la evidencia de operación.

### Fase 7 · Gobierno
- Comentario en cada tabla y en las columnas que generan dudas.
- Etiquetas: clasificación, capa, fuente, datos personales (sí/no), proyecto.
- Mínimo privilegio: el consumidor (dashboard, app) solo lee la capa de consumo, operación y referencia; nunca entrada ni cuarentena.
- **Comprobar cada permiso concedido** consultando los permisos efectivos: un GRANT sin error no garantiza el permiso.
- Revisar el linaje y declarar sus huecos como límite.

### Fase 8 · Documentación continua
Mantener desde el primer día, no al final:
- `docs/decisiones.md`: D-01… con fecha, decisión, motivo y evidencia.
- `docs/evidencias.md`: E-01… (capturas: qué se ve, qué demuestra, fecha o ejecución) e incidencias.
- `docs/ai_log.md`: IA-001… con fecha y tarea, herramienta o modelo, entrada relevante, salida utilizada, verificación y decisión humana.
- `CLAUDE.md` (o equivalente) en el repositorio con los principios de arriba, para que cualquier sesión de IA los cumpla.

## Trabajar con IA en este flujo

- Encargos con cinco piezas: tarea concreta, contexto mínimo, límites, formato de salida y verificación.
- La IA no ejecuta en la plataforma de datos ni maneja credenciales salvo autorización explícita; la persona ejecuta y aporta la evidencia.
- Cada salida de la IA llega con su comprobación: prueba unitaria, ejecución real con captura, control de calidad, contraste con fuente oficial o comparación de código (AST) cuando solo cambian comentarios.
- Registrar también **dónde se equivocó la IA** y cómo se detectó: es la mejor evidencia de un uso crítico.
- Si un resultado parece raro, contrastarlo con una fuente externa antes de aceptarlo o de "corregirlo".

## Notas de plataforma: Databricks Free Edition

- Las respuestas HTTP se cortan a 8 MiB: descargar por tramos con la cabecera `Range` (p. ej. 4 MiB) y comprobar el tamaño total.
- Tras `%pip install`, ejecutar `dbutils.library.restartPython()`.
- Con ANSI activado, leer fechas de texto con `try_cast(substr(x, 1, 10) AS DATE)`.
- Pasar de pandas a Spark con esquema explícito o convirtiendo `NaN`/`pd.NA` a `None`.
- Permisos de una Databricks App: usar el identificador de la app que muestra Unity Catalog (App ID), no el nombre visible; verificar con `SHOW GRANTS` o concederlo desde Catalog Explorer.
- Una app que despliega desde Git necesita acceso al repositorio (credencial o repositorio público sin secretos).
- Los pasos con pandas rompen el linaje automático de Unity Catalog: declararlo o reescribirlos en Spark.

## Checklist de cierre

- [ ] Ninguna fuente de ejemplo ni respaldo silencioso en el código.
- [ ] Trazabilidad por fila en la entrada y fichero original conservado.
- [ ] Cuarentena con motivo y conciliación a cero.
- [ ] Pruebas unitarias en verde.
- [ ] Controles críticos que bloquean la publicación, con resultados registrados.
- [ ] Job con ejecuciones fechadas e incidencias documentadas.
- [ ] Comentarios, etiquetas y permisos mínimos comprobados.
- [ ] Decisiones, evidencias y registro de IA al día.
