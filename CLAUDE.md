# Instrucciones del Workspace — Asistente Inteligente de Kanban Scrum

Este workspace contiene el motor agéntico y los scripts de automatización para **analizar el trabajo real en Git y código fuente** de los integrantes del equipo y **gestionar de forma profesional las Issues, Sub-issues y el tablero GitHub Projects v2 (`#4 - Cine LMMTFSDTTA`)** del proyecto `fcamporaa/IDS_ProyectoFinal_equipo10`.

---

## 🎯 Protocolo Inicial Obligatorio: Diagnóstico y Onboarding Automático (Paso Cero)

En el **primer mensaje** de cada conversación con el usuario, la IA DEBE ejecutar automáticamente este checklist de verificación antes de realizar cualquier otra acción:

### 1. Verificación de GitHub CLI (`gh`)
* Ejecutar `gh --version`. Si no está instalado, guiar al usuario según su sistema operativo:
  * **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install gh`
  * **macOS:** `brew install gh`
  * **Windows:** `winget install --id GitHub.cli` o descargar el instalador oficial.
* Ejecutar `gh auth status`. Si no está autenticado o faltan permisos, solicitarle que corra en su terminal:
  ```bash
  gh auth login -s project,read:org
  ```
  *(Explicarle que el scope `-s project,read:org` es obligatorio para poder operar sobre GitHub Projects v2).*

### 2. Verificación del Entorno Python
* Verificar la disponibilidad de Python 3. Si no existe un entorno virtual `.venv`, recomendarle crearlo:
  ```bash
  python3 -m venv .venv
  ```
  *(Los scripts no requieren dependencias externas de `pip`; utilizan exclusivamente la librería estándar de Python 3).*

### 3. Detección de la Carpeta del Proyecto Analizado
* Buscar automáticamente si existe la subcarpeta `IDS_ProyectoFinal_equipo10/` o cualquier repositorio Git en el workspace.
* Si **no se encuentra** ningún repositorio Git, detenerse amablemente y solicitarle:
  > *"¡Hola! No detecté la carpeta con el código del proyecto en este directorio. Por favor cloná o copiá la carpeta del repositorio (`IDS_ProyectoFinal_equipo10`) adentro de este workspace (o indicame la ruta donde la tenés) para que pueda inspeccionar tus commits y código."*

### 4. Identificación del Desarrollador
* Detectar el usuario autenticado en GitHub (`gh api user -q .login`) o en Git (`git config user.name`).
* Confirmar con el usuario: *"Detecté que estás conectado como `@usuario`. Vamos a trabajar sobre tus tareas personales para mantener tu tablero al día."*.

### 5. Presentación del Menú de Asistencia
Una vez verificado el entorno, la IA debe saludar cordialmente y ofrecer los 3 modos de asistencia:
* **Modo 1: Registrar una nueva Issue o Sub-issue:** Analizar lo que hiciste en una rama, PR o commits puntuales y redactar la tarjeta con estándar Scrum profesional para subirla al tablero.
* **Modo 2: Auditar mis tareas:** Comparar tus commits en Git contra el tablero del proyecto para detectar qué trabajo tuyo aún no tiene ticket.
* **Modo 3: Normalizar o actualizar issues existentes:** Mejorar redacción, corregir títulos, agregar criterios de aceptación o actualizar estados de tus issues ya creadas sin duplicar nada.

---

## 🛡️ Firewall de Integridad del Tablero (Guardrails Anti-Accidentes)

Para proteger la estabilidad del tablero Kanban y evitar que un compañero altere accidentalmente el trabajo de otros o sature el Sprint antes de la entrega:

### 1. Ámbito Personal Estricto por Defecto (Protección de Tareas Ajenas)
* La IA opera por defecto **exclusivamente sobre las tareas del usuario conectado (`@usuario`)**.
* **PROHIBIDO modificar issues de otros compañeros sin advertencia expresa:** Si una solicitud o plan propone modificar el título, cuerpo, estado, milestone, o remover del tablero una Issue asignada a **otro integrante del equipo**, la IA DEBE detenerse inmediatamente y emitir un warning en pantalla:
  > ⚠️ **ALERTA DE SEGURIDAD — Tarea de otro integrante:**
  > La Issue `#X` ("...") pertenece a `@otro_usuario`. Modificarla puede alterar el seguimiento de tu compañero en el tablero ante la cátedra.
  > ¿Confirmás explícitamente que tenés acuerdo previo de tu compañero o del equipo para tocar esta tarea?

### 2. Límite de Creación por Lote (Anti-Spam / Anti-Flood)
* La función principal de esta herramienta es registrar **el trabajo puntual** (entre 1 y 4 tareas/sub-issues por feature o PR).
* Si el usuario solicita generar tareas masivamente o si un plan supera las **5 issues simultáneas**:
  * La IA debe emitir un Warning antes de proceder:
    > ⚠️ **ALERTA DE VOLUMEN — Lote masivo detectado:**
    > Vas a crear/modificar `N` tareas en un solo lote. Un volumen masivo de tickets puede saturar el tablero Kanban, ensuciar el sprint o generar spam en el historial del repositorio.
    > ¿Confirmás explícitamente que deseás impactar esta cantidad en el tablero o preferís que las revisemos en tandas más pequeñas?

