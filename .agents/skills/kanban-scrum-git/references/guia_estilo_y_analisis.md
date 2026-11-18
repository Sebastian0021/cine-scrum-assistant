# Guía de Análisis Profundo de Código y Estilo Scrum

Esta referencia complementa a `SKILL.md` para asegurar que cada ticket redactado en `outputs/plan_<usuario>.md` refleje con precisión **el problema de negocio, el alcance funcional real y los criterios de aceptación verificables**, evitando redacciones genéricas basadas solo en mensajes de commit.

---

## 1. Protocolo de Inspección Profunda en el Repositorio Objetivo (Solo Lectura)

Después de correr `leer_git.py`, **nunca redactes tareas únicamente con el `subject` de los commits**. Entrá al código fuente dentro de la carpeta del proyecto objetivo (sin modificar nada) siguiendo estos pasos:

### A. Contexto global del producto y arquitectura
Antes de analizar commits individuales, leé en el repo objetivo:
1. `README.md` y documentación funcional (`docs/`, enunciado, backlog de hitos, plan de templates).
2. Contratos de API y esquema de datos (`docs/swagger.yaml`, `backend/db/*.sql`, modelos o esquemas).
3. Convenciones del equipo (`AGENTS.md` / `GEMINI.md` del proyecto objetivo si existen).

### B. Inspección de cambios por PR o commit
Para cada PR propio o commit directo reportado por `leer_git.py`:
1. **Revisar el diff completo del PR o commit** (en solo lectura):
   - PR merge commit: `git -C <repo> diff <merge_sha>^1..<merge_sha>^2 --stat` y `git -C <repo> show <hash>` para cada commit del autor.
   - Si el diff es extenso, inspeccionar por archivo con `git -C <repo> show <hash> -- <ruta>` o leer directamente el archivo actual en `<repo>/<ruta>`.
2. **Qué buscar dentro del código según la capa modificada:**
   - **Rutas / Controllers (`routes/`, `app.py`):** qué endpoints o vistas URL expone, métodos HTTP, decoradores de autenticación/roles, redirecciones (ej. patrón PRG, nombre exacto del endpoint corregido), validaciones previas.
   - **Services / Repositories (`services/`, `repositories/`):** reglas de negocio reales (ej. plazo de 24 h para cancelar, uso de `ahora_local()`, fallback si falla la API, manejo de transacciones o errores HTTP).
   - **Templates / CSS / JS (`templates/`, `static/`):** qué componentes visuales o interacciones reales se agregaron (ej. `stepper`, selector de sala, grilla de butacas disponibles/ocupadas/VIP, escáner QR con cámara y fallback manual), qué elementos se ocultan o habilitan por rol.
   - **Infra / DB / Config (`docker-compose.yml`, `init_db.sql`, `seed_data.sql`, `requirements.txt`):** variables de entorno, SSL, semillas, servidores WSGI, colecciones Postman.
3. **Detectar tareas ocultas o mezcladas (criterio de separación):**
   - Un mismo PR o incluso un mismo commit grande suele mezclar trabajo de **distintas épicas** o combinar una **feature nueva + un bugfix aparte**.
   - **Siempre** verificá los archivos tocados en `--stat`: si dentro de un PR de Control QR aparecen cambios en `perfil_routes.py` (Usuarios E1) o un fix en `compras_repository.py` (Entradas E3), separalos en Issues independientes apuntando al mismo PR/commit.
   - Si un PR tiene 2 o más entregables técnicos claros dentro de la misma épica (por ejemplo: vista SSR + integración JS de cámara, o tokens CSS/componentes globales + maquetado de página), modelalo como **Issue Padre (`Feature` o `Task`) + Sub-issues (`Task`)**.

---

## 2. Estilo y Estructura Scrum de Referencia

Seguí exactamente este formato y tono (tomado del estándar Scrum oficial del equipo), pero **adaptando los valores de `Priority`, `Status`, `Size`, `Milestone` y `Type` a las opciones exactas que devuelva `leer_github.py`**.

