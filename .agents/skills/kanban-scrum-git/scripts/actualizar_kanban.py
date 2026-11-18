#!/usr/bin/env python3
"""Actualiza Issues existentes y sus campos en GitHub Project v2 sin publicar comentarios.

Diseñado para reutilizar Issues previas (#1-#162): asignar desarrolladores,
agregar al Project v2 si estaban fuera (NO_PROJ), normalizar títulos/descripción,
completar campos Scrum y cerrar en orden (sub-issues antes que padres).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import aplicar_kanban  # noqa: E402
import leer_github  # noqa: E402


def cargar_updates(plan_path: Path) -> dict:
    """Carga y valida la estructura raíz del JSON de actualizaciones."""
    if not plan_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {plan_path}")
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    for key in ("repo", "project", "updates"):
        if key not in data:
            raise ValueError(f"Falta la clave obligatoria '{key}' en {plan_path}")
    if not isinstance(data["updates"], list) or not data["updates"]:
        raise ValueError("El campo 'updates' debe ser una lista no vacía.")
    return data


def validar_updates(plan: dict, gh_state: dict) -> tuple[list[str], list[str], dict[int, dict]]:
    """Valida todas las actualizaciones propuestas contra el estado real de GitHub."""
    errors: list[str] = []
    warnings: list[str] = []
    idx = aplicar_kanban.construir_indice_esquema(gh_state)

    perms = (gh_state.get("repo") or {}).get("permissions") or {}
    if not perms.get("push"):
        errors.append("El usuario autenticado en `gh` no tiene permiso 'push' sobre el repo.")

    project = idx["project"]
    if not project or not project.get("viewer_can_update"):
        errors.append("Sin permiso 'viewerCanUpdate' sobre el Project v2 destino.")

    by_number = {iss["number"]: iss for iss in gh_state.get("issues", [])}
    fields = idx["fields"]
    seen_nums: set[int] = set()
    viewer = (gh_state.get("viewer") or {}).get("login")

    # Guardrail: Warning si se intenta actualizar un lote masivo
    if len(plan["updates"]) > 5:
        warnings.append(
            f"⚠️ ALERTA DE VOLUMEN: Se detectaron {len(plan['updates'])} actualizaciones en un solo lote (> 5). Verificar que no desestabilice el tablero."
        )

    for i, upd in enumerate(plan["updates"], start=1):
        num = upd.get("number")
        ctx = f"Update[{i}] (#{num})"
        if not isinstance(num, int):
            errors.append(f"{ctx}: 'number' debe ser entero.")
            continue
        if num in seen_nums:
            errors.append(f"{ctx}: Issue #{num} repetida en el mismo JSON.")
        seen_nums.add(num)

        if num not in by_number:
            errors.append(f"{ctx}: no se encontró la Issue #{num} en el snapshot.")
            continue

        # Guardrail: Warning si la Issue pertenece a otro compañero
        current_iss = by_number[num]
        assignees = [a.get("login") for a in current_iss.get("assignees", []) if isinstance(a, dict)]
        if assignees and viewer and viewer not in assignees:
            target_assignee = upd.get("assignee")
            if target_assignee != viewer:
                warnings.append(
                    f"⚠️ SEGURIDAD ({ctx}): Pertenece a @{', @'.join(assignees)}. Modificarla afectará las tareas de tu compañero/a."
                )

        if "type" in upd and upd["type"] is not None:
            if idx["issue_types"] and upd["type"] not in idx["issue_types"]:
                errors.append(f"{ctx}: type '{upd['type']}' inválido.")

        for lbl in upd.get("labels", []):
            if lbl not in idx["labels"]:
                errors.append(f"{ctx}: label '{lbl}' no existe en el repo.")

        if "milestone" in upd and upd["milestone"] is not None:
            if upd["milestone"] not in idx["milestones"]:
                errors.append(f"{ctx}: milestone '{upd['milestone']}' no existe en el repo.")

        aplicar_kanban._validar_opcion_campo(errors, fields, "Status", upd.get("status"), ctx)
        aplicar_kanban._validar_opcion_campo(errors, fields, "Priority", upd.get("priority"), ctx)
        aplicar_kanban._validar_opcion_campo(errors, fields, "Size", upd.get("size"), ctx)

        if "estimate" in upd and upd["estimate"] is not None:
            if not isinstance(upd["estimate"], (int, float)):
                errors.append(f"{ctx}: 'estimate' debe ser numérico.")

        for dkey in ("start_date", "target_date"):
            if dkey in upd and upd[dkey] is not None:
                if not aplicar_kanban.DATE_RE.match(str(upd[dkey])):
                    errors.append(f"{ctx}: '{dkey}' inválido ({upd[dkey]!r}).")

        if "state" in upd and upd["state"] not in ("open", "closed"):
            errors.append(f"{ctx}: 'state' debe ser 'open' o 'closed'.")
        if "state_reason" in upd and upd["state_reason"] not in ("completed", "not_planned", "reopened"):
            errors.append(f"{ctx}: 'state_reason' inválido ({upd['state_reason']!r}).")

        for sub_num in upd.get("sub_issues", []):
            if not isinstance(sub_num, int) or sub_num not in by_number:
                errors.append(f"{ctx}: sub_issue #{sub_num} no existe en el snapshot.")

    return errors, warnings, by_number


def _ordenar_subissues_primero(updates: list[dict], by_number: dict[int, dict]) -> list[dict]:
    """Ordena para procesar sub-issues antes que Issues padre."""
    declared_children = {s for u in updates for s in u.get("sub_issues", [])}
    return sorted(
        updates,
        key=lambda u: (
            1 if u.get("sub_issues") else 0,
            0 if (by_number[u["number"]].get("parent_number") or u["number"] in declared_children) else 1,
            u["number"],
        ),
    )


def imprimir_dry_run(plan: dict, gh_state: dict, by_number: dict[int, dict]) -> None:
    """Muestra la simulación detallada sin realizar escrituras en GitHub."""
    project = gh_state["project"]
    ordered = _ordenar_subissues_primero(plan["updates"], by_number)
    print(f"=== DRY-RUN ACTUALIZACIÓN | Repo: {plan['repo']} | Project #{project['number']} ===")
    print(f"Total Issues a actualizar: {len(ordered)} (sin publicar comentarios)\n")

    for upd in ordered:
        num = upd["number"]
        cur = by_number[num]
        in_proj = any(
            pi.get("project_number") == project["number"] for pi in cur.get("project_items", [])
        )
        changes: list[str] = []
        if "title" in upd:
            changes.append(f"title -> {upd['title']!r}")
        if "body" in upd:
            changes.append("body -> (actualizado)")
        if "assignees" in upd:
            changes.append(f"assignees -> {upd['assignees']}")
        if "labels" in upd:
            changes.append(f"labels -> {upd['labels']}")
        if "type" in upd:
            changes.append(f"type -> {upd['type']}")
        if "milestone" in upd:
            changes.append(f"milestone -> {upd['milestone']}")
        if not in_proj and (upd.get("add_to_project") or any(k in upd for k in ("status", "priority", "size", "estimate", "start_date", "target_date"))):
            changes.append("+ agregar a Project #4")
        if in_proj and upd.get("remove_from_project"):
            changes.append("- quitar de Project #4")
        if upd.get("sub_issues"):
            changes.append(f"+ enlazar sub-issues {upd['sub_issues']}")
        for k in ("priority", "size", "estimate", "start_date", "target_date", "status"):
            if k in upd:
                changes.append(f"{k}={upd[k]}")
        if "state" in upd:
            changes.append(f"state={upd['state']} ({upd.get('state_reason', '-')})")
        if upd.get("pr_referencia") or upd.get("commits") or upd.get("comment"):
            changes.append("+ comentario trazabilidad (si --with-comments)")

        print(f"  - #{num} [{cur['state']}] ({cur['title']}):")
        print(f"      {', '.join(changes) if changes else '(sin cambios)'}")


def aplicar_updates(
    plan: dict, gh_state: dict, by_number: dict[int, dict], with_comments: bool = False
) -> dict:
    """Aplica las actualizaciones en GitHub respetando orden anti-automatizaciones."""
    owner, repo = leer_github.parsear_owner_repo(plan["repo"])
    idx = aplicar_kanban.construir_indice_esquema(gh_state)
    milestone_map = idx["milestones"]
    fields = idx["fields"]
    project = idx["project"]
    project_id = project["id"]

    ordered = _ordenar_subissues_primero(plan["updates"], by_number)
    tracked: dict[int, tuple[str, dict]] = {}
    node_ids: list[str] = []

    for upd in ordered:
        num = upd["number"]
        cur = by_number[num]
        node_ids.append(cur["node_id"])

        # 1. PATCH de metadatos REST (sin state todavía)
        patch_payload: dict[str, object] = {}
        if "title" in upd:
            patch_payload["title"] = upd["title"]
        if "body" in upd:
            patch_payload["body"] = upd["body"]
        if "assignees" in upd:
            patch_payload["assignees"] = list(upd["assignees"])
        if "labels" in upd:
            patch_payload["labels"] = list(upd["labels"])
        if "type" in upd:
            patch_payload["type"] = upd["type"]
        if "milestone" in upd:
            patch_payload["milestone"] = (
                milestone_map[upd["milestone"]] if upd["milestone"] else None
            )

        if patch_payload:
            aplicar_kanban.gh_rest_write(
                "PATCH", f"repos/{owner}/{repo}/issues/{num}", patch_payload
            )

        # 2. Vincular al Project v2 si hace falta
        proj_item_id = None
        for pi in cur.get("project_items", []):
            if pi.get("project_number") == project["number"]:
                proj_item_id = pi["item_id"]
                break

        needs_project = bool(
            upd.get("add_to_project")
            or any(
                k in upd
                for k in ("status", "priority", "size", "estimate", "start_date", "target_date")
            )
        )
        if proj_item_id and upd.get("remove_from_project"):
            mutation = """
            mutation($projectId: ID!, $itemId: ID!) {
              deleteProjectV2Item(input: {projectId: $projectId, itemId: $itemId}) {
                deletedItemId
              }
            }
            """
            aplicar_kanban.gh_graphql_write(
                mutation, {"projectId": project_id, "itemId": proj_item_id}
            )
            proj_item_id = None
        elif not proj_item_id and needs_project:
            proj_item_id = aplicar_kanban.agregar_item_project(project_id, cur["node_id"])

        # 3. Setear metadatos del Project v2 (sin Status aún)
        if proj_item_id:
            aplicar_kanban.aplicar_metadatos_project(project_id, proj_item_id, upd, fields)
            if "status" in upd:
                tracked[num] = (proj_item_id, upd)

        # 3b. Enlazar sub-issues existentes antes de setear Status=Done en el padre
        existing_subs = {s["number"] for s in cur.get("sub_issues", [])}
        for sub_num in upd.get("sub_issues", []):
            if sub_num in existing_subs:
                continue
            sub_db_id = by_number[sub_num]["database_id"]
            try:
                aplicar_kanban.vincular_sub_issue(owner, repo, num, sub_db_id)
            except RuntimeError as exc:
                if "422" not in str(exc) and "already" not in str(exc).lower():
                    raise

        # 3c. Comentario de trazabilidad opcional (--with-comments)
        if with_comments:
            comment_body = upd.get("comment") or aplicar_kanban.construir_comentario_trazabilidad(upd)
            if comment_body:
                existing_comments = leer_github.gh_rest(
                    f"repos/{owner}/{repo}/issues/{num}/comments?per_page=100"
                )
                already_posted = any(
                    (c.get("body") or "").strip() == comment_body.strip()
                    for c in (existing_comments if isinstance(existing_comments, list) else [])
                )
                if not already_posted:
                    aplicar_kanban.publicar_comentario(owner, repo, num, comment_body)

        # 4. Setear Status final en Project v2
        if proj_item_id and "status" in upd and upd["status"] is not None:
            opt_id = fields["Status"]["options"][str(upd["status"])]
            aplicar_kanban.actualizar_campo_project(
                project_id,
                proj_item_id,
                fields["Status"]["id"],
                {"singleSelectOptionId": opt_id},
            )

        # 5. Actualizar estado open/closed si se solicitó (evitando HTTP 422 si ya está cerrado igual)
        if "state" in upd:
            target_state = upd["state"]
            target_reason = upd.get("state_reason")
            current_live = leer_github.gh_rest(f"repos/{owner}/{repo}/issues/{num}")
            already_same = current_live.get("state") == target_state and (
                target_reason is None or current_live.get("state_reason") == target_reason
            )
            if not already_same:
                close_payload: dict[str, object] = {"state": target_state}
                if target_reason:
                    close_payload["state_reason"] = target_reason
                try:
                    aplicar_kanban.gh_rest_write(
                        "PATCH", f"repos/{owner}/{repo}/issues/{num}", close_payload
                    )
                except RuntimeError:
                    recheck = leer_github.gh_rest(f"repos/{owner}/{repo}/issues/{num}")
                    if not (
                        recheck.get("state") == target_state
                        and (target_reason is None or recheck.get("state_reason") == target_reason)
                    ):
                        raise

    # 6. Verificación final GraphQL + autocorrección puntual de Status si una automatización lo revirtió
    verified = aplicar_kanban.verificar_estado_final(node_ids, project["number"])
    reapplied = False
    for v in verified:
        num = v["number"]
        if num in tracked:
            p_item_id, upd_cfg = tracked[num]
            expected_status = upd_cfg.get("status")
            if expected_status and v["project_fields"].get("Status") != expected_status:
                opt_id = fields["Status"]["options"][str(expected_status)]
                aplicar_kanban.actualizar_campo_project(
                    project_id,
                    p_item_id,
                    fields["Status"]["id"],
                    {"singleSelectOptionId": opt_id},
                )
                reapplied = True
    if reapplied:
        verified = aplicar_kanban.verificar_estado_final(node_ids, project["number"])

    return {
        "repo": plan["repo"],
        "project": {"number": project["number"], "title": project["title"]},
        "total_actualizadas": len(ordered),
        "verificacion_final": verified,
    }


def construir_auditoria_omitidas(plan: dict, gh_state: dict) -> dict:
    """Detecta Issues relevantes no incluidas en el lote y asocia su razón declarada."""
    updated_nums = {u["number"] for u in plan["updates"]}
    reasons_cfg = {int(k): v for k, v in (plan.get("omitted_reasons") or {}).items()}
    omitidas: list[dict] = []

    for iss in sorted(gh_state.get("issues", []), key=lambda x: x["number"]):
        num = iss["number"]
        if num in updated_nums:
            continue
        no_assignee = not iss.get("assignees")
        is_open = iss.get("state") == "OPEN"
        if is_open or no_assignee or num in reasons_cfg:
            omitidas.append(
                {
                    "number": num,
                    "state": iss.get("state"),
                    "assignees": iss.get("assignees", []),
                    "title": iss.get("title"),
                    "reason": reasons_cfg.get(num, "SIN_RAZON_DECLARADA"),
                }
            )
    return {
        "total_omitidas_relevantes": len(omitidas),
        "sin_razon_declarada": sum(1 for o in omitidas if o["reason"] == "SIN_RAZON_DECLARADA"),
        "items": omitidas,
    }


def imprimir_auditoria_omitidas(auditoria: dict) -> None:
    """Imprime las Issues omitidas (OPEN o sin assignee) y su razón explícita."""
    print(
        f"\n=== Auditoría de Issues no modificadas en este paso "
        f"(total: {auditoria['total_omitidas_relevantes']} | sin razón: {auditoria['sin_razon_declarada']}) ==="
    )
    for item in auditoria["items"]:
        ass = ",".join(item["assignees"]) or "-"
        print(
            f"  - #{item['number']:>3} [{item['state']}] ass={ass} | {item['reason']} | {item['title']}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Actualiza Issues existentes y Project v2 sin publicar comentarios."
    )
    parser.add_argument("updates_json", help="JSON con lista de actualizaciones.")
    parser.add_argument("--dry-run", action="store_true", help="Simula sin mutar GitHub.")
    parser.add_argument(
        "--github-snapshot",
        help="Snapshot JSON generado por leer_github.py --all-issues para validar offline en --dry-run.",
    )
    parser.add_argument(
        "--with-comments",
        action="store_true",
        help="Publica comentarios de trazabilidad Git si pr_referencia/commits/comment están presentes.",
    )
    parser.add_argument(
        "--no-audit",
        action="store_true",
        help="Omitir el listado detallado de auditoría en stdout (útil en pruebas unitarias de 1 Issue).",
    )
    parser.add_argument("--out", help="Ruta opcional para guardar resultado JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan = cargar_updates(Path(args.updates_json))
        if args.github_snapshot:
            if not args.dry_run:
                raise ValueError("--github-snapshot solo puede usarse junto con --dry-run.")
            gh_state = json.loads(Path(args.github_snapshot).read_text(encoding="utf-8"))
        else:
            proj = plan["project"]
            if isinstance(proj, int):
                p_num = proj
                p_owner = None
                p_type = None
            else:
                p_num = int(proj["number"])
                p_owner = proj.get("owner")
                p_type = proj.get("owner_type")
            gh_state = leer_github.inspeccionar_github(
                repo_slug=plan["repo"],
                project_number=p_num,
                project_owner=p_owner,
                owner_type=p_type,
                assignee=None,
                include_all_issues=True,
                max_issues=300,
            )

        errors, warnings, by_number = validar_updates(plan, gh_state)
        if errors:
            print("Validación fallida:", file=sys.stderr)
            for err in errors:
                print(f"  [ERROR] {err}", file=sys.stderr)
            return 1
        for w in warnings:
            print(f"  [WARN] {w}")

        auditoria = construir_auditoria_omitidas(plan, gh_state)
        if args.dry_run:
            imprimir_dry_run(plan, gh_state, by_number)
            if not args.no_audit:
                imprimir_auditoria_omitidas(auditoria)
            return 0

        resultado = aplicar_updates(
            plan, gh_state, by_number, with_comments=args.with_comments
        )
        resultado["auditoria_omitidas"] = auditoria
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        print(f"\n=== Actualización completada ({resultado['total_actualizadas']} Issues) ===")
        for v in resultado["verificacion_final"]:
            ps = v["project_fields"].get("Status", "NO_PROJ")
            sub_txt = f" | sub_issues={v['sub_issues_count']}" if v.get("sub_issues_count") else ""
            par_txt = f" | sub_de=#{v['parent_number']}" if v.get("parent_number") else ""
            print(f"  - #{v['number']} [{v['state']}/{v['state_reason']}] Project={ps}{sub_txt}{par_txt} | {v['title']}")
        if not args.no_audit:
            imprimir_auditoria_omitidas(auditoria)
        if args.out:
            print(f"\n[OK] Reporte guardado en: {args.out}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
