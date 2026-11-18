#!/usr/bin/env python3
"""Valida y aplica un plan Kanban Scrum (JSON) en GitHub Issues y Projects v2.

Soporta validación estricta contra el esquema real del repositorio/Project v2,
modo simulación (--dry-run), orden transaccional anti-automatizaciones (Sub-issues
cerradas antes que el Padre) y verificación final vía GraphQL.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import leer_github  # noqa: E402

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SIZE_ESTIMATE_MAP = {"XS": 1, "S": 2, "M": 3, "L": 5, "XL": 8}


def gh_rest_write(method: str, endpoint: str, payload: dict) -> dict:
    """Ejecuta una mutación REST (POST/PATCH) vía `gh api --input -`."""
    raw = leer_github.run_gh(
        ["api", "--method", method, endpoint, "--input", "-"],
        stdin_data=json.dumps(payload),
    )
    return json.loads(raw) if raw.strip() else {}


def gh_graphql_write(query: str, variables: dict) -> dict:
    """Ejecuta una mutación GraphQL vía `gh api graphql --input -`."""
    return leer_github.gh_graphql(query, variables)


def cargar_plan(plan_path: Path) -> dict:
    """Carga y valida la estructura raíz mínima del archivo JSON del plan."""
    if not plan_path.exists():
        raise FileNotFoundError(f"No existe el archivo de plan: {plan_path}")
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    for key in ("repo", "project", "issues"):
        if key not in data:
            raise ValueError(f"Falta la clave obligatoria '{key}' en {plan_path}")
    if not isinstance(data["issues"], list) or not data["issues"]:
        raise ValueError("El campo 'issues' debe ser una lista no vacía.")
    return data


def construir_indice_esquema(gh_state: dict) -> dict:
    """Indexa catálogos reales de GitHub para validación O(1)."""
    milestones = {m["title"]: m["number"] for m in gh_state.get("milestones", [])}
    labels = {l["name"] for l in gh_state.get("labels", [])}
    issue_types = {
        it["name"]: it
        for it in gh_state.get("issue_types", [])
        if it.get("is_enabled", True)
    }
    existing_issues = {
        (iss.get("title") or "").strip().lower(): iss
        for iss in gh_state.get("issues", [])
    }

    project = gh_state.get("project")
    fields_by_name: dict[str, dict] = {}
    if project:
        for f in project.get("fields", []):
            options_map = {opt["name"]: opt["id"] for opt in f.get("options", [])}
            fields_by_name[f["name"]] = {
                "id": f["id"],
                "data_type": f.get("data_type"),
                "options": options_map,
            }

    return {
        "milestones": milestones,
        "labels": labels,
        "issue_types": issue_types,
        "existing_issues": existing_issues,
        "project": project,
        "fields": fields_by_name,
        "viewer": (gh_state.get("viewer") or {}).get("login"),
    }


def _validar_opcion_campo(
    errors: list[str],
    fields: dict[str, dict],
    field_name: str,
    value: object,
    ctx: str,
) -> None:
    if value is None:
        return
    if field_name not in fields:
        errors.append(f"{ctx}: el Project v2 no tiene el campo '{field_name}'.")
        return
    options = fields[field_name]["options"]
    if str(value) not in options:
        validas = ", ".join(options.keys()) or "(sin opciones)"
        errors.append(
            f"{ctx}: valor inválido '{value}' para '{field_name}'. Opciones reales: {validas}"
        )


def _validar_item(
    item: dict,
    ctx: str,
    idx: dict,
    planned_milestones: set[str],
    seen_titles: set[str],
    default_assignee: str | None,
    errors: list[str],
    warnings: list[str],
    skip_existing: bool,
) -> None:
    title = (item.get("title") or "").strip()
    if not title:
        errors.append(f"{ctx}: falta 'title'.")
        return

    norm_title = title.lower()
    if norm_title in seen_titles:
        errors.append(f"{ctx}: título duplicado dentro del mismo plan JSON ('{title}').")
    seen_titles.add(norm_title)

    if norm_title in idx["existing_issues"]:
        existing = idx["existing_issues"][norm_title]
        msg = f"{ctx}: ya existe en GitHub como #{existing['number']} ({existing['state']}): '{title}'."
        if skip_existing:
            warnings.append(f"[SKIP] {msg}")
        else:
            errors.append(msg)

    issue_type = item.get("type")
    if issue_type:
        if idx["issue_types"] and issue_type not in idx["issue_types"]:
            valid_types = ", ".join(idx["issue_types"].keys())
            errors.append(f"{ctx}: type '{issue_type}' inválido. Activos: {valid_types}")

    for lbl in item.get("labels", []):
        if lbl not in idx["labels"]:
            errors.append(f"{ctx}: label '{lbl}' no existe en el repositorio.")

    milestone = item.get("milestone")
    if milestone and milestone not in idx["milestones"] and milestone not in planned_milestones:
        errors.append(
            f"{ctx}: milestone '{milestone}' no existe en GitHub ni está en 'milestones_a_crear'."
        )

    assignees = item.get("assignees")
    item_assignee = item.get("assignee") or default_assignee
    if assignees is None and not item_assignee:
        warnings.append(f"{ctx}: sin assignee configurado.")
    elif item_assignee and idx.get("viewer") and item_assignee != idx.get("viewer"):
        warnings.append(
            f"⚠️ SEGURIDAD ({ctx}): Asignada a @{item_assignee}, que no coincide con tu usuario conectado (@{idx.get('viewer')}). Asegurate de tener acuerdo previo."
        )

    fields = idx["fields"]
    _validar_opcion_campo(errors, fields, "Status", item.get("status"), ctx)
    _validar_opcion_campo(errors, fields, "Priority", item.get("priority"), ctx)
    _validar_opcion_campo(errors, fields, "Size", item.get("size"), ctx)

    estimate = item.get("estimate")
    if estimate is not None:
        if not isinstance(estimate, (int, float)):
            errors.append(f"{ctx}: 'estimate' debe ser numérico (recibido: {estimate!r}).")
        elif item.get("size") in SIZE_ESTIMATE_MAP:
            expected = SIZE_ESTIMATE_MAP[item["size"]]
            if estimate != expected:
                warnings.append(
                    f"{ctx}: Size={item['size']} suele corresponder a Estimate={expected} (tiene {estimate})."
                )

    for date_key in ("start_date", "target_date"):
        dval = item.get(date_key)
        if dval is not None and not DATE_RE.match(str(dval)):
            errors.append(f"{ctx}: '{date_key}' debe tener formato YYYY-MM-DD (recibido: {dval!r}).")


def validar_plan(
    plan: dict, gh_state: dict, skip_existing: bool = False
) -> tuple[list[str], list[str]]:
    """Valida permisos, campos del Project v2, catálogos y no-duplicación."""
    errors: list[str] = []
    warnings: list[str] = []
    idx = construir_indice_esquema(gh_state)

    perms = (gh_state.get("repo") or {}).get("permissions") or {}
    if not perms.get("push"):
        errors.append("El usuario autenticado en `gh` no tiene permiso 'push' sobre el repo.")

    project = idx["project"]
    if not project:
        errors.append("No se obtuvo esquema del Project v2 destino.")
    elif not project.get("viewer_can_update"):
        errors.append("El usuario autenticado no tiene permiso 'viewerCanUpdate' sobre el Project v2.")

    planned_milestones = {
        (m.get("title") or "").strip()
        for m in plan.get("milestones_a_crear", [])
        if (m.get("title") or "").strip()
    }
    seen_titles: set[str] = set()
    default_assignee = plan.get("assignee")

    # Guardrail: Warning si se intenta crear un lote masivo
    total_items = len(plan["issues"]) + sum(len(iss.get("sub_issues", [])) for iss in plan["issues"])
    if total_items > 5:
        warnings.append(
            f"⚠️ ALERTA DE VOLUMEN: Se crearán {total_items} tareas en un solo lote (> 5). Verificar que no desestabilice el tablero ni genere spam."
        )

    for i, issue in enumerate(plan["issues"], start=1):
        ctx = f"Issue[{i}]"
        _validar_item(
            item=issue,
            ctx=ctx,
            idx=idx,
            planned_milestones=planned_milestones,
            seen_titles=seen_titles,
            default_assignee=default_assignee,
            errors=errors,
            warnings=warnings,
            skip_existing=skip_existing,
        )
        for j, sub in enumerate(issue.get("sub_issues", []), start=1):
            _validar_item(
                item=sub,
                ctx=f"{ctx}.Sub[{j}]",
                idx=idx,
                planned_milestones=planned_milestones,
                seen_titles=seen_titles,
                default_assignee=default_assignee,
                errors=errors,
                warnings=warnings,
                skip_existing=skip_existing,
            )

    return errors, warnings


def _normalizar_prs(pr_ref: object) -> list[int]:
    if pr_ref is None:
        return []
    if isinstance(pr_ref, int):
        return [pr_ref]
    if isinstance(pr_ref, list):
        return [int(x) for x in pr_ref if x is not None]
    return [int(pr_ref)]


def construir_comentario_trazabilidad(item: dict) -> str | None:
    """Genera el texto del comentario con referencia a PR(s) y commits sin backticks para que GitHub cree links."""
    if item.get("comment"):
        return str(item["comment"]).strip()

    prs = _normalizar_prs(item.get("pr_referencia"))
    commits = [str(c).strip() for c in item.get("commits", []) if str(c).strip()]
    if not prs and not commits:
        return None

    partes: list[str] = []
    if prs:
        pr_str = ", ".join(f"#{n}" for n in prs)
        partes.append(f"PR {pr_str}")
    else:
        partes.append("commit directo")

    if commits:
        # Sin backticks para permitir que GitHub genere el autolink clickable
        commits_str = ", ".join(f"commit {c}" for c in commits)
        partes.append(commits_str)

    return f"Resuelto en {' — '.join(partes)}."


def resolver_assignees(item: dict, default_assignee: str | None) -> list[str]:
    """Obtiene la lista de assignees para un issue o sub-issue."""
    if isinstance(item.get("assignees"), list):
        return [str(a) for a in item["assignees"] if str(a).strip()]
    single = item.get("assignee") or default_assignee
    return [str(single)] if single else []


def crear_milestone(owner: str, repo: str, milestone_cfg: dict) -> dict:
    """Crea un Milestone en el repositorio."""
    payload = {"title": milestone_cfg["title"]}
    if milestone_cfg.get("description"):
        payload["description"] = milestone_cfg["description"]
    if milestone_cfg.get("due_on"):
        payload["due_on"] = f"{milestone_cfg['due_on']}T23:59:59Z"
    return gh_rest_write("POST", f"repos/{owner}/{repo}/milestones", payload)


def crear_issue(
    owner: str,
    repo: str,
    item: dict,
    milestone_map: dict[str, int],
    default_assignee: str | None,
) -> dict:
    """Crea un Issue en GitHub con type, labels, assignees y milestone."""
    payload: dict[str, object] = {
        "title": item["title"],
        "body": item.get("body", ""),
    }
    assignees = resolver_assignees(item, default_assignee)
    if assignees:
        payload["assignees"] = assignees
    if item.get("labels"):
        payload["labels"] = list(item["labels"])
    if item.get("milestone"):
        payload["milestone"] = milestone_map[item["milestone"]]
    if item.get("type"):
        payload["type"] = item["type"]

    return gh_rest_write("POST", f"repos/{owner}/{repo}/issues", payload)


def vincular_sub_issue(
    owner: str, repo: str, parent_number: int, child_database_id: int
) -> dict:
    """Enlaza un sub-issue existente al Issue padre usando su database_id entero."""
    return gh_rest_write(
        "POST",
        f"repos/{owner}/{repo}/issues/{parent_number}/sub_issues",
        {"sub_issue_id": child_database_id},
    )


def agregar_item_project(project_id: str, issue_node_id: str) -> str:
    """Agrega un Issue al Project v2 y devuelve su item_id (PVTI_...)."""
    mutation = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item {
          id
        }
      }
    }
    """
    data = gh_graphql_write(mutation, {"projectId": project_id, "contentId": issue_node_id})
    return data["addProjectV2ItemById"]["item"]["id"]