### Reglas de redacción
1. **Título:** `[HITO N] [CAPA] Verbo en infinitivo + objetivo funcional claro`, usando las capas reales del equipo (`[BACKEND]`, `[FRONTEND]`, `[DB]`, `[INFRA]`, `[DOCS]`) y dejando la épica/módulo en el `Milestone`. *(Ej.: `[HITO 2] [BACKEND] Definir estructura base...`, `[HITO 4] [FRONTEND] Habilitar validador QR...`).*
2. **Orientado a requerimiento (nunca en pasado):**
   - En **toda tarjeta** (Features, Tasks, Bugs e inclusive **Sub-issues**) → usar historia de usuario formal en `### Descripción`:
     `Como <rol específico del dominio o ingeniería>, necesito <capacidad o solución en tiempo presente> para <beneficio o valor técnico verificable>.`
   - En `Bug` → describir en **tiempo presente** el defecto observable y su impacto antes del fix, seguido de la causa y la solución esperada.
3. **Criterios de aceptación obligatorios:**
   - En **todas** las tarjetas (incluyendo Sub-issues), sección `### Criterios de aceptación` con viñetas comunes (`- ...`), **nunca** checkboxes (`- [ ]`).
   - Redacción verificable (`"El sistema debe..."`, `"El endpoint debe responder HTTP..."`, `"La vista debe renderizar..."`), citando reglas, rutas, helpers o comportamientos reales observados en el código.
4. **Metadatos siempre en tabla** al pie de cada Issue y Sub-issue.

---

### Ejemplo 1 — `Feature` con Sub-issues + separación de tareas de otras épicas

```markdown
### Issue 20 — Módulo de validación de ingresos QR en Backoffice

* **Título:**
  ```text
  [Control QR] Habilitar módulo de validación de ingresos QR en Backoffice
  ```

* **Descripción:**
  ```markdown
  ### Descripción
  Como administrador o personal de recepción del cine, necesito contar con una pantalla de validación de entradas en el Backoffice para escanear o ingresar códigos QR de los clientes, verificar si el ingreso es válido para la sala correspondiente y consultar el historial reciente de validaciones.

  ### Criterios de aceptación
  - Permitir validar entradas mediante lectura por cámara del dispositivo o ingreso manual del código QR, seleccionando la sala correspondiente.
  - Mostrar feedback visual claro del resultado de cada validación (aprobado, ya utilizado, inválido o error) junto con el detalle de la entrada y compra.
  - Exponer un historial filtrable de validaciones realizadas en la jornada y enlazar el acceso desde el Dashboard administrativo.
  ```

* **Campos a completar:**

  | Campo | Valor |
  | :--- | :--- |
  | **Type** | `Feature` |
  | **Assignee** | `Sebastian0021` |
  | **Label** | `enhancement` |
  | **Milestone** | `Control QR (E6)` |
  | **Status** | `Done` |
  | **Priority** | `Alta` |
  | **Size** | `L` |
  | **Estimate** | `5` |
  | **Start date** | `2026-11-09` |
  | **Target date** | `2026-11-18` |
  | **Development** | `PR #161` (`feature/admin-validador-qr`) |
  | **Cierre** | `Close issue` → *Completed* (después de sub-issues) |

#### Sub-issue 20.1

* **Título:**
  ```text
  [Backoffice] Implementar vista SSR, selector de sala e historial filtrable de validaciones QR
  ```

* **Descripción:**
  ```markdown
  ### Objetivo
  Construir la vista de recepción en `/admin/validador-qr`, conectarla con los endpoints de validaciones y salas del backend, implementar el patrón PRG para evitar reenvíos y enlazarla desde el Dashboard administrativo.

  ### Criterios de aceptación
  - Proteger la ruta con decorador de administrador y manejar expiración de sesión JWT.
  - Validar formato del token QR y filtros del historial (`resultado`, `id_compra`) antes de consultar al backend.
  - Mostrar tarjetas visuales diferenciadas según el resultado de validación y tabla de historial reciente.
  ```