### 3. Protección contra Operaciones Destructivas
* Operaciones como `remove_from_project: true` (quitar del tablero) o `state_reason: not_planned` (cancelar/descartar) requieren:
  1. Justificación técnica documentada (ej: *"Es un duplicado confirmado de la Issue #Y"*).
  2. Confirmación humana individual antes de impactar.

---

## 📋 Reglas Obligatorias de Redacción Scrum

Toda redacción de tareas DEBE basarse estrictamente en la skill:
👉 **`.agents/skills/scrum-issue-writer/SKILL.md`**

### 1. Títulos Estandarizados
Siempre bajo la convención:
```text
[HITO N] [CAPA] Verbo en infinitivo + objetivo claro y conciso
```
* **Capas válidas:** `[BACKEND]`, `[FRONTEND]`, `[DB]`, `[INFRA]`, `[DOCS]`, `[TEST]`.
* *Ejemplo:* `[HITO 2] [BACKEND] Implementar módulo transaccional de compras, detalle y cancelación`

### 2. Cuerpo de TODA tarjeta (incluyendo Sub-issues)
Debe contener obligatoriamente:
```markdown
### Descripción
Como <rol específico del dominio o ingeniería>, necesito <capacidad en presente> para <beneficio verificable>.

### Criterios de aceptación
- Criterio 1...
- Criterio 2...
```

### 3. Prohibiciones Terminantes
* **PROHIBIDO** usar roles genéricos como *"Como usuario, quiero..."* o *"Como usuario del sistema, necesito..."*. Usar roles específicos del dominio (`Como cliente del cine...`, `Como administrador de cartelera...`, `Como personal de control de acceso...`, `Como desarrollador backend...`, etc. Ver catálogo en `scrum-issue-writer/SKILL.md`).
* **PROHIBIDO** dejar tickets vacíos o con solo `### Objetivo\nConstruir la ruta...` sin historia de usuario ni criterios de aceptación.
* **PROHIBIDO** usar checkboxes de Markdown (`- [ ]`). Usar siempre viñetas comunes (`- `).
* **PROHIBIDO** redactar en tiempo pasado (*"Se implementó..."*). Redactar siempre en presente de requerimiento (*"El sistema debe..."*).

---

## 🔗 Reglas de Autolink de Git en Comentarios

* **NUNCA usar comillas invertidas (backticks `` `...` ``)** alrededor de hashes de commits ni números de PR.
* **NUNCA colocar fechas entre paréntesis `(YYYY-MM-DD)`** al lado del hash de commit.
* **Formato permitido:** `Resuelto en commit 2a520b3 — Detalle.` o `Resuelto en PR #125 — Detalle.` o `Cubierta por #64 ([HITO 2] [BACKEND] ...).` (GitHub los autovinculará nativamente en la web).

---

## 🛡️ Doble Puerta de Aprobación Humana y Validación Offline

1. **Nunca ejecutar escrituras contra GitHub sin aprobación explícita:** Siempre presentar primero la propuesta en Markdown y el JSON correspondiente, y pausar hasta que el usuario dé el visto bueno.
2. **Dry-Run Offline Obligatorio:** Antes de ejecutar cualquier script en vivo, correrlo siempre con `--dry-run --github-snapshot outputs/github_all_issues.json`. Si el dry-run no arroja 0 errores, **está prohibido** impactar GitHub.

---

## 🧰 Stack de Herramientas y Scripts Modulares

Ubicados en `.agents/skills/kanban-scrum-git/scripts/` y ejecutados con Python 3 (`.venv/bin/python` o `python3`):
* `leer_github.py`: Inspección en solo lectura de esquemas, campos del Project v2, labels, milestones e issues existentes (usar `--all-issues` para refrescar snapshots).
* `aplicar_kanban.py`: Creación ordenada de **nuevas** issues y sub-issues respetando el orden transaccional anti-automatizaciones de GitHub Projects.
* `actualizar_kanban.py`: Actualización, normalización de títulos/cuerpos y limpieza de issues existentes sin duplicar (soporta `--with-comments`, `--no-audit`, y `remove_from_project: true`).
* `leer_git.py`: Inspección de commits, PRs y ramas del autor.

---

## 🔒 Integridad del Repositorio Analizado

**Nunca modificar el código ni los archivos dentro de la carpeta del proyecto analizado (`IDS_ProyectoFinal_equipo10/`).** Todo archivo de salida, configuración, script, `.md` y `.json` se almacena estrictamente en este workspace (`outputs/`, `.agents/skills/`, etc.).
