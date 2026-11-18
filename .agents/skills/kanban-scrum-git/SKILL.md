---
name: kanban-scrum-git
description: Úsala para analizar el historial Git de un desarrollador (sus ramas, merges propios y commits), inspeccionar sus cambios reales en el código del proyecto y el estado de un GitHub Project v2, redactar tareas en formato Scrum profesional (MD) para aprobación y cargarlas automáticamente en GitHub Issues y Projects vía scripts Python + gh CLI.
---

# Objetivo
Transformar el trabajo real registrado en Git y en el código fuente de un integrante del equipo en un backlog Scrum profesional (Issues, Sub-issues, Milestones y campos de GitHub Projects v2), respetando estrictamente la autoría real y evitando duplicar tarjetas ya existentes.

# Estructura de la Skill (`.agents/skills/kanban-scrum-git/`)
- `scripts/leer_git.py`: Inspecciona el repositorio objetivo en solo lectura (alias, ramas, PRs propios vs. PRs ajenos mergeados, commits directos, fechas reales y `--numstat`).
- `scripts/leer_github.py`: Consulta en solo lectura permisos del usuario, Milestones, Labels, Issue Types, esquema y opciones exactas de campos del Project v2, e Issues ya existentes del autor. Soporta `--all-issues` para snapshots completos del repositorio.
- `scripts/aplicar_kanban.py`: Valida el JSON generado a partir del MD aprobado, soporta `--dry-run --github-snapshot` y ejecuta la creación ordenada de nuevas issues en GitHub y Project v2.
- `scripts/actualizar_kanban.py`: Actualiza, normaliza metadatos/cuerpos o archiva issues existentes sin recrearlas, con soporte de `--with-comments`, `--dry-run --github-snapshot` y remoción limpia de Project v2 (`remove_from_project: true`).
- `references/guia_estilo_y_analisis.md`: Protocolo de inspección profunda de código/diffs en el repositorio objetivo y ejemplos reales de redacción Scrum (`Feature`, `Task`, `Bug` y `Sub-issues`).

> [!IMPORTANT]
> **Estándar de Redacción Scrum Obligatorio:** Antes de redactar cualquier tarjeta o propuesta, consultar y seguir estrictamente la skill `.agents/skills/scrum-issue-writer/SKILL.md`.
> **Entorno de ejecución:** Correr todos los scripts con `.venv/bin/python` (librería estándar, sin dependencias externas) + `gh` CLI autenticado (`gh auth login -s project,read:org`). Nunca escribir ni modificar archivos dentro del repositorio analizado.

# Flujo Obligatorio Paso a Paso

## Fase 1 — Recolección de Contexto e Inspección Profunda del Código (Solo Lectura)
1. Ejecutar `leer_git.py` apuntando al repositorio objetivo y al usuario/autor solicitado:
   - Verificar alias agrupados (`author` / `email`) y usar `--aliases` si hubiera nombres distintos del mismo desarrollador.
   - **Separar estrictamente** PRs y commits propios de PRs ajenos donde el usuario solo hizo *Merge pull request* o resolvió conflictos/sync.
2. **Inspeccionar directamente el código y los diffs en la carpeta del proyecto objetivo** (siguiendo `references/guia_estilo_y_analisis.md`):
   - Leer la documentación de negocio y arquitectura del repo (`README.md`, `docs/`, contratos como `swagger.yaml`, esquemas SQL o backlogs de hitos).
   - Para **cada** PR propio o commit directo relevante, revisar el diff (`git -C <repo> show <hash>`) y/o leer los archivos modificados dentro de `<repo>/` (rutas, servicios, repositorios, templates, CSS/JS, SQL) para entender **qué se cambió exactamente, qué reglas de negocio aplica, qué causa raíz resolvió (en fixes) y si mezcla entregables de distintas épicas**.
   - Prohibido redactar tickets adivinando solo a partir de títulos cortos o ambiguos de commits.
