const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, AlignmentType,
  HeadingLevel, WidthType, ShadingType, BorderStyle, LevelFormat, Footer, PageNumber, PageBreak,
  TableOfContents,
} = require("docx");

const dims = JSON.parse(fs.readFileSync("dims.json", "utf8"));
const FONT = "Arial";
const CW = 9638; // ancho útil A4 con márgenes de 2 cm (DXA)
let nFig = 0;

const run = (t, o = {}) => new TextRun({ text: t, font: FONT, size: o.size || 20, bold: o.bold, italics: o.italics, color: o.color });
// Texto con **negritas** simples
function rich(t, o = {}) {
  return t.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(s =>
    s.startsWith("**") ? run(s.slice(2, -2), { ...o, bold: true }) : run(s, o));
}
const P = (t, o = {}) => new Paragraph({ children: rich(t, o), spacing: { after: 100, line: 276 }, alignment: o.align || AlignmentType.JUSTIFIED });
const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, keepNext: true, keepLines: true, children: [run(t, { size: 28, bold: true, color: "6B1D3A" })], spacing: { before: 240, after: 120 } });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, keepNext: true, keepLines: true, children: [run(t, { size: 22, bold: true, color: "333333" })], spacing: { before: 160, after: 80 } });
const B = t => new Paragraph({ numbering: { reference: "vinetas", level: 0 }, children: rich(t), spacing: { after: 50, line: 264 } });

function fig(key, caption, widthCm = 16, maxHcm = 9.5) {
  const [w, h] = dims[key];
  let wpx = widthCm / 2.54 * 96, hpx = wpx * h / w;
  const maxh = maxHcm / 2.54 * 96;
  if (hpx > maxh) { hpx = maxh; wpx = hpx * w / h; }
  nFig += 1;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 80, after: 40 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(`img/${key}.png`), transformation: { width: Math.round(wpx), height: Math.round(hpx) } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
      children: [run(`Figura ${nFig}. `, { size: 16, bold: true, color: "555555" }), run(caption, { size: 16, italics: true, color: "555555" })] }),
  ];
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "C9C9C9" };
const borders = { top: border, bottom: border, left: border, right: border };
function table(head, rows, widths, opts = {}) {
  const cell = (t, w, isHead, fill) => new TableCell({
    borders, width: { size: w, type: WidthType.DXA },
    shading: isHead ? { fill: "EBDDE2", type: ShadingType.CLEAR } : (fill ? { fill, type: ShadingType.CLEAR } : undefined),
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ children: rich(t, { size: opts.size || 17, bold: isHead }) })],
  });
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: head.map((h, i) => cell(h, widths[i], true)) }),
      ...rows.map(r => new TableRow({ children: r.map((c, i) => cell(c, widths[i], false)) }))],
  });
}
// Recuadro "Stack · Rol de la IA" al final de cada sección
function ia(stack, rol, humano) {
  const c = (label, t) => new Paragraph({ spacing: { after: 40 }, children: [run(label, { size: 17, bold: true, color: "6B1D3A" }), ...rich(t, { size: 17 })] });
  return [new Table({
    width: { size: CW, type: WidthType.DXA }, columnWidths: [CW],
    rows: [new TableRow({ children: [new TableCell({
      borders: { top: border, bottom: border, right: border, left: { style: BorderStyle.SINGLE, size: 18, color: "6B1D3A" } },
      width: { size: CW, type: WidthType.DXA }, shading: { fill: "F7F1F3", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 140, right: 140 },
      children: [c("Stack: ", stack), c("Rol de la IA: ", rol), c("Decisión y verificación humana: ", humano)],
    })] })],
  }), new Paragraph({ spacing: { after: 120 }, children: [] })];
}

const children = [];
const add = (...xs) => xs.flat().forEach(x => children.push(x));