* **Campos a completar:**

  | Campo | Valor |
  | :--- | :--- |
  | **Type** | `Task` |
  | **Assignee** | `Sebastian0021` |
  | **Label** | `enhancement` |
  | **Milestone** | `Control QR (E6)` |
  | **Status** | `Done` |
  | **Priority** | `Alta` |
  | **Size** | `M` |
  | **Estimate** | `3` |
  | **Start date** | `2026-11-10` |
  | **Target date** | `2026-11-18` |
  | **Relationships** | `Parent` = Issue 20 |
  | **Development** | `PR #161` (commit `9c33836`) |
  | **Cierre** | `Close issue` → *Completed* |
```

---

### Ejemplo 2 — `Task` de Arquitectura / Base

```markdown
### Issue 1 — Arquitectura multicapa del Backend

* **Título:**
  ```text
  [Backend] Definir estructura base y arquitectura en 4 capas de la API REST
  ```

* **Descripción:**
  ```markdown
  ### Descripción
  Como equipo de desarrollo backend, necesitamos contar con una estructura modular y uniforme en Flask para organizar los distintos módulos del sistema de cine (autenticación, películas, funciones, salas, compras, servicios, validaciones y dashboard) sin acoplar rutas con lógica de negocio o consultas SQL.

  ### Criterios de aceptación
  - La aplicación Flask debe registrar blueprints separados por módulo funcional.
  - Cada módulo debe respetar la separación en 4 capas: `routes`, `validators`, `services` y `repositories`.
  - Debe existir configuración centralizada de constantes, conexión a MySQL y utilidades compartidas.
  - Debe incluir archivo de variables de entorno de ejemplo, script de inicio y dependencias iniciales.
  ```

* **Campos a completar:**

  | Campo | Valor |
  | :--- | :--- |
  | **Type** | `Task` |
  | **Assignee** | `Sebastian0021` |
  | **Label** | `enhancement` |
  | **Milestone** | `Base y Arquitectura (E0)` |
  | **Status** | `Done` |
  | **Priority** | `Alta` |
  | **Size** | `L` |
  | **Estimate** | `5` |
  | **Start date** | `2026-10-28` |
  | **Target date** | `2026-11-02` |
  | **Development** | `PR #116` (`feat/estructura-backend`) |
  | **Cierre** | `Close issue` → *Completed* |
```

---

### Ejemplo 3 — `Bug` independiente (con PR o commit directo)

```markdown
### Issue 23 — Corregir redirección de Candy Bar hacia checkout principal

* **Título:**
  ```text
  [Servicios] Corregir redirección desde selección de Candy Bar hacia el checkout principal
  ```

* **Descripción:**
  ```markdown
  ### Descripción
  Al confirmar u omitir la selección de servicios de Candy Bar, la redirección apunta a un endpoint inexistente (`compras.checkout`), provocando un error de enrutamiento en lugar de avanzar al paso de checkout.

  ### Criterios de aceptación
  - Corregir las redirecciones del paso de selección de servicios (tanto al confirmar como al omitir) para apuntar a la ruta válida del checkout principal (`compra.seleccion_checkout`).
  ```

* **Campos a completar:**

  | Campo | Valor |
  | :--- | :--- |
  | **Type** | `Bug` |
  | **Assignee** | `Sebastian0021` |
  | **Label** | `bug` |
  | **Milestone** | `Servicios (E4)` |
  | **Status** | `Done` |
  | **Priority** | `Alta` |
  | **Size** | `XS` |
  | **Estimate** | `1` |
  | **Start date** | `2026-11-11` |
  | **Target date** | `2026-11-18` |
  | **Development** | Sin PR (commit directo en `develop`: `5196ce4`) |
  | **Cierre** | Comentar hash `5196ce4` y `Close issue` → *Completed* |
```