def actualizar_campo_project(
    project_id: str, item_id: str, field_id: str, value_input: dict
) -> None:
    """Actualiza el valor de un campo de un item en Project v2."""
    mutation = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
      updateProjectV2ItemFieldValue(
        input: {projectId: $projectId, itemId: $itemId, fieldId: $fieldId, value: $value}
      ) {
        projectV2Item {
          id
        }
      }
    }
    """
    gh_graphql_write(
        mutation,
        {
            "projectId": project_id,
            "itemId": item_id,
            "fieldId": field_id,
            "value": value_input,
        },
    )


def aplicar_metadatos_project(
    project_id: str, item_id: str, item_cfg: dict, fields: dict[str, dict]
) -> None:
    """Setea Priority, Size, Estimate, Start date y Target date (SIN tocar Status aún)."""
    for fname, cfg_key in (("Priority", "priority"), ("Size", "size")):
        val = item_cfg.get(cfg_key)
        if val is not None and fname in fields:
            opt_id = fields[fname]["options"][str(val)]
            actualizar_campo_project(
                project_id, item_id, fields[fname]["id"], {"singleSelectOptionId": opt_id}
            )

    if item_cfg.get("estimate") is not None and "Estimate" in fields:
        actualizar_campo_project(
            project_id,
            item_id,
            fields["Estimate"]["id"],
            {"number": float(item_cfg["estimate"])},
        )

    for fname, cfg_key in (("Start date", "start_date"), ("Target date", "target_date")):
        dval = item_cfg.get(cfg_key)
        if dval is not None and fname in fields:
            actualizar_campo_project(
                project_id, item_id, fields[fname]["id"], {"date": str(dval)}
            )


def aplicar_status_y_cierre(
    owner: str,
    repo: str,
    project_id: str,
    project_item_id: str,
    issue_number: int,
    item_cfg: dict,
    fields: dict[str, dict],
) -> None:
    """Aplica el Status final en Project v2 y cierra el Issue como COMPLETED si corresponde."""
    status_val = item_cfg.get("status")
    if status_val is not None and "Status" in fields:
        opt_id = fields["Status"]["options"][str(status_val)]
        actualizar_campo_project(
            project_id,
            project_item_id,
            fields["Status"]["id"],
            {"singleSelectOptionId": opt_id},
        )

    if item_cfg.get("cerrar"):
        current = leer_github.gh_rest(f"repos/{owner}/{repo}/issues/{issue_number}")
        if current.get("state") == "closed" and current.get("state_reason") == "completed":
            return
        try:
            gh_rest_write(
                "PATCH",
                f"repos/{owner}/{repo}/issues/{issue_number}",
                {"state": "closed", "state_reason": "completed"},
            )
        except RuntimeError:
            recheck = leer_github.gh_rest(f"repos/{owner}/{repo}/issues/{issue_number}")
            if not (recheck.get("state") == "closed" and recheck.get("state_reason") == "completed"):
                raise


def publicar_comentario(owner: str, repo: str, issue_number: int, body: str) -> None:
    """Publica un comentario de trazabilidad en el Issue."""
    gh_rest_write(
        "POST",
        f"repos/{owner}/{repo}/issues/{issue_number}/comments",
        {"body": body},
    )


def verificar_estado_final(node_ids: list[str], project_number: int) -> list[dict]:
    """Consulta GraphQL final sobre los Issues creados para confirmar estado y Project."""
    if not node_ids:
        return []
    query = """
    query($ids: [ID!]!) {
      nodes(ids: $ids) {
        ... on Issue {
          number
          title
          state
          stateReason
          url
          issueType { name }
          milestone { title }
          parent { number }
          subIssues(first: 50) { nodes { number state } }
          projectItems(first: 10) {
            nodes {
              id
              project { number title }
              fieldValues(first: 20) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                  ... on ProjectV2ItemFieldNumberValue {
                    number
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                  ... on ProjectV2ItemFieldDateValue {
                    date
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    data = leer_github.gh_graphql(query, {"ids": node_ids})
    verified: list[dict] = []
    for node in data.get("nodes") or []:
        if not node:
            continue
        proj_fields = {}
        for pi in (node.get("projectItems") or {}).get("nodes") or []:
            if (pi.get("project") or {}).get("number") == project_number:
                for fv in (pi.get("fieldValues") or {}).get("nodes") or []:
                    fname = (fv.get("field") or {}).get("name")
                    if fname:
                        proj_fields[fname] = (
                            fv.get("name")
                            if "name" in fv
                            else fv.get("number", fv.get("date"))
                        )
        verified.append(
            {
                "number": node.get("number"),
                "title": node.get("title"),
                "state": node.get("state"),
                "state_reason": node.get("stateReason"),
                "url": node.get("url"),
                "type": (node.get("issueType") or {}).get("name"),
                "milestone": (node.get("milestone") or {}).get("title"),
                "parent_number": (node.get("parent") or {}).get("number"),
                "sub_issues_count": len((node.get("subIssues") or {}).get("nodes") or []),
                "project_fields": proj_fields,
            }
        )
    return verified


def imprimir_dry_run(plan: dict, gh_state: dict, warnings: list[str]) -> None:
    """Imprime la simulación exacta paso a paso sin mutar nada en GitHub."""
    idx = construir_indice_esquema(gh_state)
    default_assignee = plan.get("assignee")
    project = gh_state["project"]

    print(f"=== DRY-RUN OK | Repo: {plan['repo']} | Project #{project['number']} ({project['title']}) ===")
    if warnings:
        print("\nAdvertencias:")
        for w in warnings:
            print(f"  [!] {w}")

    milestones_to_create = [
        m for m in plan.get("milestones_a_crear", [])
        if m["title"] not in idx["milestones"]
    ]
    print(f"\nPaso 1 — Milestones a crear: {len(milestones_to_create)}")
    for m in milestones_to_create:
        print(f"  + Milestone: {m['title']}")

    total_parents = len(plan["issues"])
    total_subs = sum(len(i.get("sub_issues", [])) for i in plan["issues"])
    print(f"\nPasos 2-7 — Issues a crear: {total_parents} padre(s) + {total_subs} sub-issue(s)")

    pr_links: dict[int, list[str]] = {}
    for pos, issue in enumerate(plan["issues"], start=1):
        norm_title = issue["title"].strip().lower()
        skip_flag = " [OMITIR: ya existe]" if norm_title in idx["existing_issues"] else ""
        assignees = ", ".join(resolver_assignees(issue, default_assignee)) or "-"
        print(
            f"  {pos}. [{issue.get('type', '?')}] {issue['title']}{skip_flag}\n"
            f"     milestone={issue.get('milestone', '-')} | labels={issue.get('labels', [])} "
            f"| assignees={assignees} | priority={issue.get('priority')} | size={issue.get('size')} "
            f"| est={issue.get('estimate')} | {issue.get('start_date')}..{issue.get('target_date')} "
            f"| final_status={issue.get('status')} | cerrar={issue.get('cerrar', False)}"
        )
        for pr in _normalizar_prs(issue.get("pr_referencia")):
            pr_links.setdefault(pr, []).append(issue["title"])

        for sidx, sub in enumerate(issue.get("sub_issues", []), start=1):
            sub_skip = (
                " [OMITIR: ya existe]"
                if sub["title"].strip().lower() in idx["existing_issues"]
                else ""
            )
            print(
                f"     {pos}.{sidx} [{sub.get('type', '?')}] {sub['title']}{sub_skip}\n"
                f"         priority={sub.get('priority')} | size={sub.get('size')} "
                f"| est={sub.get('estimate')} | final_status={sub.get('status')} "
                f"| cerrar={sub.get('cerrar', False)}"
            )
            for pr in _normalizar_prs(sub.get("pr_referencia")):
                pr_links.setdefault(pr, []).append(sub["title"])

        print("     -> Orden de cierre: primero sub-issues (Status + Close), al final Issue padre.")

    if pr_links:
        print("\nPRs para vincular manualmente en Development (cuando se aplique):")
        for pr_num in sorted(pr_links):
            print(f"  - PR #{pr_num}: {', '.join(pr_links[pr_num])}")


def aplicar_plan(
    plan: dict,
    gh_state: dict,
    skip_existing: bool,
    no_comments: bool = False,
) -> dict:
    """Ejecuta la creación y configuración ordenada en GitHub Issues y Project v2."""
    owner, repo = leer_github.parsear_owner_repo(plan["repo"])
    idx = construir_indice_esquema(gh_state)
    milestone_map = dict(idx["milestones"])
    fields = idx["fields"]
    project = idx["project"]
    project_id = project["id"]
    default_assignee = plan.get("assignee")

    # Paso 1: Milestones faltantes
    created_milestones: list[dict] = []
    for m_cfg in plan.get("milestones_a_crear", []):
        title = m_cfg["title"].strip()
        if title in milestone_map:
            continue
        created_m = crear_milestone(owner, repo, m_cfg)
        milestone_map[title] = created_m["number"]
        created_milestones.append({"number": created_m["number"], "title": title})

    # Pasos 2 al 7 por cada grupo (Padre + sus Sub-issues)
    created_records: list[dict] = []
    all_node_ids: list[str] = []
    pr_to_issues: dict[int, list[int]] = {}
    tracked_items: dict[int, tuple[str, dict]] = {}

    for issue_cfg in plan["issues"]:
        norm_title = issue_cfg["title"].strip().lower()
        if skip_existing and norm_title in idx["existing_issues"]:
            continue

        # Paso 2a: Crear Issue Padre
        parent_res = crear_issue(owner, repo, issue_cfg, milestone_map, default_assignee)
        parent_num = parent_res["number"]
        parent_node_id = parent_res["node_id"]
        all_node_ids.append(parent_node_id)

        for pr in _normalizar_prs(issue_cfg.get("pr_referencia")):
            pr_to_issues.setdefault(pr, []).append(parent_num)

        # Paso 2b y 3: Crear y enlazar Sub-issues
        sub_results: list[tuple[dict, dict]] = []
        for sub_cfg in issue_cfg.get("sub_issues", []):
            sub_res = crear_issue(owner, repo, sub_cfg, milestone_map, default_assignee)
            all_node_ids.append(sub_res["node_id"])
            vincular_sub_issue(owner, repo, parent_num, sub_res["id"])
            for pr in _normalizar_prs(sub_cfg.get("pr_referencia")):
                pr_to_issues.setdefault(pr, []).append(sub_res["number"])
            sub_results.append((sub_cfg, sub_res))

        # Paso 4: Agregar Padre y Sub-issues al Project v2
        parent_item_id = agregar_item_project(project_id, parent_node_id)
        tracked_items[parent_num] = (parent_item_id, issue_cfg)
        sub_item_ids: list[str] = []
        for sub_cfg, sub_res in sub_results:
            s_item_id = agregar_item_project(project_id, sub_res["node_id"])
            sub_item_ids.append(s_item_id)
            tracked_items[sub_res["number"]] = (s_item_id, sub_cfg)

        # Paso 5: Setear metadatos (sin Status todavía) en Padre y Sub-issues
        aplicar_metadatos_project(project_id, parent_item_id, issue_cfg, fields)
        for (sub_cfg, _), sub_item_id in zip(sub_results, sub_item_ids):
            aplicar_metadatos_project(project_id, sub_item_id, sub_cfg, fields)

        # Paso 6: Comentario de trazabilidad (opcional)
        if not no_comments:
            parent_comment = construir_comentario_trazabilidad(issue_cfg)
            if parent_comment:
                publicar_comentario(owner, repo, parent_num, parent_comment)
            for sub_cfg, sub_res in sub_results:
                sub_comment = construir_comentario_trazabilidad(sub_cfg)
                if sub_comment:
                    publicar_comentario(owner, repo, sub_res["number"], sub_comment)

        # Paso 7: Status = Done y cierre: PRIMERO todas las Sub-issues, AL FINAL el Padre
        for (sub_cfg, sub_res), sub_item_id in zip(sub_results, sub_item_ids):
            aplicar_status_y_cierre(
                owner, repo, project_id, sub_item_id, sub_res["number"], sub_cfg, fields
            )

        aplicar_status_y_cierre(
            owner, repo, project_id, parent_item_id, parent_num, issue_cfg, fields
        )

        created_records.append(
            {
                "parent": {
                    "number": parent_num,
                    "title": issue_cfg["title"],
                    "url": parent_res["html_url"],
                },
                "sub_issues": [
                    {
                        "number": sub_res["number"],
                        "title": sub_cfg["title"],
                        "url": sub_res["html_url"],
                    }
                    for sub_cfg, sub_res in sub_results
                ],
            }
        )

    # Paso 8: Verificación final vía GraphQL + autocorrección puntual de Status si una automatización lo revirtió
    verified = verificar_estado_final(all_node_ids, project["number"])
    reapplied = False
    for v in verified:
        num = v["number"]
        if num in tracked_items:
            p_item_id, item_cfg = tracked_items[num]
            expected_status = item_cfg.get("status")
            if expected_status and v["project_fields"].get("Status") != expected_status:
                aplicar_status_y_cierre(
                    owner, repo, project_id, p_item_id, num, item_cfg, fields
                )
                reapplied = True
    if reapplied:
        verified = verificar_estado_final(all_node_ids, project["number"])

    return {
        "repo": plan["repo"],
        "project": {"number": project["number"], "title": project["title"], "url": project["url"]},
        "milestones_creados": created_milestones,
        "issues_creados": created_records,
        "verificacion_final": verified,
        "prs_para_vincular_development": {
            f"PR #{pr}": sorted(set(nums)) for pr, nums in sorted(pr_to_issues.items())
        },
    }


def imprimir_resumen_aplicado(resultado: dict) -> None:
    """Imprime el reporte final con enlaces y PRs para vincular manualmente en Development."""
    print(f"\n=== Carga completada en {resultado['repo']} (Project #{resultado['project']['number']}) ===")
    if resultado["milestones_creados"]:
        print("\nMilestones creados:")
        for m in resultado["milestones_creados"]:
            print(f"  - #{m['number']} {m['title']}")

    print("\nIssues creados:")
    for grupo in resultado["issues_creados"]:
        p = grupo["parent"]
        print(f"  - #{p['number']} {p['title']} -> {p['url']}")
        for s in grupo["sub_issues"]:
            print(f"      - #{s['number']} {s['title']} -> {s['url']}")

    print("\nVerificación final (API GraphQL):")
    for v in resultado["verificacion_final"]:
        p_status = v["project_fields"].get("Status", "?")
        print(
            f"  - #{v['number']} [{v['state']}/{v['state_reason']}] "
            f"Project Status={p_status} | milestone={v['milestone'] or '-'}"
        )

    prs = resultado["prs_para_vincular_development"]
    if prs:
        print("\n=== Vinculación manual pendiente en widget Development (PRs cerrados) ===")
        print("GitHub no expone API pública para editar Development en PRs ya mergeados.")
        print("En cada PR cerrado: barra derecha -> Development (⚙️) -> seleccionar los Issues:")
        for pr_label, issue_nums in prs.items():
            nums_txt = ", ".join(f"#{n}" for n in issue_nums)
            print(f"  - {pr_label} -> {nums_txt}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida y aplica un plan Kanban Scrum JSON en GitHub Issues y Project v2."
    )
    parser.add_argument(
        "plan_json",
        help="Ruta al archivo JSON aprobado (ej. outputs/plan_Sebastian0021.json).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida esquema y muestra el plan paso a paso sin realizar escrituras en GitHub.",
    )
    parser.add_argument(
        "--github-snapshot",
        help="JSON generado por leer_github.py para validar sin consultar la API en --dry-run.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Omite Issues cuyo título ya exista en GitHub en lugar de abortar.",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        help="No publicar comentarios automáticos de trazabilidad en los Issues creados.",
    )
    parser.add_argument(
        "--out",
        help="Ruta opcional donde guardar el reporte JSON de resultados tras aplicar.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan = cargar_plan(Path(args.plan_json))
        if args.github_snapshot:
            if not args.dry_run:
                raise ValueError("--github-snapshot solo puede usarse junto con --dry-run.")
            gh_state = json.loads(Path(args.github_snapshot).read_text(encoding="utf-8"))
        else:
            proj = plan["project"]
            gh_state = leer_github.inspeccionar_github(
                repo_slug=plan["repo"],
                project_number=int(proj["number"]),
                project_owner=proj.get("owner"),
                owner_type=proj.get("owner_type"),
                assignee=plan.get("assignee"),
                include_all_issues=True,
                max_issues=250,
            )

        errors, warnings = validar_plan(plan, gh_state, skip_existing=args.skip_existing)
        if errors:
            print("Validación fallida:", file=sys.stderr)
            for err in errors:
                print(f"  [ERROR] {err}", file=sys.stderr)
            if warnings:
                for w in warnings:
                    print(f"  [WARN] {w}", file=sys.stderr)
            return 1

        if args.dry_run:
            imprimir_dry_run(plan, gh_state, warnings)
            return 0

        resultado = aplicar_plan(
            plan, gh_state, skip_existing=args.skip_existing, no_comments=args.no_comments
        )
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        imprimir_resumen_aplicado(resultado)
        if args.out:
            print(f"\n[OK] Reporte guardado en: {args.out}")
        return 0

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