3. Ejecutar `leer_github.py` contra el repo y Project v2 destino para obtener:
   - Nombres exactos de `Milestones`, `Labels` (incluyendo capas técnicas: `backend`, `frontend`, `database`, `infraestructura`), `Issue Types` habilitados (`Feature`, `Task`, `Bug`).
   - Opciones exactas de cada campo del Project (`Status`, `Priority`, `Size`, `Estimate`, `Start date`, `Target date`). *Ejemplo: `Priority` puede estar en español (`Alta`, `Media`, `Baja`).*
   - Lista de Issues ya creados/asignados al usuario para no duplicarlos.

## Fase 2 — Redacción Scrum en Markdown (`outputs/plan_<usuario>.md`)
Antes de redactar, leer `scrum-issue-writer/SKILL.md` y `references/guia_estilo_y_analisis.md` aplicando estas reglas estrictas:
1. **Formato de títulos:** `[HITO N] [CAPA] Verbo en infinitivo + objetivo claro` (ej: `[HITO 2] [BACKEND] Implementar módulo transaccional de compras`).
2. **Redacción Scrum en requerimiento (nunca en pasado):**
   - **Todas las tarjetas (incluyendo Sub-issues):** Deben llevar historia de usuario formal (`Como <rol específico del dominio o ingeniería>, necesito <capacidad en presente> para <beneficio verificable>.`) + sección obligatoria `### Criterios de aceptación` con viñetas comunes (`- `).
   - **Prohibido:** No usar roles genéricos como *"Como usuario..."*, no omitir criterios de aceptación y no usar párrafos aislados de `### Objetivo` sin rol.
3. **Sin checkboxes `[ ]`:** Usar viñetas comunes (`- `) en los criterios de aceptación.
4. **Metadatos en tabla estandarizada:** Incluir tabla con `Type`, `Assignee`, `Label` (combinando tipo + capa técnica), `Milestone`, `Status`, `Priority`, `Size`, `Estimate`, `Start date`, `Target date`, `Development` (PR/commit de referencia) y `Cierre`.
5. **Fechas y estimación:**
   - `Start date`: fecha real del primer commit/inicio de la rama en Git (`YYYY-MM-DD`).
   - `Target date`: fecha oficial de entrega del **Hito** al que pertenece la tarea (`Hito 1: 2026-10-26`, `Hito 2: 2026-11-02`, `Hito 3: 2026-11-11`, `Hito 4: 2026-11-18`).
   - Escala `Size` ↔ `Estimate`: `XS = 1`, `S = 2`, `M = 3`, `L = 5`, `XL = 8`.
6. **Comentarios de trazabilidad Git (Regla de autolinks):**
   - **NUNCA usar comillas invertidas (backticks)** alrededor de hashes de commits ni PRs.
   - **NUNCA agregar fechas entre paréntesis al lado del commit** (rompe el autolink en GitHub).
   - Formato correcto: `Resuelto en commit 2a520b3 — Descripción.` o `Resuelto en PR #125 — Descripción.`
7. **Pausa obligatoria:** Presentar el `.md` al usuario y **detenerse** hasta que apruebe o pida ajustes.

## Fase 3 — Generación de JSON y Carga Controlada (`outputs/plan_<usuario>.json`)
Solo después de aprobación explícita del usuario:
1. Generar `outputs/plan_<usuario>.json` con el esquema validado contra los campos reales obtenidos por `leer_github.py`.
2. Ejecutar dry-run offline obligatorio con `--dry-run --github-snapshot outputs/github_all_issues.json`.
3. Según la operación:
   - **Nuevas Issues:** Ejecutar `aplicar_kanban.py` respetando el orden transaccional (Milestones → Issues/Sub-issues → Enlace de Sub-issues → Agregar a Project → Setear campos Priority/Size/Dates → Comentario de trazabilidad → Setear Status=Done en Sub-issues y luego en Padre).
   - **Actualización / Normalización / Limpieza:** Ejecutar `actualizar_kanban.py` pasando las actualizaciones deseadas (`body`, `title`, `state: closed`, `state_reason: not_planned`, `remove_from_project: true`).
4. Verificar el estado final consultando la API y entregar al usuario un reporte con links creados o actualizados.
