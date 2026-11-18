---
name: scrum-issue-writer
description: Guía y estándar obligatorio para redactar Issues y Sub-issues en formato Scrum profesional para el proyecto Cine LMMTFSDTTA (GitHub Project v2 #4). Define la convención de títulos por Hito y Capa técnica, roles de dominio específicos, redacción de historias de usuario con criterios de aceptación sin checkboxes, tablas de metadatos (Story Points, Fechas, Milestones, Labels) y reglas de autolink de Git en comentarios.
---

# Scrum Issue Writer — Cine LMMTFSDTTA

Esta skill establece las **reglas de redacción Scrum estrictas y obligatorias** para todo el backlog del repositorio `fcamporaa/IDS_ProyectoFinal_equipo10` y su tablero en **GitHub Projects v2 (`#4 - Cine LMMTFSDTTA`)**.

El objetivo es que cualquier Issue o Sub-issue nueva o editada mantenga una calidad homogénea, profesional, trazable y lista para evaluación académica y de ingeniería, idéntica al estándar oficial del equipo.

---

## 1. Convención Estándar de Títulos

Todo título de Issue o Sub-issue debe respetar estrictamente esta estructura:

```text
[HITO N] [CAPA] Verbo en infinitivo + objetivo claro y conciso
```

### Capas Técnicas Válidas (`[CAPA]`):
* `[BACKEND]`: Rutas Flask, controladores, servicios, repositorios SQL, validadores de negocio, lógica transaccional.
* `[FRONTEND]`: Vistas SSR (Flask + Jinja2), componentes CSS, scripts JavaScript cliente (ES6), modales, interactividad de butacas/checkout.
* `[DB]`: Scripts DDL (`init_db.sql`), migraciones, índices, procedimientos, modelos de datos, pool de conexiones SSL (TiDB/MySQL).
* `[INFRA]`: Dockerfiles, `docker-compose.yml`, configuración WSGI Gunicorn, variables de entorno, despliegue en la nube.
* `[DOCS]`: Constitución técnica, especificación OpenAPI (`docs/swagger.yaml`), backlog maestro de sprint, diagramas de arquitectura.
* `[TEST]`: Colecciones Postman, tests unitarios (`pytest`), scripts de prueba de carga, auditoría de concurrencia.

### Ejemplos Correctos:
* `[HITO 2] [BACKEND] Implementar módulo transaccional de compras, detalle y cancelación`
* `[HITO 3] [FRONTEND] Conectar selección dinámica de adicionales de Candy Bar en el flujo de compra`
* `[HITO 1] [DB] Diseñar e implementar el esquema inicial de base de datos relacional`
* `[HITO 3] [INFRA] Configurar servidor de aplicaciones WSGI Gunicorn para despliegue productivo`
* `[HITO 2] [DOCS] Redactar constitución técnica, flujo de desarrollo y adjuntar documentación oficial`

---

## 2. Redacción Scrum del Cuerpo (`body`)

Toda tarjeta (tanto **Issues Padre / Features / Tasks** como **Sub-issues**) DEBE contener obligatoriamente dos secciones principales: `### Descripción` y `### Criterios de aceptación`.

```markdown
### Descripción
Como <rol específico del dominio o de ingeniería>, necesito <capacidad o requerimiento en tiempo presente> para <beneficio de negocio o valor técnico verificable>.

### Criterios de aceptación
- El sistema / endpoint / vista debe...
- La validación debe rechazar... con código HTTP XXX ante...
- La interfaz debe renderizar...
```

### Prohibiciones Terminantes:
1. **PROHIBIDO roles genéricos:** Nunca escribir *"Como usuario, quiero..."* o *"Como usuario del sistema, necesito..."*.
2. **PROHIBIDO redactar sin historia:** Nunca poner solamente `### Objetivo\nConstruir la ruta...` sin el rol Scrum y los criterios.
3. **PROHIBIDO checkboxes `[ ]`:** Siempre usar viñetas comunes con guion (`- `).
4. **PROHIBIDO redactar en pasado:** Describir siempre en presente de requerimiento (*"El sistema debe..."*, nunca *"Se implementó..."*).
5. **PROHIBIDO pegar mensajes crudos de commits:** La descripción explica la funcionalidad de negocio y técnica, no la historia interna de Git.

---

## 3. Catálogo de Roles Autorizados por Capa / Módulo

Para garantizar precisión semántica, usar los roles específicos del ecosistema del cine:

| Capa / Módulo | Rol Scrum Recomendado |
| :--- | :--- |
| **Boletería / Compras** | `Como cliente del cine...` |
| **Autenticación / Cuenta** | `Como cliente autenticado...` o `Como cliente o administrador del sistema...` |
| **Cartelera / Home** | `Como usuario visitante del sitio web...` |
| **Programación Funciones** | `Como administrador de programación de cartelera...` |
| **Administración General** | `Como administrador del cine...` |
| **Backoffice Candy Bar** | `Como operador del Backoffice administrativo...` |
| **Admisión / Entrada** | `Como personal de control de acceso en puerta...` |
| **Métricas / Negocio** | `Como director ejecutivo o administrador general...` |
| **Auditoría / Seguridad** | `Como supervisor de seguridad y operaciones...` |
| **Backend Core / API** | `Como equipo de desarrollo backend...` o `Como desarrollador backend...` |
| **Frontend SSR / UI** | `Como desarrollador frontend...` |
| **Base de Datos / Cloud** | `Como equipo de infraestructura y datos...` |
| **DevOps / Despliegue** | `Como desarrollador de infraestructura...` |
| **Equipo General** | `Como equipo de ingeniería del proyecto...` |

---

## 4. Tabla de Metadatos Scrum Obligatoria

Toda propuesta de Issue en Markdown (`outputs/plan_<usuario>.md` o planes integrales) debe acompañar cada tarjeta con una tabla de metadatos estandarizada:

| Campo | Opciones Válidas en el Repositorio |
| :--- | :--- |
| **Type** | `Feature` (funcionalidad de usuario), `Task` (tarea técnica/infra), `Bug` (corrección) |
| **Assignee** | Username de GitHub del responsable (`Sebastian0021`, `fcamporaa`, `lautaro-gomila`, etc.) |
| **Labels** | Combinar tipo (`enhancement`, `bug`, `documentation`) + capa técnica (`backend`, `frontend`, `database`, `infraestructura`) |
| **Milestone** | `Base y Arquitectura (E0)`, `Usuarios (E1)`, `Cartelera (E2)`, `Entradas (E3)`, `Servicios (E4)`, `Backoffice (E5)`, `Control QR (E6)`, `Dashboard (E7)`, `Deseable (E8)` |
| **Status** | `Unassigned`, `In progress`, `In review`, `Done` |
| **Priority** | `Alta` (P0/crítico), `Media` (P1/normal), `Baja` (P2/opcional) |
| **Size** | `XS`, `S`, `M`, `L`, `XL` |
| **Estimate** | Escala Fibonacci alineada a Size: `XS = 1`, `S = 2`, `M = 3`, `L = 5`, `XL = 8` |
| **Start date** | Fecha real de inicio (`YYYY-MM-DD`) |
| **Target date** | Fecha oficial de entrega del Hito correspondiente (`YYYY-MM-DD`) |
| **Development** | PR (`PR #125`) o commit (`commit 2a520b3`) de resolución |
| **Cierre** | `Close issue` → *Completed* (si ya se entregó) o *Leave Open* |

### Cronograma Oficial de Hitos (`Target date`):
* **Hito 1:** `2026-10-26` (Estructura base, carpetas, esquema SQL relacional).
* **Hito 2:** `2026-11-02` (Carril backend API REST, arquitectura 4 capas, maquetas SSR front).
* **Hito 3:** `2026-11-11` (Integración front-back, backoffice, validador QR, cloud DB, login web).
* **Hito 4:** `2026-11-18` (Checkout unificado, pago en efectivo, reportes PDF, hosting productivo y suite QA).

---

## 5. Reglas de Autolink de Git en Comentarios

Cuando se publiquen comentarios de trazabilidad o cierre en GitHub Issues vía scripts o comentarios manuales:

> [!CAUTION]
> **NUNCA envolver hashes de commits en comillas invertidas (backticks `` `...` ``)**.
> **NUNCA agregar fechas entre paréntesis `(YYYY-MM-DD)` al lado de los hashes de commits**.
> En GitHub, las comillas invertidas desactivan el parser de autolink y rompen el hipervínculo clickeable.

### Formato Permitido y Probado:
* **Para PRs:** `Resuelto en PR #125 — Implementación del módulo de autenticación.`
* **Para commits directos:** `Resuelto en commit 2a520b3 — Inicialización del esquema relacional en backend/db/init_db.sql.`
* **Para issues absorbidas:** `Cubierta por #64 ([HITO 2] [BACKEND] Implementar módulo transaccional de compras, detalle y cancelación).`

GitHub convertirá automáticamente `#125`, `commit 2a520b3` y `#64` en enlaces nativos clickeables.

---

## 6. Integración con el Flujo de Scripts del Workspace

Para sumar o modificar issues de forma rápida y segura:

1. **Inspección previa (Solo lectura):**
   ```bash
   .venv/bin/python .agents/skills/kanban-scrum-git/scripts/leer_github.py --repo fcamporaa/IDS_ProyectoFinal_equipo10 --project 4 --all-issues --out outputs/github_all_issues.json
   ```
2. **Generar el plan JSON:**
   - Si son issues **nuevas**: estructurar según `aplicar_kanban.py`.
   - Si son issues **existentes a actualizar / normalizar / limpiar**: estructurar según `actualizar_kanban.py` con `updates: [{"number": X, ...}]`.
3. **Dry-Run Offline Obligatorio:**
   ```bash
   .venv/bin/python .agents/skills/kanban-scrum-git/scripts/actualizar_kanban.py outputs/mi_plan.json --dry-run --github-snapshot outputs/github_all_issues.json
   ```
4. **Impacto en Vivo (con aprobación del usuario):**
   ```bash
   .venv/bin/python .agents/skills/kanban-scrum-git/scripts/actualizar_kanban.py outputs/mi_plan.json --no-audit
   ```

