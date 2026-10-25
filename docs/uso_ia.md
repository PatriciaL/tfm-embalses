# Cómo se ha trabajado con la IA · TFM Embalses

Complementa el registro de uso de IA (`ai_log.md`, IA-001 a IA-008). El registro dice **qué** se hizo con IA en cada paso; este documento dice **con qué entorno, con qué reglas y con qué controles** se trabajó.

---

## 1. Entorno

| Pieza | Qué es | Para qué se usó |
|---|---|---|
| **Modelo** | Claude Opus 5.5 (Anthropic) | Todo el trabajo asistido |
| **Superficie** | App de Claude, en modo agente: la IA ejecuta tareas de varios pasos en un espacio de trabajo en la nube (terminal Linux, Python, Node) | Escribir y probar código, generar documentos, hacer commits |
| **Proyecto de Claude** "JAKALA IA" | Carpeta persistente con documentos de contexto (`master-ia/`: guía del TFM, diagnóstico, decisiones, evidencias, registro de IA) | Que cada sesión parta de los requisitos y de las decisiones ya tomadas, sin volver a explicarlas |
| **Conector GitHub** | Acceso de escritura al repositorio `PatriciaL/tfm-embalses` | Commits y push del código y la documentación |
| **Conector Google Drive** | Lectura y escritura en "JAKALA IA MASTER" | Leer la guía del TFM y publicar documentos de trabajo |
| **Búsqueda web** | Búsqueda y lectura de páginas públicas | Verificar fuentes (AEMET, MITECO), obtener las calificaciones oficiales DOCa y contrastar valores de Winkler |
| **Navegador integrado** | Panel de navegador en el ordenador de la autora | Revisar la app desplegada (solo lectura) |

## 2. Skills e instrucciones

Una *skill* es un paquete de instrucciones que la IA carga para hacer bien un tipo de tarea concreto. Se distinguen las skills de la plataforma de las instrucciones propias del proyecto.

| Tipo | Elemento | Qué aporta |
|---|---|---|
| Skill de la plataforma | **docx** (documentos Word) | Generar la memoria con estilos, tablas, figuras numeradas y pies de página correctos |
| Skill de la plataforma | **Navegador integrado** | Uso del panel de navegador, sus permisos y límites |
| Skill propia | **`pipeline-datos-controlado`** (`skills/`) | El método de este TFM convertido en skill reutilizable: principios, fases, controles, notas de Databricks Free Edition y checklist. Ver §8 |
| Instrucciones del proyecto | **`CLAUDE.md`** del repositorio | Las reglas que la IA debe cumplir siempre en este repo (ver abajo) |
| Contexto del proyecto | **`tfm-requisitos.md`** | La guía del TFM convertida a Markdown: la IA comprueba cada entregable contra ella |
| Contexto del proyecto | **`decisiones.md`, `evidencias.md`, `ai_log.md`** | Memoria de trabajo: qué se decidió, qué se probó y qué falta |

**Reglas de `CLAUDE.md`** (son la "política" del proyecto para la IA):

1. Nunca introducir datos de ejemplo, sintéticos ni *fallbacks* silenciosos: si una fuente falla, se registra y se detiene.
2. Toda fila de bronze lleva `_source`, `_ingest_ts` y `_run_id`.
3. Ninguna fila se descarta sin rastro: va a silver o a quarantine con motivo.
4. La lógica de transformación va en `transforms.py` con su prueba; `pytest` antes de cada commit.
5. Nada de secretos en el repositorio (la API key está en el secret scope).
6. Cada cambio relevante hecho con IA se registra en `ai_log.md`.

Las reglas 1 a 3 responden directamente a los hallazgos del diagnóstico del pipeline heredado: son errores que una IA (o una persona) podría reintroducir sin darse cuenta.

## 3. Prompts clave

La guía (§8) pide guardar los prompts importantes. Se recogen literales, con la entrada del registro a la que dieron lugar.

| Prompt de la autora (literal) | Qué desencadenó | Registro |
|---|---|---|
| "te leas el documento y me digas como vamos a organizar el workspace para luego pasar al faseado" | Lectura de la guía y propuesta de organización y fases | — |
| "tenemos que revisar el trabajo hecho ahora porque no se que ha salido de aqui […] quiero que ahora seas un planificador y hagamos las fases del TFM antes de empezar a trabajar" | Diagnóstico del pipeline heredado antes de escribir código | IA-001 |
| "podemos hacer una alternativa? me gustaria que fuera relacionado con vino" | Sustituir los modelos por el indicador de campaña vitícola (D-06) | — |
| "busca la salida del consejo regulador y listo la añades donde toque" | Calificaciones oficiales DOCa desde la web del Consejo Regulador | IA-003 |
| "hay que explicar en la memoria para que sirve el dashboard e incluir stack y rol de la IA en cada una" | Recuadro "Stack · Rol de la IA · Decisión humana" en cada sección | IA-005 |
| "se sincero […] crees que el trabajo tiene calidad?" | Revisión crítica: riesgos de la defensa, valores de Winkler a contrastar | — |
| "necesito que comentes los notebooks explicando que hace cada celda tambien de forma facil" | Comentarios didácticos sin tocar el código | IA-006 |

