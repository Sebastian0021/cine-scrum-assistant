#!/usr/bin/env python3
"""Inspección en solo lectura de un repositorio y Project v2 en GitHub vía `gh` CLI.

Consulta usuario autenticado, permisos sobre el repositorio, Milestones, Labels,
Issue Types, esquema completo de campos del Project v2 e Issues existentes
para evitar duplicados y validar nombres/IDs antes de aplicar cambios.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_FIELDS_FRAGMENT = """
  id
  number
  title
  url
  closed
  viewerCanUpdate
  fields(first: 50) {
    nodes {
      __typename
      ... on ProjectV2Field {
        id
        name
        dataType
      }
      ... on ProjectV2SingleSelectField {
        id
        name
        dataType
        options {
          id
          name
          description
          color
        }
      }
      ... on ProjectV2IterationField {
        id
        name
        dataType
        configuration {
          iterations {
            id
            title
            startDate
            duration
          }
        }
      }
    }
  }
"""


def run_gh(args: list[str], stdin_data: str | None = None) -> str:
    """Ejecuta `gh` en modo solo lectura y devuelve stdout."""
    cmd = ["gh", *args]
    res = subprocess.run(cmd, input=stdin_data, capture_output=True, text=True)
    if res.returncode != 0:
        err = res.stderr.strip() or res.stdout.strip()
        raise RuntimeError(f"Error ejecutando {' '.join(cmd)}: {err}")
    return res.stdout


def gh_rest(endpoint: str, paginate: bool = False) -> dict | list:
    """Realiza una consulta GET REST vía `gh api`."""
    args = ["api", endpoint]
    if paginate:
        args.extend(["--paginate", "--slurp"])
    raw = run_gh(args)
    if not raw.strip():
        return []
    data = json.loads(raw)
    if paginate and isinstance(data, list) and data and isinstance(data[0], list):
        flattened: list = []
        for page in data:
            flattened.extend(page)
        return flattened
    return data


def gh_graphql(query: str, variables: dict | None = None) -> dict:
    """Realiza una consulta GraphQL vía `gh api graphql --input -`."""
    payload = {"query": query, "variables": variables or {}}
    raw = run_gh(["api", "graphql", "--input", "-"], stdin_data=json.dumps(payload))
    data = json.loads(raw)
    if data.get("errors"):
        messages = "; ".join(err.get("message", str(err)) for err in data["errors"])
        raise RuntimeError(f"Error GraphQL: {messages}")
    return data.get("data", {})


def parsear_owner_repo(repo_slug: str) -> tuple[str, str]:
    """Separa `owner/repo` validando el formato."""
    if "/" not in repo_slug:
        raise ValueError(f"Formato inválido para --repo (se esperaba owner/repo): {repo_slug}")
    owner, repo = repo_slug.split("/", 1)
    if not owner or not repo:
        raise ValueError(f"Formato inválido para --repo: {repo_slug}")
    return owner.strip(), repo.strip()


def obtener_usuario_y_permisos(owner: str, repo: str) -> tuple[dict, dict]:
    """Consulta el usuario autenticado en `gh` y sus permisos sobre el repositorio."""
    user_data = gh_rest("user")
    repo_data = gh_rest(f"repos/{owner}/{repo}")
    viewer = {
        "login": user_data.get("login"),
        "name": user_data.get("name"),
        "id": user_data.get("id"),
    }
    repo_info = {
        "full_name": repo_data.get("full_name"),
        "id": repo_data.get("id"),
        "node_id": repo_data.get("node_id"),
        "private": repo_data.get("private"),
        "default_branch": repo_data.get("default_branch"),
        "owner_type": (repo_data.get("owner") or {}).get("type"),
        "permissions": repo_data.get("permissions", {}),
        "html_url": repo_data.get("html_url"),
    }
    return viewer, repo_info


def obtener_milestones(owner: str, repo: str) -> list[dict]:
    """Lista todos los Milestones (abiertos y cerrados) del repositorio."""
    raw = gh_rest(f"repos/{owner}/{repo}/milestones?state=all&per_page=100", paginate=True)
    milestones = [
        {
            "number": m.get("number"),
            "title": m.get("title"),
            "description": m.get("description") or "",
            "state": m.get("state"),
            "due_on": (m.get("due_on") or "")[:10] or None,
            "open_issues": m.get("open_issues", 0),
            "closed_issues": m.get("closed_issues", 0),
        }
        for m in raw
    ]
    return sorted(milestones, key=lambda m: m["number"] or 0)


def obtener_labels(owner: str, repo: str) -> list[dict]:
    """Lista todas las Labels disponibles en el repositorio."""
    raw = gh_rest(f"repos/{owner}/{repo}/labels?per_page=100", paginate=True)
    labels = [
        {
            "name": lbl.get("name"),
            "color": lbl.get("color"),
            "description": lbl.get("description") or "",
        }
        for lbl in raw
    ]
    return sorted(labels, key=lambda lbl: (lbl["name"] or "").lower())


def obtener_issue_types(owner: str, repo: str) -> list[dict]:
    """Obtiene los Issue Types configurados en el repositorio vía GraphQL."""
    query = """
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        issueTypes(first: 50) {
          nodes {
            id
            name
            description
            isEnabled
          }
        }
      }
    }
    """
    try:
        data = gh_graphql(query, {"owner": owner, "repo": repo})
    except RuntimeError:
        return []

    nodes = ((data.get("repository") or {}).get("issueTypes") or {}).get("nodes") or []
    return [
        {
            "id": node.get("id"),
            "name": node.get("name"),
            "description": node.get("description") or "",
            "is_enabled": node.get("isEnabled", True),
        }
        for node in nodes
    ]


def obtener_projects_vinculados(owner: str, repo: str) -> list[dict]:
    """Lista los Projects v2 vinculados directamente al repositorio."""
    query = """
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        projectsV2(first: 20) {
          nodes {
            id
            number
            title
            url
            closed
            viewerCanUpdate
            owner {
              __typename
              ... on User { login }
              ... on Organization { login }
            }
          }
        }
      }
    }
    """
    try:
        data = gh_graphql(query, {"owner": owner, "repo": repo})
    except RuntimeError:
        return []

    nodes = ((data.get("repository") or {}).get("projectsV2") or {}).get("nodes") or []
    result: list[dict] = []
    for node in nodes:
        owner_node = node.get("owner") or {}
        result.append(
            {
                "id": node.get("id"),
                "number": node.get("number"),
                "title": node.get("title"),
                "url": node.get("url"),
                "closed": node.get("closed"),
                "viewer_can_update": node.get("viewerCanUpdate"),
                "owner_login": owner_node.get("login"),
                "owner_type": (owner_node.get("__typename") or "").lower() or None,
            }
        )
    return result


def normalizar_campo_project(node: dict) -> dict:
    """Normaliza un nodo de campo de ProjectV2 (single select, number, date, iteration)."""
    field = {
        "id": node.get("id"),
        "name": node.get("name"),
        "data_type": node.get("dataType"),
        "typename": node.get("__typename"),
    }
    if "options" in node:
        field["options"] = [
            {
                "id": opt.get("id"),
                "name": opt.get("name"),
                "description": opt.get("description") or "",
                "color": opt.get("color"),
            }
            for opt in (node.get("options") or [])
        ]
    if "configuration" in node and node["configuration"]:
        field["iterations"] = node["configuration"].get("iterations") or []
    return field


def consultar_project_por_tipo(
    project_owner: str, project_number: int, owner_type: str
) -> dict | None:
    """Consulta un Project v2 bajo `user` o `organization`."""
    root_field = "user" if owner_type == "user" else "organization"
    query = f"""
    query($owner: String!, $number: Int!) {{
      {root_field}(login: $owner) {{
        projectV2(number: $number) {{
          {PROJECT_FIELDS_FRAGMENT}
        }}
      }}
    }}
    """
    data = gh_graphql(query, {"owner": project_owner, "number": project_number})
    holder = data.get(root_field)
    if not holder:
        return None
    return holder.get("projectV2")


def obtener_esquema_project(
    project_owner: str, project_number: int, owner_type: str | None
) -> dict:
    """Obtiene el esquema completo del Project v2 autodetectando user/organization si falta."""
    types_to_try = [owner_type] if owner_type else ["user", "organization"]
    project_node = None
    resolved_type = None
    last_error = None

    for candidate_type in types_to_try:
        try:
            node = consultar_project_por_tipo(project_owner, project_number, candidate_type)
            if node:
                project_node = node
                resolved_type = candidate_type
                break
        except RuntimeError as exc:
            last_error = exc

    if not project_node:
        detail = f" ({last_error})" if last_error else ""
        raise RuntimeError(
            f"No se pudo encontrar el Project #{project_number} para '{project_owner}'{detail}."
        )

    fields_nodes = (project_node.get("fields") or {}).get("nodes") or []
    fields = [normalizar_campo_project(n) for n in fields_nodes if n]
    return {
        "id": project_node.get("id"),
        "number": project_node.get("number"),
        "title": project_node.get("title"),
        "url": project_node.get("url"),
        "closed": project_node.get("closed"),
        "viewer_can_update": project_node.get("viewerCanUpdate"),
        "owner": project_owner,
        "owner_type": resolved_type,
        "fields": fields,
    }


def _extraer_project_items(node: dict) -> list[dict]:
    items: list[dict] = []
    for pitem in (node.get("projectItems") or {}).get("nodes") or []:
        proj = pitem.get("project") or {}
        field_values: dict[str, object] = {}
        for fv in (pitem.get("fieldValues") or {}).get("nodes") or []:
            field_info = fv.get("field") or {}
            fname = field_info.get("name")
            if not fname:
                continue
            if "name" in fv:
                field_values[fname] = fv.get("name")
            elif "text" in fv:
                field_values[fname] = fv.get("text")
            elif "number" in fv:
                field_values[fname] = fv.get("number")
            elif "date" in fv:
                field_values[fname] = fv.get("date")
            elif "title" in fv:
                field_values[fname] = fv.get("title")
        items.append(
            {
                "item_id": pitem.get("id"),
                "project_id": proj.get("id"),
                "project_number": proj.get("number"),
                "project_title": proj.get("title"),
                "fields": field_values,
            }
        )
    return items


def obtener_issues_graphql(
    owner: str, repo: str, assignee: str | None, max_issues: int = 200
) -> list[dict]:
    """Obtiene Issues del repositorio con type, sub-issues y valores en Project v2."""
    query_with_hierarchy = """
    query($owner: String!, $repo: String!, $cursor: String, $filter: IssueFilters) {
      repository(owner: $owner, name: $repo) {
        issues(first: 50, after: $cursor, filterBy: $filter, orderBy: {field: CREATED_AT, direction: DESC}) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            id
            databaseId
            number
            title
            body
            state
            stateReason
            url
            createdAt
            closedAt
            author { login }
            issueType { id name }
            milestone { number title }
            labels(first: 20) { nodes { name } }
            assignees(first: 10) { nodes { login } }
            parent { number title state }
            subIssues(first: 50) { nodes { number title state } }
            projectItems(first: 10) {
              nodes {
                id
                project { id number title }
                fieldValues(first: 20) {
                  nodes {
                    __typename
                    ... on ProjectV2ItemFieldSingleSelectValue {
                      name
                      field { ... on ProjectV2FieldCommon { name } }
                    }
                    ... on ProjectV2ItemFieldTextValue {
                      text
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
                    ... on ProjectV2ItemFieldIterationValue {
                      title
                      field { ... on ProjectV2FieldCommon { name } }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    query_fallback = query_with_hierarchy.replace(
        "parent { number title state }\n            subIssues(first: 50) { nodes { number title state } }\n",
        "",
    )

    issue_filter = {"assignee": assignee} if assignee else {}
    collected: list[dict] = []
    cursor: str | None = None
    active_query = query_with_hierarchy

    while len(collected) < max_issues:
        variables = {
            "owner": owner,
            "repo": repo,
            "cursor": cursor,
            "filter": issue_filter,
        }
        try:
            data = gh_graphql(active_query, variables)
        except RuntimeError as exc:
            if active_query == query_with_hierarchy and ("parent" in str(exc) or "subIssues" in str(exc)):
                active_query = query_fallback
                data = gh_graphql(active_query, variables)
            else:
                raise

        issues_conn = (data.get("repository") or {}).get("issues") or {}
        nodes = issues_conn.get("nodes") or []
        for node in nodes:
            parent_node = node.get("parent")
            sub_nodes = (node.get("subIssues") or {}).get("nodes") or []
            collected.append(
                {
                    "number": node.get("number"),
                    "database_id": node.get("databaseId"),
                    "node_id": node.get("id"),
                    "title": node.get("title"),
                    "body": node.get("body") or "",
                    "author": (node.get("author") or {}).get("login"),
                    "state": node.get("state"),
                    "state_reason": node.get("stateReason"),
                    "url": node.get("url"),
                    "created_at": (node.get("createdAt") or "")[:10] or None,
                    "closed_at": (node.get("closedAt") or "")[:10] or None,
                    "type": (node.get("issueType") or {}).get("name"),
                    "milestone": (node.get("milestone") or {}).get("title"),
                    "labels": [l.get("name") for l in (node.get("labels") or {}).get("nodes") or []],
                    "assignees": [a.get("login") for a in (node.get("assignees") or {}).get("nodes") or []],
                    "parent_number": parent_node.get("number") if parent_node else None,
                    "sub_issues": [
                        {
                            "number": s.get("number"),
                            "title": s.get("title"),
                            "state": s.get("state"),
                        }
                        for s in sub_nodes
                    ],
                    "project_items": _extraer_project_items(node),
                }
            )
            if len(collected) >= max_issues:
                break

        page_info = issues_conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    return collected


def inspeccionar_github(
    repo_slug: str,
    project_number: int | None,
    project_owner: str | None,
    owner_type: str | None,
    assignee: str | None,
    include_all_issues: bool,
    max_issues: int,
) -> dict:
    """Reúne en solo lectura todo el esquema del repositorio y Project v2."""
    owner, repo = parsear_owner_repo(repo_slug)
    viewer, repo_info = obtener_usuario_y_permisos(owner, repo)
    milestones = obtener_milestones(owner, repo)
    labels = obtener_labels(owner, repo)
    issue_types = obtener_issue_types(owner, repo)
    linked_projects = obtener_projects_vinculados(owner, repo)

    project_schema = None
    if project_number is not None:
        effective_owner = project_owner or owner
        effective_type = owner_type
        if not effective_type and effective_owner.lower() == owner.lower():
            repo_owner_type = (repo_info.get("owner_type") or "").lower()
            if repo_owner_type in ("user", "organization"):
                effective_type = repo_owner_type
        project_schema = obtener_esquema_project(effective_owner, project_number, effective_type)

    issue_filter_assignee = None if include_all_issues else assignee
    issues = obtener_issues_graphql(
        owner=owner,
        repo=repo,
        assignee=issue_filter_assignee,
        max_issues=max_issues,
    )

    return {
        "viewer": viewer,
        "repo": repo_info,
        "issue_types": issue_types,
        "milestones": milestones,
        "labels": labels,
        "linked_projects": linked_projects,
        "project": project_schema,
        "issues_filter": {
            "assignee": issue_filter_assignee,
            "all_issues": include_all_issues,
            "count": len(issues),
        },
        "issues": issues,
    }


def formatear_reporte_texto(reporte: dict) -> str:
    """Genera un resumen legible en texto del estado de GitHub y del Project v2."""
    lines: list[str] = []
    viewer = reporte["viewer"]
    repo = reporte["repo"]
    perms = repo.get("permissions") or {}

    lines.append(f"=== Repositorio GitHub: {repo['full_name']} ===")
    lines.append(f"Usuario gh autenticado: {viewer['login']} ({viewer.get('name') or 'sin nombre'})")
    lines.append(
        "Permisos en repo: "
        + ", ".join(f"{k}={v}" for k, v in perms.items())
    )

    lines.append("\nIssue Types activos:")
    if not reporte["issue_types"]:
        lines.append("  (ninguno o no habilitados)")
    for it in reporte["issue_types"]:
        estado = "activo" if it["is_enabled"] else "deshabilitado"
        lines.append(f"  - {it['name']} (id: {it['id']}, {estado})")

    lines.append("\nMilestones:")
    if not reporte["milestones"]:
        lines.append("  (ninguno)")
    for m in reporte["milestones"]:
        due = f" | due: {m['due_on']}" if m["due_on"] else ""
        lines.append(
            f"  - #{m['number']} {m['title']} [{m['state']}] "
            f"(open: {m['open_issues']}, closed: {m['closed_issues']}{due})"
        )

    lines.append("\nLabels:")
    if not reporte["labels"]:
        lines.append("  (ninguna)")
    else:
        lines.append("  " + ", ".join(l["name"] for l in reporte["labels"]))

    if reporte["project"]:
        p = reporte["project"]
        lines.append(f"\n=== Project v2 #{p['number']}: {p['title']} ===")
        lines.append(
            f"ID: {p['id']} | owner: {p['owner']} ({p['owner_type']}) "
            f"| viewerCanUpdate: {p['viewer_can_update']} | url: {p['url']}"
        )
        lines.append("Campos del Project:")
        for f in p["fields"]:
            if "options" in f:
                opts = ", ".join(f"{o['name']} ({o['id']})" for o in f["options"])
                lines.append(f"  - {f['name']} [{f['data_type']}] (id: {f['id']}): {opts}")
            elif "iterations" in f:
                its = ", ".join(i["title"] for i in f["iterations"])
                lines.append(f"  - {f['name']} [{f['data_type']}] (id: {f['id']}): {its}")
            else:
                lines.append(f"  - {f['name']} [{f['data_type']}] (id: {f['id']})")
    elif reporte["linked_projects"]:
        lines.append("\nProjects vinculados al repositorio:")
        for lp in reporte["linked_projects"]:
            lines.append(
                f"  - #{lp['number']} {lp['title']} (owner: {lp['owner_login']}, id: {lp['id']})"
            )

    flt = reporte["issues_filter"]
    scope_txt = "todos" if flt["all_issues"] else f"assignee={flt['assignee'] or 'todos'}"
    lines.append(f"\n=== Issues existentes ({scope_txt} | total: {flt['count']}) ===")
    if not reporte["issues"]:
        lines.append("  (ninguno)")
    for iss in reporte["issues"]:
        parent_txt = f" [sub-issue de #{iss['parent_number']}]" if iss["parent_number"] else ""
        subs_txt = f" [sub-issues: {len(iss['sub_issues'])}]" if iss["sub_issues"] else ""
        proj_txt = ""
        if iss["project_items"]:
            statuses = [
                f"P#{pi['project_number']}:{pi['fields'].get('Status', '?')}"
                for pi in iss["project_items"]
            ]
            proj_txt = f" | {', '.join(statuses)}"
        lines.append(
            f"  - #{iss['number']} [{iss['state']}] ({iss['type'] or 'Sin tipo'}) "
            f"{iss['title']} | milestone: {iss['milestone'] or '-'}{parent_txt}{subs_txt}{proj_txt}"
        )

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consulta en solo lectura repositorio, esquema de Project v2 e Issues vía gh CLI."
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Repositorio destino en formato owner/repo (ej. fcamporaa/IDS_ProyectoFinal_equipo10).",
    )
    parser.add_argument(
        "--project",
        type=int,
        default=None,
        help="Número del GitHub Project v2 (ej. 4).",
    )
    parser.add_argument(
        "--project-owner",
        default=None,
        help="Owner del Project v2 si difiere del owner del repo.",
    )
    parser.add_argument(
        "--owner-type",
        choices=("user", "organization"),
        default=None,
        help="Tipo de owner del Project v2 (por defecto se autodetecta).",
    )
    parser.add_argument(
        "--assignee",
        default=None,
        help="Filtrar Issues existentes por usuario asignado (ej. Sebastian0021).",
    )
    parser.add_argument(
        "--all-issues",
        action="store_true",
        help="Traer todos los Issues del repo sin filtrar por assignee.",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=200,
        help="Máximo de Issues a consultar (por defecto: 200).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Formato de salida por stdout (text o json).",
    )
    parser.add_argument(
        "--out",
        help="Ruta opcional donde guardar el JSON completo (ej. outputs/github_Sebastian0021.json).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        reporte = inspeccionar_github(
            repo_slug=args.repo,
            project_number=args.project,
            project_owner=args.project_owner,
            owner_type=args.owner_type,
            assignee=args.assignee,
            include_all_issues=args.all_issues,
            max_issues=args.max_issues,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(reporte, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(reporte, indent=2, ensure_ascii=False))
    else:
        print(formatear_reporte_texto(reporte))
        if args.out:
            print(f"\n[OK] JSON completo guardado en: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