// ---------------------------------------------------------------- Portada
add(
  new Paragraph({ spacing: { before: 1800 }, children: [run("Trabajo Fin de Máster · Jxpert IA Aplicada", { size: 22, color: "6B1D3A", bold: true })] }),
  new Paragraph({ children: [run("Track 9 · IA aplicada a Data Management · Vía caso (proyecto propio)", { size: 20, color: "555555" })] }),
  new Paragraph({ spacing: { before: 400, after: 200 }, children: [run("Agua y viñedo en La Rioja", { size: 56, bold: true })] }),
  new Paragraph({ spacing: { after: 600 }, children: [run("De un pipeline de embalses que «parecía funcionar» a un sistema de datos reales, controlado y operable", { size: 26, color: "444444" })] }),
  table(["Ficha del trabajo", ""], [
    ["Autora", "Patricia Lafuente"],
    ["Entrega", "30 de octubre de 2026"],
    ["Repositorio", "github.com/PatriciaL/tfm-embalses (público)"],
    ["Plataforma", "Databricks Free Edition · Unity Catalog · Databricks Apps"],
    ["Fuentes", "AEMET OpenData (estación 9170 Logroño) · MITECO BD-Embalses (cuenca del Ebro) · Consejo Regulador DOCa Rioja"],
  ], [2200, CW - 2200], { size: 18 }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---------------------------------------------------------------- 1
add(H1("1. Resumen y objetivo"),
  P("**Problema.** Para una bodega o un técnico de la DOCa Rioja, la pregunta de cada campaña es la misma: ¿cómo vienen el agua y el calor este año comparados con añadas anteriores? Los datos existen y son públicos (reserva de los embalses, lluvia y temperatura), pero están dispersos, en formatos poco amigables y sin control de calidad."),
  P("**Por qué este caso.** Me gusta mucho el vino y me siento cercana a ese mundo: estudié hostelería y turismo. Además, me parecía un buen caso de uso para salir de mi foco habitual, el ecommerce, y comprobar que el mismo método de trabajo con datos funciona en otro sector."),
  P("**Punto de partida.** El caso se construye sobre un pipeline propio de embalses en Databricks, desarrollado en agosto de 2026 como material docente. El diagnóstico inicial (sección 3) demostró que **parecía funcionar, pero producía datos no verificables**: cuatro de sus seis fuentes caían en silencio a ficheros de ejemplo, una inventaba lluvia de 0 mm cuando fallaba y las validaciones descartaban filas sin dejar rastro."),
  P("**Objetivo.** Convertirlo en un sistema de datos **real, controlado y operable**, centrado en las cuatro capas que pide la guía para un proyecto propio: normalización, calidad, gobierno y operación. El resultado de negocio es un indicador de campaña vitícola (lluvia, grados-día de Winkler y reserva del Ebro) contrastado con la calificación oficial de cada añada y servido en un dashboard."),
  P("**Alcance y límites.** Dos fuentes reales operadas a diario (AEMET y MITECO) y una de referencia mantenida a mano (DOCa). Quedan fuera las fuentes heredadas sin endpoint verificable y los modelos predictivos, sustituidos por un indicador descriptivo (decisión D-06). No hay datos personales: la propagación de consentimiento o supresión no aplica y se declara como límite."),
  table(["Resultado", "Evidencia"], [
    ["Pipeline medallion con datos reales: 125.127 lecturas de 84 embalses del Ebro (1988–2026) y 9.790 días de clima de Logroño (2000–2026)", "Fig. 1, 2"],
    ["Cuarentena con motivo y 14 controles automáticos (9 críticos bloquean la publicación)", "Fig. 3, 4"],
    ["Gobierno: clasificación, etiquetas, linaje y permisos de solo lectura para el dashboard", "Fig. 5–7"],
    ["Operación: Job diario desatendido, registro de ejecuciones y 6 incidencias reales resueltas", "Fig. 8, 9 y tabla 5.2"],
    ["Dashboard de negocio y de salud del pipeline", "Fig. 10, 11"],
    ["Uso de IA con reglas, controles y errores detectados", "Sección 7"],
  ], [6900, CW - 6900]),
);

// ---------------------------------------------------------------- 2
add(H1("2. Fuentes, arquitectura y modelado"),
  H2("2.1 Fuentes"),
  table(["Fuente", "Qué aporta", "Formato y frecuencia", "Papel"], [
    ["AEMET OpenData · estación 9170 Logroño Aeropuerto", "Lluvia y temperaturas diarias", "API REST con key; diaria (3–4 días de retraso)", "Núcleo"],
    ["MITECO · BD-Embalses (Boletín Hidrológico)", "Reserva semanal de cada embalse > 5 hm³ desde 1988; se filtra la cuenca del Ebro", "ZIP con base de datos Access (10,4 MB); semanal, marcada como «sin validar»", "Núcleo"],
    ["Consejo Regulador DOCa Rioja", "Calificación oficial de cada añada", "Tabla web; anual → CSV versionado con su URL de origen", "Referencia"],
  ], [2500, 2700, 2700, CW - 7900]),
  P(""),
  P("La elección se apoyó en pruebas, no en supuestos: primero se comprobó la conectividad desde Databricks, después la descarga real y por último la lectura del contenido (figura 1). El histórico de MITECO llega hasta el 20/10/2026, lo que confirma que se actualiza cada semana y que habrá al menos una carga real de datos nuevos durante el TFM."),
  ...fig("fuentes", "Primera lectura de datos reales (24/10/2026 18:30). MITECO: 723.842 filas de 1987 a 20/10/2026, con coma decimal («308,00»). AEMET 9170: lluvia y temperaturas diarias, también con coma decimal.", 13, 8),
  H2("2.2 Arquitectura"),
  ...fig("arquitectura", "Arquitectura. Cada capa es un esquema de Unity Catalog con tablas Delta registradas; el Job encadena los pasos y cada uno deja rastro en ops.", 16, 7),
  H2("2.3 Modelado"),
  table(["Tabla", "Grano", "Clave / contenido"], [
    ["silver.embalses_ebro", "embalse × semana", "embalse, fecha · volumen, capacidad, % capacidad"],
    ["silver.clima_logrono", "día", "estacion_id, fecha · lluvia (mm), tmax, tmin, tmed"],
    ["gold.reserva_ebro_semanal", "semana", "suma de volumen y capacidad de la cuenca · %"],
    ["gold.campana_vitivinicola", "campaña (1 abr–31 oct)", "lluvia, Winkler = Σ max(tmed − 10 ºC, 0), completitud, reserva media, calificación DOCa"],
    ["gold.kpis", "KPI", "valor, nota, ejecución que lo generó"],
  ], [2900, 2200, CW - 5100]),
  ...ia("Databricks Free Edition (serverless), Unity Catalog, Python/pandas, requests, access-parser; Claude (Opus 5.5) en claude.ai.",
    "propuso las fuentes candidatas (localizó el histórico BD-Embalses de MITECO), escribió las celdas de prueba de conectividad y lectura, y diagnosticó los resultados (por ejemplo, que el corte exacto a 8 MiB indicaba un límite de la plataforma).",
    "la autora eligió el caso del vino, ejecutó cada prueba en Databricks y decidió el alcance (D-03 a D-05) a la vista de las salidas reales."),
);

// ---------------------------------------------------------------- 3
add(H1("3. Método: del pipeline heredado al nuevo"),
  H2("3.1 Diagnóstico del punto de partida"),
  P("Antes de construir nada se revisó el código heredado (9 notebooks y 5 CSV de ejemplo) frente a los requisitos de la guía. El diagnóstico identificó **12 hallazgos**; los que más condicionaron el trabajo fueron:"),
  table(["#", "Hallazgo en el pipeline heredado", "Cómo se resuelve"], [
    ["H1", "4 de 6 fuentes apuntaban a URLs inexistentes y caían en silencio a CSV de ejemplo; bronze no distinguía dato real de ejemplo", "Sin fallbacks: si una fuente falla se registra y el Job se detiene. Origen (_source) en cada fila"],
    ["H2", "Si AEMET fallaba, se insertaba una lluvia sintética de 0,0 mm", "Control crítico «sin datos sintéticos»"],
    ["H4", "Las filas inválidas se descartaban con un print", "Estados aceptado / revisión / rechazado y tabla de cuarentena con motivo"],
    ["H5", "Sin tratamiento de coma decimal: «308,00» → nulo", "parse_decimal_es, con prueba unitaria. Confirmado con datos reales: con el código heredado se habrían perdido todos los volúmenes"],
    ["H6–H7", "Deduplicación arbitraria y lluvia duplicada en cada ejecución", "Una fila por clave, la de la ingesta más reciente; silver se reconstruye y es idempotente"],
    ["H9–H11", "Índice que mezclaba cuencas, KPI mal calculado y KPIs de relleno", "Todo Ebro / La Rioja; KPIs calculados desde datos y run_log"],
  ], [800, 4300, CW - 5100]),
  P(""),
  P("Al completar la referencia oficial de la DOCa apareció un hallazgo adicional: **6 de las 10 añadas del CSV de ejemplo heredado estaban mal calificadas**. Refuerza la conclusión del diagnóstico: los datos de ejemplo eran inventados y nada en el pipeline lo advertía."),
  H2("3.2 Construcción"),
  B("**Bronze** (01): ingesta incremental. AEMET pide solo los días nuevos con 10 de solape para recoger correcciones; MITECO solo se carga si la huella SHA-256 del fichero cambia. El fichero original se conserva en un volumen, una carpeta por fecha de carga."),
  B("**Silver** (02): normalización (coma decimal, «Ip» = precipitación inapreciable), deduplicación con criterio y reparto en silver o cuarentena."),
  B("**Calidad** (03) y **gold** (04): ver secciones 4 y 6."),
  B("La lógica vive en un módulo de funciones puras (transforms.py) con **11 pruebas unitarias** que se ejecutan en local antes de cada commit."),
  ...ia("Python, pandas, PySpark, Delta Lake, pytest, Git/GitHub (Git folder en Databricks); Claude con acceso de escritura al repositorio.",
    "realizó el diagnóstico (IA-001), escribió la primera versión completa del pipeline, las pruebas y la documentación (IA-002) y completó la referencia DOCa desde la web oficial (IA-003).",
    "revisión y aceptación del diagnóstico; ejecución paso a paso en la plataforma, que destapó una corrección necesaria (INC-03); decisión de aceptar la referencia DOCa sin contraste manual adicional, declarada como límite."),
);

// ---------------------------------------------------------------- 4
add(H1("4. Calidad y gobierno"),
  H2("4.1 Cuarentena: nada se descarta sin rastro"),
  P("Cada fila acaba en **silver** (aceptada) o en **quarantine** (en revisión o rechazada), siempre con su motivo. En la primera carga, el 0,34 % de las lecturas de embalses y el 0,12 % de los días de clima fueron a cuarentena."),
  table(["Fuente", "Aceptadas", "Rechazadas (motivo)", "En revisión (motivo)"], [
    ["Embalses del Ebro", "124.701", "228 (capacidad vacía o 0)", "198 (volumen > capacidad)"],
    ["Clima de Logroño", "9.778", "11 (sin temperatura media)", "1 (lluvia «Acum», acumulada de varios días)"],
  ], [2300, 1500, 2900, CW - 6700]),
  ...fig("cuarentena", "Silver de embalses (24/10/2026 19:07): estados y motivos registrados en ops.run_log.", 15, 4),
  H2("4.2 Controles repetibles"),
  P("Los 14 controles se ejecutan en cada carga y guardan su resultado en ops.quality_results. Los **críticos** detienen la publicación de gold; los **avisos** se muestran en el dashboard."),
  table(["Nivel", "Controles"], [
    ["Crítico (9)", "Unicidad de claves (2) · sin datos sintéticos (2) · % de capacidad entre 0 y 100 · silver no vacía (2) · **conciliación bronze → silver + quarantine (2): 0 claves perdidas**"],
    ["Aviso (5)", "Frescura de MITECO (≤ 14 días) y AEMET (≤ 10 días) · cuarentena ≤ 5 % (2) · variación semanal de la reserva ≤ 10 puntos"],
  ], [1500, CW - 1500]),
  ...fig("controles", "Primera ejecución de los controles críticos (24/10/2026 19:11): los 9 superados, con 0 claves perdidas entre capas.", 15, 6),
  H2("4.3 Gobierno"),
  B("**Clasificación y documentación:** las 14 tablas tienen comentario y etiquetas (clasificación pública, sin datos personales, capa, fuente y proyecto). Las columnas clave explican su cálculo (figura 5)."),
  B("**Linaje:** Unity Catalog lo registra automáticamente donde la transformación es SQL (figura 6). **Límite:** en los pasos que pasan por pandas solo registra quién escribe la tabla, no de dónde viene (D-17); se compensa con la trazabilidad por fila (_source, _ingest_ts, _run_id) y con ops.run_log."),
  B("**Exposición mínima:** el dashboard se ejecuta con su propia identidad y solo puede leer gold, ops y ref; nunca bronze ni quarantine (figura 7)."),
  B("**Secretos y datos personales:** la key de AEMET vive en un secret scope, nunca en el código. No hay datos personales; no se envió ninguno al asistente."),
  ...fig("tags", "Catalog Explorer: descripción, comentario de columna (definición de Winkler) y etiquetas de gold.campana_vitivinicola.", 15, 6.5),
  ...fig("linaje", "Linaje automático silver.embalses_ebro → gold.reserva_ebro_semanal en Unity Catalog.", 15, 6.5),
  ...fig("grants", "Permisos verificados con SHOW GRANTS (25/10/2026 00:01): la identidad de la app solo tiene USE SCHEMA y SELECT en gold y ops (y ref).", 10, 5.5),
  ...ia("Unity Catalog (tags, comentarios, linaje, GRANT), SQL, Catalog Explorer.",
    "escribió las reglas de calidad, los controles y el notebook de gobierno, y propuso la verificación con SHOW GRANTS que destapó INC-06.",
    "ejecución y revisión de cada control; concesión final de permisos desde Catalog Explorer; aceptación del límite de linaje."),
);

// ---------------------------------------------------------------- 5
add(H1("5. Operación"),
  H2("5.1 Cómo se ejecuta"),
  P("El Job **tfm_embalses_diario** encadena bronze → silver → calidad → gold cada día a las 07:37 (Europe/Madrid), en serverless y sin intervención. Cada tarea solo se ejecuta si la anterior termina bien, y cada paso escribe su estado en ops.run_log. Se desactivó el modo *performance optimized* para no agotar la cuota diaria de Free Edition."),
  ...fig("job", "Primera ejecución del Job (24/10/2026): 4 tareas en verde en 6 min 15 s. Las dos canceladas son lanzamientos duplicados detenidos a mano.", 15, 6.5),
  H2("5.2 Incidencias y resolución"),
  table(["#", "Incidencia", "Causa", "Resolución"], [
    ["INC-01", "AEMET sin datos para la estación 9170X", "Indicativo erróneo heredado", "Inventario oficial de AEMET: el correcto es 9170"],
    ["INC-02", "La descarga de MITECO se corta a 8.388.608 bytes", "Límite de 8 MiB por respuesta en Free Edition", "Descarga por tramos HTTP Range de 4 MiB"],
    ["INC-03", "Aviso de reinicio tras instalar access-parser", "%pip no recarga la sesión", "restartPython() tras la instalación"],
    ["INC-04", "GRANT: PRINCIPAL_DOES_NOT_EXIST", "Se usó el nombre visible de la app", "Usar un identificador"],
    ["INC-05", "La app no descarga el código", "Repositorio privado sin credencial", "Repositorio público, revisado antes: sin secretos (D-18)"],
    ["INC-06", "La app sin permiso USE CATALOG", "El GRANT por código usó otro identificador; no dio error, pero SHOW GRANTS estaba vacío", "Permisos desde Catalog Explorer, verificados con SHOW GRANTS"],
  ], [900, 2700, 2900, CW - 6500]),
  P(""),
  ...fig("inc_8mib", "INC-01 e INC-02 (24/10/2026 18:12): AEMET sin datos para 9170X y la descarga de MITECO cortada exactamente a 8 MiB.", 12, 6.5),
  H2("5.3 Historial de ejecuciones"),
  table(["Fecha", "Ejecución", "AEMET", "MITECO", "Calidad", "Resultado"], [
    ["24/10 18:58–19:15", "Manual, por pasos (carga histórica)", "9.790 días", "125.127 filas", "14/14", "OK"],
    ["24/10 19:26", "Job, lanzado a mano", "Días nuevos", "Sin cambios", "14/14", "OK (6 min 15 s)"],
    ["25/10 07:37", "Job programado (primera desatendida)", "OK (último dato 21/10)", "Sin cambios", "14/14, 0 avisos", "OK (7 min 23 s)"],
    ["26/10 y 27/10 07:37", "Job programado", "OK", "Sin cambios", "14/14, 0 avisos", "OK (6 min 5 s y 6 min 28 s)"],
    ["28/10 07:37", "Job programado · MITECO publica la semana del 27/10", "OK (último dato 24/10)", "Fichero nuevo: +76 lecturas", "14/14, 0 avisos", "OK (6 min 57 s)"],
  ], [1500, 2500, 1300, 1500, 1100, CW - 7900]),
  P(""),
  P("**La carga del 28/10 es la prueba de operación más completa.** MITECO publicó la semana del 27/10 y el Job la cargó sin intervención: la huella SHA-256 del fichero cambió (tras tres días de «sin cambios»), bronze recibió de nuevo el histórico del Ebro y silver pasó de 124.701 a 124.777 lecturas. La deduplicación dejó una sola lectura por embalse y fecha (unicidad 0), la conciliación siguió a 0 y la frescura de MITECO bajó de 5 días a 1 (E-31, E-32)."),
  ...ia("Databricks Jobs (serverless), Delta, ops.run_log.",
    "diseñó el registro de ejecuciones e incidencias y diagnosticó cada fallo a partir de las capturas (por ejemplo, la causa raíz de INC-06 al comparar identificadores).",
    "configuración del Job en la interfaz, cancelación de duplicados y validación de cada resolución con una nueva ejecución o un SHOW GRANTS."),
);

// ---------------------------------------------------------------- 6
add(H1("6. Resultados y dashboard"),
  H2("6.1 Para qué sirve el dashboard"),
  P("El dashboard responde a dos públicos y, por eso, tiene dos pestañas:"),
  B("**Campaña y reserva (negocio).** Para una bodega, un técnico de viñedo o la propia DOCa: en un vistazo, cómo está la reserva del Ebro frente al año anterior, cuánto ha llovido y cuánto calor ha acumulado la campaña, y dónde se sitúa respecto a todas las añadas desde 2000 con su calificación oficial. No predice la calificación: sitúa la campaña en curso frente a la historia para apoyar decisiones de riego, vendimia o comunicación."),
  B("**Salud del pipeline (operación).** Para quien mantiene el sistema: ejecuciones, resultado de los 14 controles en la última carga, su evolución y los ficheros de MITECO cargados con su huella. Es la evidencia viva de que los datos de la otra pestaña están controlados."),
  P("Se implementó en **Streamlit como Databricks App** (D-07): el código está en el repositorio, lee en vivo las tablas gold y ops a través del SQL warehouse y se ejecuta con una identidad de solo lectura."),
  ...fig("app_negocio", "Pestaña «Campaña y reserva» (25/10/2026 00:11): KPIs y cada campaña situada por grados-día y lluvia, coloreada por su calificación DOCa.", 15, 11),
  ...fig("app_salud", "Pestaña «Salud del pipeline» (25/10/2026 00:09): ejecuciones registradas y los 14 controles de la última carga, con 0 fallos.", 14, 11),
  H2("6.2 Resultados medidos"),
  B("**Reserva del Ebro: 44,9 %** en la semana del 20/10/2026, **8 puntos por debajo** de la misma semana de 2025."),
  B("**Campaña 2026 en Logroño:** 202 mm de lluvia y **2.377 grados-día**, el valor más alto de la serie desde 2000 (región V, «cálida»)."),
  B("**Lectura descriptiva de la serie:** más lluvia no implica mejor calificación. 2024 fue la campaña más lluviosa (480 mm) y se calificó «Buena»; 2016 y 2022, de las más secas, «Muy buena»."),
  H2("6.3 Hipótesis, no resultados"),
  B("Los grados-día de Logroño (≈ 1.950–2.380 en 2022–2026) parecen altos frente a la clasificación clásica de Rioja. **Contraste:** el informe de índices bioclimáticos de AEMET da a Logroño 2.748 grados-día en 2021 (1 de abril–30 de septiembre, base 10 ºC, calculados con máximas y mínimas), así que el orden de magnitud es plausible. La diferencia con la referencia clásica se explica por el periodo, el método de cálculo y el calentamiento reciente; una sola estación de valle sigue sin representar toda la DOCa."),
  B("Con 26 añadas calificadas no es posible establecer una relación estadística entre clima y calificación; por eso el indicador es descriptivo."),
  ...ia("Streamlit, Altair, databricks-sql-connector, Databricks Apps, SQL warehouse serverless.",
    "escribió la app y su configuración, y revisó la app desplegada en el navegador integrado (solo lectura).",
    "creación y despliegue de la app, concesión de permisos y comprobación de que los KPIs coinciden con gold.kpis (E-15)."),
);

// ---------------------------------------------------------------- 7
add(H1("7. Cómo se ha trabajado con la IA"),
  P("Los recuadros de cada sección dicen qué hizo la IA en ese paso. Esta sección explica **con qué entorno, con qué reglas y con qué controles** se trabajó; el detalle está en docs/uso_ia.md y en el registro de uso de IA (IA-001 a IA-008)."),
  H2("Entorno, skills e instrucciones"),
  table(["Pieza", "Qué aporta al trabajo"], [
    ["**Claude Opus 5.5** (Anthropic), en la app de Claude en modo agente", "Ejecuta tareas de varios pasos en un espacio de trabajo en la nube: escribe y prueba código, genera documentos y hace commits"],
    ["**Proyecto de Claude** con la guía, el diagnóstico, las decisiones y las evidencias", "Contexto persistente: cada sesión parte de los requisitos y de lo ya decidido"],
    ["**Conectores:** GitHub, Google Drive, búsqueda web y navegador integrado", "Repositorio, documentos de trabajo, verificación de fuentes públicas y revisión de la app (solo lectura)"],
    ["**Skills de la plataforma:** docx y navegador integrado", "Instrucciones empaquetadas para generar esta memoria en Word y para usar el navegador con sus límites"],
    ["**Skill propia: pipeline-datos-controlado**", "El método de este trabajo empaquetado para reutilizarlo: principios, fases, controles, notas de Databricks Free Edition y checklist (carpeta skills/ del repositorio)"],
    ["**CLAUDE.md** del repositorio", "Las reglas que la IA cumple siempre: sin datos sintéticos ni respaldos silenciosos, trazabilidad por fila, nada se descarta sin rastro, pruebas antes de cada commit, sin secretos y registro de cada cambio con IA"],
  ], [3900, CW - 3900]),
  P(""),
  P("Las tres primeras reglas de CLAUDE.md traducen los hallazgos del diagnóstico: son justo los errores que el pipeline heredado cometía y que una IA podría reintroducir sin darse cuenta. Los encargos siguieron las cinco piezas de la guía (§8): una tarea concreta cada vez, el contexto del proyecto, los límites de CLAUDE.md, un formato de salida definido y una verificación asociada. Los prompts clave se guardan literales en docs/uso_ia.md."),
  H2("Límites y verificación"),
  B("**La IA no ejecuta en Databricks ni maneja credenciales:** la autora ejecuta cada celda, crea el Job, la app y los permisos, y aporta la captura. Se dejó de automatizar la consola desde el navegador al aparecer el aviso de control automatizado."),
  B("**Cada salida tiene su comprobación:** pruebas unitarias, ejecución real con captura fechada, los 14 controles de calidad, contraste con fuente oficial (DOCa, AEMET) y, para los comentarios de los notebooks, comparación del árbol sintáctico para asegurar que el código no cambió."),
  H2("Dónde se equivocó la IA"),
  table(["Caso", "Qué pasó", "Cómo se detectó"], [
    ["Permisos de la app (INC-06)", "El GRANT propuesto se ejecutó sin error, pero sin efecto", "SHOW GRANTS vacío; corregido desde Catalog Explorer"],
    ["Límite de 8 MiB (INC-02) y reinicio tras %pip (INC-03)", "Límites de la plataforma no anticipados", "Errores en la primera ejecución real"],
    ["Repositorio privado (INC-05)", "Se asumió que la app podría leerlo", "Error «no credential» al desplegar"],
    ["Valores de Winkler", "Más altos que las referencias clásicas de Rioja", "Contraste con un informe de AEMET antes de aceptarlos"],
  ], [2900, 3300, CW - 6200]),
  P(""),
  ...ia("Claude Opus 5.5 en la app de Claude; proyecto de Claude; conectores de GitHub y Google Drive; búsqueda web; navegador integrado; skills docx y navegador.",
    "planificar las fases, escribir código y documentación, verificar fuentes públicas y proponer soluciones a las incidencias.",
    "elegir el caso, el alcance y las fuentes; tomar las decisiones D-01 a D-18; ejecutar en la plataforma; detectar las incidencias y aceptar o rechazar cada salida con su evidencia."),
);

// ---------------------------------------------------------------- 8
add(H1("8. Justificación cuantitativa: horas y costes"),
  P("**Tarea comparada:** llevar un pipeline heredado de una fuente pública a producción controlada (diagnóstico, fuentes reales, normalización, calidad, gobierno, operación, dashboard y documentación). **Criterio de resultado correcto:** los 14 controles superados, el Job operando y el dashboard con datos reales."),
  table(["Bloque", "Sin IA (estimación)", "Con IA: ejecución + revisión humana"], [
    ["Diagnóstico del código heredado", "2,5 h", "0,3 h"],
    ["Búsqueda y pruebas de fuentes reales", "3 h", "0,8 h"],
    ["Pipeline, pruebas y normalización", "14 h", "1,5 h"],
    ["Calidad y controles", "4 h", "0,5 h"],
    ["Gobierno y permisos", "2 h", "1 h"],
    ["Dashboard y despliegue", "6 h", "1,5 h"],
    ["Registros, evidencias y documentación", "4,5 h", "1,5 h"],
    ["Memoria, comentarios de notebooks, documentación del uso de IA y skill", "10 h", "1,2 h"],
    ["Seguimiento de la operación (comprobar ejecuciones y registrar evidencias)", "0,7 h", "0,7 h"],
    ["**Total**", "**46,7 h**", "**9,0 h** (24/10 17:07 → 25/10 01:10, más 25/10 08:03–08:20 y 09:32–10:15)"],
  ], [4300, 2300, CW - 6600]),
  P(""),
  P("**Origen de las cifras.** Las horas con IA salen de las marcas de tiempo de las sesiones de trabajo; su reparto por bloque es aproximado e incluye la revisión humana (ejecutar, comprobar, decidir). El seguimiento de la operación cuesta lo mismo en los dos modos, porque lo hace la autora. Las sesiones de cierre (27–29/10) se sumarán al total antes de la entrega. La columna sin IA es una **estimación** de la autora para una profesional con experiencia en el stack: **no hay línea base observada**. Para confirmarla habría que repetir una tarea equivalente sin asistente."),
  table(["Concepto", "Valor", "Tipo"], [
    ["Horas ahorradas por ejecución (46,7 − 9,0)", "37,7 h", "Estimación"],
    ["Tarifa horaria", "45 €/h", "Supuesto declarado"],
    ["Coste incremental de IA y herramientas por ejecución", "≈ 22 € (un mes de Claude Pro: 20 USD + IVA; Databricks Free Edition y GitHub: 0 €)", "Medido: plan usado; importe según factura"],
    ["Ejecuciones al año (nuevas fuentes o casos equivalentes)", "4", "Supuesto"],
    ["**Beneficio neto anual estimado**", "**(37,7 × 45 − 22) × 4 ≈ 6.698 €**", "Estimación"],
  ], [4000, 3400, CW - 7400]),
  P(""),
  P("**Límites.** El ahorro de tiempo es más sólido que el monetario, que depende de la tarifa y de la frecuencia supuestas. El ahorro no es gratuito: hubo 6 incidencias que la IA no anticipó y que exigieron ejecución y criterio humano, y su propia propuesta de permisos por código falló en silencio (INC-06). En plataformas de pago habría que sumar el coste de cómputo, aquí nulo por usar Free Edition."),
);

// ---------------------------------------------------------------- 9
add(H1("9. Conclusiones y límites"),
  H2("Qué queda demostrado"),
  B("Que un pipeline que «funcionaba» puede estar produciendo datos no verificables, y que diagnosticarlo con evidencia (hallazgos confirmados con datos reales) es el primer paso de cualquier proyecto de datos."),
  B("Un flujo de datos reales con origen trazable por fila, cuarentena con motivo, 14 controles repetibles que bloquean la publicación, gobierno con exposición mínima y operación diaria registrada."),
  B("Un uso de IA trazable y con reglas: un CLAUDE.md que fija lo que la IA no puede hacer, 8 entradas en el registro de IA con su verificación y la decisión humana explícita, y los casos en que la IA se equivocó, detectados y corregidos (sección 7)."),
  H2("Qué no queda demostrado"),
  B("La línea base manual es estimada, no medida."),
  B("La relación entre clima y calificación DOCa: el indicador es descriptivo."),
  B("El linaje completo entre tablas en los pasos con pandas (D-17)."),
  B("Una sola estación meteorológica representa la DOCa, y la añada 2000 procede de una fuente secundaria."),
  H2("Riesgos y siguientes pasos"),
  B("MITECO publica sus datos «sin validar»: pueden revisarse hacia atrás. El pipeline ya conserva cada versión del fichero y se queda con la última; el siguiente paso sería medir cuántos valores cambian entre versiones."),
  B("Reescribir en Spark los pasos con pandas para recuperar el linaje completo, añadir más estaciones (Haro, Rioja Alta) y alertas por correo cuando falle un control crítico."),
  B("Con más tiempo, añadiría más fuentes de datos y capas de predicción, por ejemplo para estimar la demanda de vino o la capacidad de las bodegas. Los modelos se descartaron en este trabajo (D-06) porque no había datos suficientes para entrenarlos con garantías; más fuentes son la condición para recuperarlos."),
  H2("Lo que me llevo"),
  P("El pipeline de agosto lo monté yo como material docente y, aunque no era del todo correcto, me dio la oportunidad de cacharrear con Databricks. No soy una profesional senior de data engineering y es normal tener errores. Para mí, detectar el fallo ha sido lo más valioso: me ha permitido mejorarlo y descubrir piezas que no tenía en el radar, como la capa de gobierno o desplegar el dashboard en Streamlit directamente en Databricks."),
  P("Lo más difícil de trabajar con IA ha sido no dar por sentadas sus respuestas. Cuesta no creerse directamente que todo es verídico, porque no se nos enseña a cuestionarla. Por eso este trabajo registra cada verificación y también los casos en que la IA se equivocó (sección 7)."),
  P("En el día a día, usada como copiloto, me permite aprender cosas nuevas sin tener experiencia previa en ellas y profundizar, aunque no sea a nivel profesional. Creo que es una herramienta muy potente, siempre que se trabaje con reglas y comprobando lo que propone."),
);

// ---------------------------------------------------------------- Anexo
add(H1("Anexo · Documentación y reproducibilidad"),
  table(["Elemento", "Dónde"], [
    ["Código, pruebas y notebooks", "github.com/PatriciaL/tfm-embalses (pipeline/, tests/, app/)"],
    ["Reproducir desde cero", "README.md del repositorio (5 pasos; las pruebas se ejecutan con pytest)"],
    ["Diagnóstico del pipeline heredado", "docs/diagnostico.md"],
    ["Registro de decisiones (D-01 a D-18)", "docs/decisiones.md"],
    ["Índice de evidencias e incidencias (E-01 a E-32, INC-01 a INC-06)", "docs/evidencias.md"],
    ["Registro de uso de IA (IA-001 a IA-008)", "docs/ai_log.md"],
    ["Entorno de IA, skills, reglas y prompts clave", "docs/uso_ia.md y CLAUDE.md"],
    ["Skill reutilizable del método", "skills/pipeline-datos-controlado/SKILL.md"],
    ["Definición del Job", "jobs/job_tfm_embalses.md"],
  ], [4300, CW - 4300]),
);

const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 28, bold: true, font: FONT, color: "6B1D3A" }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 22, bold: true, font: FONT }, paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "vinetas", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 240 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [run("TFM · Agua y viñedo en La Rioja · ", { size: 16, color: "888888" }), new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: "888888" })] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync("TFM_Agua_y_vinedo_La_Rioja.docx", b); console.log("ok", nFig, "figuras"); });
