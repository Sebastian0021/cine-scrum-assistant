# 🎬 Asistente Inteligente de Kanban & Scrum — Cine LMMTFSDTTA

Herramienta de automatización y asistencia agéntica diseñada para el equipo de desarrollo de **Cine LMMTFSDTTA** (`fcamporaa/IDS_ProyectoFinal_equipo10`).

Permite a cualquier integrante del equipo auditar su trabajo en Git, redactar Issues y Sub-issues con calidad Scrum profesional estricta (aprobada por la cátedra) y cargarlas o actualizarlas automáticamente en **GitHub Projects v2 (`#4`)** sin errores manuales ni duplicaciones.

---

## 🚀 Inicio Rápido en 3 Pasos

### Paso 1: Clonar este repositorio
```bash
git clone <URL_DE_ESTE_REPO> scrum-assistant
cd scrum-assistant
```

### Paso 2: Colocar la carpeta del proyecto adentro
Cloná o copiá la carpeta del proyecto del equipo (`IDS_ProyectoFinal_equipo10`) dentro de esta carpeta:
```bash
git clone git@github.com:fcamporaa/IDS_ProyectoFinal_equipo10.git
```
*(Ya está configurada en `.gitignore`, por lo que nunca vas a ensuciar ni anidar repositorios de Git).*

### Paso 3: Abrir tu Agente de IA favorito y chatear
Abrí esta carpeta en tu entorno de IA preferido:
* **Antigravity / Cursor / Windsurf**
* **Claude Code** (`CLAUDE.md`)
* **Gemini Code Assist / Gemini CLI** (`GEMINI.md`)

Iniciá un chat simplemente diciendo:
> **"Hola, leé AGENTS.md y ayudame a registrar mis tareas."**

¡Listo! La IA se encargará de verificar tu entorno, comprobar si tenés instalado `gh`, ver si estás logueado y guiarte paso a paso.

---

## 🛠️ Requisitos Previos Mínimos

1. **Python 3:** Disponible en tu sistema (`python3 --version`). No requiere instalar dependencias con `pip` (usa 100% librería estándar).
2. **GitHub CLI (`gh`):**
   * Si no lo tenés:
     * **Ubuntu/Debian:** `sudo apt install gh`
     * **macOS:** `brew install gh`
     * **Windows:** `winget install --id GitHub.cli`
   * Iniciar sesión con permisos de Project:
     ```bash
     gh auth login -s project,read:org
     ```
     *(El parámetro `-s project,read:org` es indispensable para que los scripts puedan interactuar con el tablero de GitHub Projects v2).*

---

## 💡 ¿Qué puede hacer el Asistente por vos?

### 1. Registrar una nueva Issue o Sub-issue (desde tus cambios reales)
* Le decís en qué rama trabajaste o qué commits hiciste.
* La IA inspecciona el código y los diffs reales (`git diff`, `git log`).
* Redacta la Issue bajo el estándar oficial:
  * **Título estandarizado:** `[HITO N] [CAPA] Verbo en infinitivo + objetivo claro`.
  * **Historia de usuario formal en tiempo presente:** `Como <rol del cine>, necesito <capacidad> para <valor verificable>.`
  * **Criterios de aceptación verificables:** Viñetas simples (`- `), sin checkboxes.
  * **Metadatos completos:** Milestone, Labels, Priority, Size, Estimate (Fibonacci), Start Date y Target Date oficial.
* Te presenta la propuesta para que la apruebes.
* Tras tu confirmación, corre un simulacro offline (`--dry-run`) y la sube en vivo a GitHub Issues y al Project v2.

### 2. Auditar tus tareas pendientes en Git
* La IA filtra todos tus commits y PRs del repositorio.
* Los compara contra las issues ya creadas en el tablero.
* Te lista con total precisión qué funcionalidades o commits están "huérfanos" (sin ticket asociado) para que no te olvides de nada.

### 3. Normalizar o corregir Issues ya creadas
* Si ya creaste issues a mano pero tienen títulos desprolijos, les faltan criterios de aceptación o querés vincularles Sub-issues sin recrearlas ni duplicarlas en el tablero, la IA las actualiza de forma limpia y transaccional.

---

## 📁 Estructura del Workspace

```text
.
├── .agents/
│   └── skills/
│       ├── kanban-scrum-git/       # Scripts transaccionales (leer_git, leer_github, aplicar, actualizar)
│       └── scrum-issue-writer/     # Estándar y catálogo oficial de roles y capas
├── outputs/                        # Almacena snapshots de GitHub y propuestas en JSON/MD
├── AGENTS.md                       # Protocolo maestro para agentes de IA
├── GEMINI.md                       # Protocolo para Gemini Code Assist
├── CLAUDE.md                       # Protocolo para Claude Code
├── README.md                       # Esta guía
└── IDS_ProyectoFinal_equipo10/     # Carpeta con el código del equipo (ignorada en git)
```

---

## 🛡️ Seguridad, Firewall del Tablero y Doble Puerta de Aprobación

* **Firewall de tareas ajenas:** El asistente está configurado para gestionar exclusivamente **tus propias tareas**. Si una operación intenta modificar, mover o cerrar issues asignadas a otro compañero de equipo, la IA se detendrá y te pedirá confirmación explícita con advertencia.
* **Control de volumen (Anti-Spam):** Para evitar desestabilizar el tablero o el sprint cerca de la entrega, el asistente opera sobre tareas puntuales (1 a 4 por tanda). Si detecta un lote de más de 5 tareas, te advertirá antes de proceder.
* **Lectura protegida:** El asistente **NUNCA modifica ningún archivo** dentro de `IDS_ProyectoFinal_equipo10/`.
* **Sin sorpresas:** La IA **NUNCA sube nada a GitHub** sin mostrarte primero la redacción en Markdown y esperar tu confirmación explícita.
* **Trazabilidad limpia:** Todos los comentarios de Git se enlazan con autolinks nativos de GitHub (`commit abc1234` o `PR #125`).