Patrón seguido en los encargos, alineado con las cinco piezas de la guía (§8): **tarea concreta** (una fase cada vez), **contexto mínimo** (los documentos del proyecto), **límites** (las reglas de `CLAUDE.md`), **formato de salida** (notebook, documento o tabla de registro) y **verificación** (cada entrega llega con su prueba o su evidencia).

## 4. Límites puestos a la IA

| Límite | Por qué |
|---|---|
| La IA **no ejecuta nada en Databricks**: la autora ejecuta cada celda y el Job, y aporta la captura | La ejecución real y su evidencia quedan bajo control humano |
| La IA **no introduce credenciales** ni accede a la API key | Los secretos solo existen en el secret scope |
| Se dejó de automatizar la consola de Databricks desde el navegador al aparecer el aviso de control automatizado | No operar una plataforma de forma automatizada sin permiso explícito |
| Navegador solo de lectura sobre la app | Revisar sin modificar |
| Decisiones de alcance, fuentes y diseño: siempre de la autora (D-01 a D-18) | La IA propone; la autora decide |

## 5. Cómo se verificó lo que hizo la IA

| Técnica | Dónde se aplicó |
|---|---|
| Pruebas unitarias (`pytest`, 11 pruebas) | Lógica de transformación: coma decimal, `Ip`, esquema, deduplicación, Winkler |
| Ejecución real en la plataforma con captura fechada | Cada notebook y cada ejecución del Job (E-06 a E-26) |
| 14 controles de calidad automáticos | Cada ejecución: unicidad, origen real, rango, conciliación bronze → silver/quarantine |
| Comprobación independiente del resultado | `SHOW GRANTS` tras el GRANT de permisos (INC-06) |
| Contraste con fuente oficial | Calificaciones DOCa (web del Consejo Regulador), Winkler (informe de índices bioclimáticos de AEMET) |
| Comparación del árbol sintáctico (AST) | Comentarios de los notebooks: el código ejecutable no cambió |
| Revisión visual del documento renderizado | Cada versión de la memoria |

## 6. Dónde se equivocó o no llegó la IA

Es la parte más útil para valorar el uso de la IA: muestra que las salidas no se aceptaron sin comprobar.

| Caso | Qué pasó | Cómo se detectó y resolvió |
|---|---|---|
| INC-06 · Permisos de la app | El GRANT propuesto por código se ejecutó **sin error pero sin efecto**: el identificador del *service principal* no era el correcto | `SHOW GRANTS` vacío; la autora concedió el permiso desde Catalog Explorer con el App ID correcto |
| INC-03 · Librería sin reinicio | El notebook no reiniciaba Python tras `%pip` | Aviso en la primera ejecución real; se añadió `restartPython()` |
| INC-02 · Límite de 8 MiB | No se anticipó el corte de respuestas de Free Edition | Error en la descarga de MITECO; descarga por tramos `Range` |
| INC-05 · Despliegue de la app | Se asumió que la app podría leer un repositorio privado | Error "no credential"; decisión de hacer público el repo tras revisar que no tiene secretos (D-18) |
| Valores de Winkler | Salían más altos que las referencias clásicas de Rioja | Se contrastó con AEMET en lugar de aceptarlos o "corregirlos" sin base |
| Linaje (D-17) | Los pasos con pandas no aparecen en el linaje de Unity Catalog | Detectado al revisar el linaje; declarado como límite |

## 7. Reparto de papeles

| La IA | La autora |
|---|---|
| Diagnóstico del código heredado | Elegir el caso, el alcance y las fuentes |
| Código del pipeline, pruebas, app y gobierno | Ejecutar en Databricks, crear el Job, la app y los permisos |
| Búsqueda y lectura de fuentes públicas | Validar los resultados y decidir qué se acepta |
| Borradores de documentación y memoria | Revisar, corregir y aportar su voz |
| Proponer soluciones a las incidencias | Detectar las incidencias en la plataforma y aplicar la solución |

## 8. Skill propia: `pipeline-datos-controlado`

El método seguido en este TFM se ha empaquetado como una skill reutilizable (`skills/pipeline-datos-controlado/SKILL.md`), para aplicarlo en otros proyectos sin volver a explicarlo a la IA.

| Contenido | Origen en el TFM |
|---|---|
| 6 principios no negociables | Reglas de `CLAUDE.md` y hallazgos del diagnóstico |
| 9 fases (diagnóstico → documentación) | Fases F0–F8 del plan del TFM |
| Catálogo de controles críticos y avisos | Notebook `03_quality_checks` |
| Cómo trabajar con IA en el flujo | Guía del TFM (§8) y este documento |
| Notas de Databricks Free Edition | Incidencias INC-02, INC-03, INC-05, INC-06 y decisión D-17 |
| Checklist de cierre | Guía del TFM (§10) |

Es el principal resultado reutilizable del trabajo con IA: la experiencia del proyecto queda como instrucción que cualquier sesión futura puede cargar.
