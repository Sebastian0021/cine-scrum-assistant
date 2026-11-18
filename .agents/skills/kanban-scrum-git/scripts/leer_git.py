#!/usr/bin/env python3
"""Inspección en solo lectura del historial Git de un repositorio y un desarrollador.

Separa estrictamente commits y PRs propios de PRs ajenos mergeados o conflictos
resueltos por el desarrollador, detecta múltiples alias (nombre/email) y extrae
fechas reales y estadísticas de archivos modificados.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"

PR_FROM_RE = re.compile(r"^Merge pull request #(\d+) from ([^/\s]+)/(\S+)")
PR_SIMPLE_RE = re.compile(r"^Merge pull request #(\d+)\b")
BRANCH_MERGE_RE = re.compile(r"^Merge (?:remote-tracking )?branch '([^']+)'(?: into (\S+))?")
GITHUB_REMOTE_RE = re.compile(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$")

DEFAULT_INTEGRATION_BRANCHES = ("develop", "main", "master")
SYNC_BRANCH_NAMES = {"develop", "main", "master", "origin/develop", "origin/main", "origin/master"}


def run_git(repo_path: Path, args: list[str]) -> str:
    """Ejecuta un comando git en modo solo lectura sobre repo_path."""
    cmd = ["git", "-C", str(repo_path), *args]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Error ejecutando {' '.join(cmd)}: {res.stderr.strip()}")
    return res.stdout


def validar_repo(repo_path: Path) -> Path:
    """Verifica que repo_path sea un repositorio Git válido."""
    resolved = repo_path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"No existe la ruta del repositorio: {resolved}")
    out = run_git(resolved, ["rev-parse", "--is-inside-work-tree"]).strip()
    if out != "true":
        raise RuntimeError(f"La ruta no es un working tree de Git: {resolved}")
    return resolved


def parsear_remote_github(remote_url: str) -> str | None:
    """Extrae owner/repo si el remoto apunta a GitHub."""
    match = GITHUB_REMOTE_RE.search(remote_url.strip())
    return match.group(1) if match else None


def ref_existe(repo_path: Path, ref: str) -> bool:
    """Comprueba si una referencia Git existe."""
    res = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
    )
    return res.returncode == 0


def obtener_info_repo(repo_path: Path) -> dict:
    """Obtiene metadatos generales del repositorio (remoto, HEAD, ramas)."""
    try:
        remote_url = run_git(repo_path, ["remote", "get-url", "origin"]).strip()
    except RuntimeError:
        remote_url = ""

    head_branch = run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    head_sha = run_git(repo_path, ["rev-parse", "--short", "HEAD"]).strip()

    refs_raw = run_git(
        repo_path,
        [
            "for-each-ref",
            "--sort=-committerdate",
            "--format=%(refname:short)|%(objectname:short)|%(committerdate:short)|%(refname)",
            "refs/heads",
            "refs/remotes",
        ],
    )
    ramas_locales: list[dict] = []
    ramas_remotas: list[dict] = []
    for line in refs_raw.splitlines():
        if not line.strip():
            continue
        short_name, sha, date_str, full_ref = line.split("|", 3)
        if short_name.endswith("/HEAD"):
            continue
        entry = {"name": short_name, "sha": sha, "last_commit_date": date_str}
        if full_ref.startswith("refs/heads/"):
            ramas_locales.append(entry)
        else:
            ramas_remotas.append(entry)

    return {
        "path": str(repo_path),
        "remote_url": remote_url,
        "github_repo": parsear_remote_github(remote_url),
        "head_branch": head_branch,
        "head_sha": head_sha,
        "local_branches": ramas_locales,
        "remote_branches": ramas_remotas,
    }


def cargar_commits_dag(repo_path: Path) -> tuple[dict[str, dict], list[str]]:
    """Carga el grafo completo de commits en orden topológico/cronológico."""
    fmt = f"%H{FIELD_SEP}%P{FIELD_SEP}%aI{FIELD_SEP}%an{FIELD_SEP}%ae{FIELD_SEP}%s{RECORD_SEP}"
    raw = run_git(repo_path, ["log", "--all", "--date-order", f"--format={fmt}"])
    commits: dict[str, dict] = {}
    order: list[str] = []

    for rec in raw.split(RECORD_SEP):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split(FIELD_SEP, 5)
        if len(parts) < 6:
            continue
        sha, parents_str, author_iso, author_name, author_email, subject = parts
        parents = parents_str.split() if parents_str.strip() else []
        commits[sha] = {
            "sha": sha,
            "short_sha": sha[:7],
            "parents": parents,
            "is_merge": len(parents) > 1,
            "author_iso": author_iso,
            "date": author_iso[:10],
            "author_name": author_name,
            "author_email": author_email,
            "subject": subject,
        }
        order.append(sha)

    return commits, order


def obtener_first_parent(repo_path: Path, ref: str) -> list[str]:
    """Devuelve los hashes del camino --first-parent de una rama."""
    raw = run_git(repo_path, ["rev-list", "--first-parent", ref])
    return [line.strip() for line in raw.splitlines() if line.strip()]


def detectar_ramas_integracion(
    repo_path: Path, extra_bases: list[str]
) -> dict[str, list[str]]:
    """Detecta ramas de integración existentes y su cadena --first-parent."""
    candidates: list[str] = []
    for name in [*extra_bases, *DEFAULT_INTEGRATION_BRANCHES]:
        if name not in candidates:
            candidates.append(name)

    integration: dict[str, list[str]] = {}
    for name in candidates:
        ref = name if ref_existe(repo_path, name) else f"origin/{name}"
        if ref_existe(repo_path, ref):
            integration[name] = obtener_first_parent(repo_path, ref)
    return integration


def obtener_autores(commits: dict[str, dict]) -> list[dict]:
    """Agrupa todos los pares (author_name, author_email) con conteos."""
    stats: dict[tuple[str, str], dict] = {}
    for commit in commits.values():
        key = (commit["author_name"], commit["author_email"])
        if key not in stats:
            stats[key] = {
                "name": commit["author_name"],
                "email": commit["author_email"],
                "total_commits": 0,
                "non_merge_commits": 0,
                "merge_commits": 0,
            }
        stats[key]["total_commits"] += 1
        if commit["is_merge"]:
            stats[key]["merge_commits"] += 1
        else:
            stats[key]["non_merge_commits"] += 1

    return sorted(
        stats.values(),
        key=lambda item: (-item["non_merge_commits"], -item["total_commits"], item["name"].lower()),
    )


def resolver_aliases(
    autores: list[dict], author_query: str | None, extra_aliases: list[str]
) -> dict:
    """Resuelve los alias (name/email) del autor objetivo y sugiere posibles sinónimos."""
    if not author_query and not extra_aliases:
        return {
            "query": None,
            "matched_aliases": [],
            "possible_related_aliases": [],
        }

    queries = [q.strip().lower() for q in ([author_query] if author_query else []) + extra_aliases if q and q.strip()]
    matched_keys: set[tuple[str, str]] = set()

    for entry in autores:
        name_l = entry["name"].lower()
        email_l = entry["email"].lower()
        if any(q in name_l or q in email_l for q in queries):
            matched_keys.add((entry["name"], entry["email"]))

    # Expansión transitiva por nombre exacto o email exacto compartido
    changed = True
    while changed:
        changed = False
        known_names = {n.lower() for n, _ in matched_keys}
        known_emails = {e.lower() for _, e in matched_keys}
        for entry in autores:
            key = (entry["name"], entry["email"])
            if key in matched_keys:
                continue
            if entry["name"].lower() in known_names or entry["email"].lower() in known_emails:
                matched_keys.add(key)
                changed = True

    # Detectar posibles alias relacionados por local-part del email
    known_local_parts = {
        e.split("@", 1)[0].lower()
        for _, e in matched_keys
        if "@" in e and not e.endswith("@users.noreply.github.com")
    }
    possible_related: list[dict] = []
    matched_aliases: list[dict] = []
    for entry in autores:
        key = (entry["name"], entry["email"])
        if key in matched_keys:
            matched_aliases.append(entry)
        elif "@" in entry["email"]:
            local_part = entry["email"].split("@", 1)[0].lower()
            if local_part in known_local_parts:
                possible_related.append(entry)

    return {
        "query": author_query,
        "matched_aliases": matched_aliases,
        "possible_related_aliases": possible_related,
    }


def es_del_autor(commit: dict, alias_keys: set[tuple[str, str]]) -> bool:
    """Indica si un commit pertenece a alguno de los alias del desarrollador."""
    return (commit["author_name"], commit["author_email"]) in alias_keys


def calcular_ancestros(
    commits: dict[str, dict], start_sha: str, cache: dict[str, set[str]]
) -> set[str]:
    """Devuelve el conjunto de ancestros (inclusive) de start_sha usando BFS iterativo."""
    if start_sha in cache:
        return cache[start_sha]

    visited: set[str] = set()
    stack = [start_sha]
    while stack:
        curr = stack.pop()
        if curr in visited:
            continue
        if curr in cache:
            visited.update(cache[curr])
            continue
        visited.add(curr)
        node = commits.get(curr)
        if node:
            for parent in node["parents"]:
                if parent not in visited:
                    stack.append(parent)

    cache[start_sha] = visited
    return visited


def parsear_merge_pr(subject: str) -> dict:
    """Extrae información de PR o merge de rama desde el título de un merge commit."""
    m = PR_FROM_RE.match(subject)
    if m:
        pr_num = int(m.group(1))
        owner = m.group(2)
        branch = m.group(3)
        is_sync = branch in SYNC_BRANCH_NAMES
        return {
            "kind": "sync_pr" if is_sync else "feature_pr",
            "pr_number": pr_num,
            "source_owner": owner,
            "source_branch": branch,
        }

    m_simple = PR_SIMPLE_RE.match(subject)
    if m_simple:
        return {
            "kind": "feature_pr",
            "pr_number": int(m_simple.group(1)),
            "source_owner": None,
            "source_branch": None,
        }

    m_branch = BRANCH_MERGE_RE.match(subject)
    if m_branch:
        src = m_branch.group(1)
        dst = m_branch.group(2)
        return {
            "kind": "sync_branch",
            "pr_number": None,
            "source_owner": None,
            "source_branch": src,
            "target_branch_hint": dst,
        }

    return {
        "kind": "other_merge",
        "pr_number": None,
        "source_owner": None,
        "source_branch": None,
    }


def obtener_estadisticas_commit(repo_path: Path, sha: str) -> dict:
    """Obtiene cuerpo del commit y estadísticas --numstat (archivos, +líneas, -líneas)."""
    raw = run_git(repo_path, ["show", "--numstat", f"--format=%B{RECORD_SEP}", sha])
    if RECORD_SEP in raw:
        body_raw, numstat_raw = raw.split(RECORD_SEP, 1)
    else:
        body_raw, numstat_raw = raw, ""

    body_lines = body_raw.strip().splitlines()
    # La primera línea de %B es el subject; el resto es el body extendido
    extended_body = "\n".join(body_lines[1:]).strip() if len(body_lines) > 1 else ""

    files: list[dict] = []
    total_ins = 0
    total_del = 0
    for line in numstat_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        ins_str, del_str, path = parts
        ins = int(ins_str) if ins_str.isdigit() else 0
        dels = int(del_str) if del_str.isdigit() else 0
        total_ins += ins
        total_del += dels
        files.append(
            {
                "path": path,
                "insertions": ins if ins_str.isdigit() else None,
                "deletions": dels if del_str.isdigit() else None,
            }
        )

    return {
        "body": extended_body,
        "files_changed": len(files),
        "insertions": total_ins,
        "deletions": total_del,
        "files": files,
    }


def formatear_commit_detalle(
    repo_path: Path, commit: dict, include_stat: bool
) -> dict:
    """Construye la representación serializable de un commit."""
    item = {
        "sha": commit["sha"],
        "short_sha": commit["short_sha"],
        "date": commit["date"],
        "author_iso": commit["author_iso"],
        "author_name": commit["author_name"],
        "author_email": commit["author_email"],
        "subject": commit["subject"],
    }
    if include_stat:
        item.update(obtener_estadisticas_commit(repo_path, commit["sha"]))
    return item


def detectar_rama_destino_merge(
    merge_sha: str, integration_sets: dict[str, set[str]]
) -> str | None:
    """Determina sobre qué rama de integración (develop, main, etc.) se aplicó un merge."""
    for branch_name, fp_set in integration_sets.items():
        if merge_sha in fp_set:
            return branch_name
    return None


def analizar_ramas_sin_mergear(
    repo_path: Path,
    commits: dict[str, dict],
    ancestors_cache: dict[str, set[str]],
    integration_branches: dict[str, list[str]],
    alias_keys: set[tuple[str, str]],
    include_stat: bool,
) -> list[dict]:
    """Detecta ramas remotas o locales no mergeadas con commits del autor."""
    integrated_commits: set[str] = set()
    for fp_list in integration_branches.values():
        if fp_list:
            integrated_commits.update(calcular_ancestros(commits, fp_list[0], ancestors_cache))

    refs_raw = run_git(
        repo_path,
        ["for-each-ref", "--format=%(refname:short)|%(objectname)", "refs/heads", "refs/remotes"],
    )
    unmerged: list[dict] = []
    seen_tips: set[str] = set()

    for line in refs_raw.splitlines():
        if not line.strip():
            continue
        ref_name, tip_sha = line.split("|", 1)
        if ref_name.endswith("/HEAD") or ref_name in integration_branches:
            continue
        if tip_sha in integrated_commits or tip_sha in seen_tips:
            continue

        tip_ancestors = calcular_ancestros(commits, tip_sha, ancestors_cache)
        unique_shas = [sha for sha in tip_ancestors if sha not in integrated_commits]
        author_commits = [
            commits[sha]
            for sha in unique_shas
            if not commits[sha]["is_merge"] and es_del_autor(commits[sha], alias_keys)
        ]
        if not author_commits:
            continue

        seen_tips.add(tip_sha)
        author_commits.sort(key=lambda c: c["author_iso"])
        unmerged.append(
            {
                "branch": ref_name,
                "tip_sha": tip_sha[:7],
                "start_date": author_commits[0]["date"],
                "end_date": author_commits[-1]["date"],
                "commits": [
                    formatear_commit_detalle(repo_path, c, include_stat) for c in author_commits
                ],
            }
        )
    return unmerged


def analizar_historial(
    repo_path: Path,
    author_query: str | None,
    extra_aliases: list[str],
    base_branches: list[str],
    include_stat: bool,
) -> dict:
    """Ejecuta el análisis completo en solo lectura sobre el repositorio."""
    repo_info = obtener_info_repo(repo_path)
    commits, order = cargar_commits_dag(repo_path)
    integration_branches = detectar_ramas_integracion(repo_path, base_branches)
    integration_sets = {name: set(fp) for name, fp in integration_branches.items()}

    autores = obtener_autores(commits)
    alias_info = resolver_aliases(autores, author_query, extra_aliases)
    alias_keys = {(a["name"], a["email"]) for a in alias_info["matched_aliases"]}

    ancestors_cache: dict[str, set[str]] = {}
    direct_integration_shas: dict[str, str] = {}
    for branch_name, fp_list in integration_branches.items():
        for sha in fp_list:
            if not commits[sha]["is_merge"] and sha not in direct_integration_shas:
                direct_integration_shas[sha] = branch_name

    # Analizar todos los merge commits (PRs y merges de ramas)
    all_merges: list[dict] = []
    commit_to_feature_prs: dict[str, list[dict]] = defaultdict(list)

    for sha in order:
        c = commits[sha]
        if not c["is_merge"]:
            continue
        p1 = c["parents"][0]
        p1_anc = calcular_ancestros(commits, p1, ancestors_cache)
        introduced_anc: set[str] = set()
        for p_other in c["parents"][1:]:
            introduced_anc.update(calcular_ancestros(commits, p_other, ancestors_cache) - p1_anc)

        introduced_non_merge = [
            commits[s]
            for s in order
            if s in introduced_anc and not commits[s]["is_merge"]
        ]
        # Orden cronológico ascendente dentro del PR
        introduced_non_merge.sort(key=lambda item: item["author_iso"])

        merge_meta = parsear_merge_pr(c["subject"])
        target_branch = detectar_rama_destino_merge(sha, integration_sets)
        entry = {
            "merge_sha": sha,
            "short_merge_sha": c["short_sha"],
            "merge_date": c["date"],
            "merge_iso": c["author_iso"],
            "merged_by": f"{c['author_name']} <{c['author_email']}>",
            "merged_by_target_author": es_del_autor(c, alias_keys),
            "subject": c["subject"],
            "target_branch": target_branch,
            "total_introduced_commits": len(introduced_non_merge),
            "introduced_commits": introduced_non_merge,
            **merge_meta,
        }
        all_merges.append(entry)

        if merge_meta["kind"] == "feature_pr":
            for nc in introduced_non_merge:
                commit_to_feature_prs[nc["sha"]].append(entry)

    # Si no se especificó autor, devolvemos el resumen general del repo y autores
    if not author_query and not extra_aliases:
        return {
            "repo": repo_info,
            "integration_branches": list(integration_branches.keys()),
            "authors": autores,
            "author_filter": None,
            "total_commits": len(commits),
            "total_merges": len(all_merges),
        }

    # Asignar cada commit no-merge del autor a su PR introductorio o rama directa
    author_non_merge = [
        commits[sha]
        for sha in order
        if not commits[sha]["is_merge"] and es_del_autor(commits[sha], alias_keys)
    ]
    author_non_merge.sort(key=lambda item: item["author_iso"])

    pr_groups: dict[int, dict] = {}
    direct_commits_by_branch: dict[str, list[dict]] = defaultdict(list)
    orphan_commits: list[dict] = []

    def elegir_pr_primario(candidates: list[dict]) -> dict:
        # Priorizar: 1) PR que no arrastra commits directos de develop, 2) menor cantidad de commits,
        # 3) target_branch == 'develop' antes que 'main', 4) PR más antiguo.
        def rank(pr_entry: dict) -> tuple:
            has_direct_develop = any(
                nc["sha"] in direct_integration_shas for nc in pr_entry["introduced_commits"]
            )
            branch_prio = 0 if pr_entry["target_branch"] == "develop" else 1
            return (
                1 if has_direct_develop else 0,
                pr_entry["total_introduced_commits"],
                branch_prio,
                pr_entry["merge_iso"],
            )

        return sorted(candidates, key=rank)[0]

    for c in author_non_merge:
        sha = c["sha"]
        if sha in direct_integration_shas:
            direct_commits_by_branch[direct_integration_shas[sha]].append(c)
            continue

        candidates = commit_to_feature_prs.get(sha, [])
        if not candidates:
            orphan_commits.append(c)
            continue

        primary = elegir_pr_primario(candidates)
        pr_num = primary["pr_number"]
        if pr_num not in pr_groups:
            also_prs = sorted(
                {
                    cand["pr_number"]
                    for cand in candidates
                    if cand["pr_number"] != pr_num
                    and cand["pr_number"] is not None
                    and (
                        (primary["source_branch"] and cand["source_branch"] == primary["source_branch"])
                        or set(nc["sha"] for nc in cand["introduced_commits"])
                        == set(nc["sha"] for nc in primary["introduced_commits"])
                    )
                }
            )
            pr_groups[pr_num] = {
                "pr_meta": primary,
                "also_merged_in_prs": also_prs,
                "author_commits": [],
            }
        pr_groups[pr_num]["author_commits"].append(c)

    # Construir lista estructurada de PRs propios / colaborativos
    prs_propios: list[dict] = []
    prs_colaborativos: list[dict] = []
    primary_pr_numbers = set(pr_groups.keys())

    for pr_num, group in sorted(pr_groups.items(), key=lambda kv: kv[1]["pr_meta"]["merge_iso"]):
        meta = group["pr_meta"]
        all_in_pr = meta["introduced_commits"]
        author_shas = {c["sha"] for c in group["author_commits"]}
        other_authors = sorted(
            {
                f"{nc['author_name']} <{nc['author_email']}>"
                for nc in all_in_pr
                if nc["sha"] not in author_shas
            }
        )
        author_commits_sorted = sorted(group["author_commits"], key=lambda item: item["author_iso"])
        record = {
            "pr_number": pr_num,
            "source_branch": meta["source_branch"],
            "target_branch": meta["target_branch"],
            "merge_sha": meta["short_merge_sha"],
            "merge_date": meta["merge_date"],
            "merged_by": meta["merged_by"],
            "also_merged_in_prs": group["also_merged_in_prs"],
            "start_date": author_commits_sorted[0]["date"],
            "end_date": author_commits_sorted[-1]["date"],
            "total_commits_in_pr": len(all_in_pr),
            "author_commit_count": len(author_commits_sorted),
            "other_authors_in_pr": other_authors,
            "commits": [
                formatear_commit_detalle(repo_path, c, include_stat) for c in author_commits_sorted
            ],
        }
        if other_authors:
            prs_colaborativos.append(record)
        else:
            prs_propios.append(record)

    # Identificar PRs y merges de ramas donde el usuario solo mergeó trabajo ajeno o resolvió sync
    prs_ajenos_mergeados: list[dict] = []
    sync_merges_por_autor: list[dict] = []

    for m in all_merges:
        if not m["merged_by_target_author"]:
            continue
        if m["kind"] in ("sync_pr", "sync_branch") or (
            m["pr_number"] is None and (m["kind"] == "other_merge" or not m["introduced_commits"])
        ):
            sync_merges_por_autor.append(
                {
                    "merge_sha": m["short_merge_sha"],
                    "merge_date": m["merge_date"],
                    "pr_number": m["pr_number"],
                    "source_branch": m["source_branch"],
                    "target_branch": m["target_branch"],
                    "subject": m["subject"],
                }
            )
            continue

        pr_num = m["pr_number"]
        if pr_num in primary_pr_numbers:
            continue
        # Excluir duplicados de PR propios que también aparecen en otra rama (#143 vs #144)
        if any(pr_num in g["also_merged_in_prs"] for g in pr_groups.values()):
            continue

        introduced = m["introduced_commits"]
        author_commits_inside = [nc for nc in introduced if es_del_autor(nc, alias_keys)]
        other_authors_inside = sorted(
            {
                f"{nc['author_name']} <{nc['author_email']}>"
                for nc in introduced
                if not es_del_autor(nc, alias_keys)
            }
        )
        prs_ajenos_mergeados.append(
            {
                "pr_number": pr_num,
                "source_branch": m["source_branch"],
                "target_branch": m["target_branch"],
                "merge_sha": m["short_merge_sha"],
                "merge_date": m["merge_date"],
                "subject": m["subject"],
                "other_authors": other_authors_inside,
                "author_commits_inside": len(author_commits_inside),
                "total_commits_inside": len(introduced),
            }
        )

    commits_directos: list[dict] = []
    for branch_name, clist in direct_commits_by_branch.items():
        clist_sorted = sorted(clist, key=lambda item: item["author_iso"])
        commits_directos.append(
            {
                "branch": branch_name,
                "commits": [formatear_commit_detalle(repo_path, c, include_stat) for c in clist_sorted],
            }
        )

    ramas_sin_mergear = analizar_ramas_sin_mergear(
        repo_path, commits, ancestors_cache, integration_branches, alias_keys, include_stat
    )

    # Sacar de orphan_commits los que ya están reportados en ramas_sin_mergear
    unmerged_shas = {
        c["sha"] for branch in ramas_sin_mergear for c in branch["commits"]
    }
    commits_sueltos = [
        formatear_commit_detalle(repo_path, c, include_stat)
        for c in orphan_commits
        if c["sha"] not in unmerged_shas
    ]

    return {
        "repo": repo_info,
        "integration_branches": list(integration_branches.keys()),
        "author_filter": alias_info,
        "summary": {
            "total_author_non_merge_commits": len(author_non_merge),
            "prs_propios_count": len(prs_propios),
            "prs_colaborativos_count": len(prs_colaborativos),
            "direct_commits_count": sum(len(b["commits"]) for b in commits_directos),
            "unmerged_branches_count": len(ramas_sin_mergear),
            "prs_ajenos_mergeados_count": len(prs_ajenos_mergeados),
            "sync_merges_count": len(sync_merges_por_autor),
        },
        "prs_propios": prs_propios,
        "prs_colaborativos": prs_colaborativos,
        "commits_directos": commits_directos,
        "ramas_sin_mergear": ramas_sin_mergear,
        "commits_sueltos": commits_sueltos,
        "prs_ajenos_mergeados": prs_ajenos_mergeados,
        "sync_merges_por_autor": sync_merges_por_autor,
    }


def _imprimir_commits_bloque(lines: list[str], commits: list[dict], indent: str = "    ") -> None:
    for c in commits:
        stat_txt = ""
        if "files_changed" in c:
            stat_txt = f" [{c['files_changed']} files, +{c['insertions']}/-{c['deletions']}]"
        lines.append(f"{indent}- {c['short_sha']} ({c['date']}) {c['subject']}{stat_txt}")
        if c.get("files"):
            file_names = ", ".join(f["path"] for f in c["files"][:6])
            extra = f" (+{len(c['files']) - 6} más)" if len(c["files"]) > 6 else ""
            lines.append(f"{indent}  archivos: {file_names}{extra}")


def formatear_reporte_texto(reporte: dict) -> str:
    """Genera un reporte legible por humanos para revisar autoría y PRs."""
    lines: list[str] = []
    repo = reporte["repo"]
    lines.append(f"=== Repositorio: {repo['path']} ===")
    if repo["github_repo"]:
        lines.append(f"GitHub: {repo['github_repo']} (HEAD: {repo['head_branch']} @ {repo['head_sha']})")
    else:
        lines.append(f"Remoto: {repo['remote_url'] or 'N/A'} (HEAD: {repo['head_branch']} @ {repo['head_sha']})")
    lines.append(f"Ramas de integración detectadas: {', '.join(reporte['integration_branches']) or 'Ninguna'}")

    if reporte.get("author_filter") is None:
        lines.append(f"\nTotal commits: {reporte['total_commits']} | Merges: {reporte['total_merges']}")
        lines.append("\nAutores detectados:")
        for a in reporte["authors"]:
            lines.append(
                f"  - {a['name']} <{a['email']}>: {a['non_merge_commits']} commits (+ {a['merge_commits']} merges)"
            )
        return "\n".join(lines)

    af = reporte["author_filter"]
    lines.append(f"\n=== Autor analizado: {af['query']} ===")
    if not af["matched_aliases"]:
        lines.append("  [!] No se encontraron alias coincidentes en el historial.")
        return "\n".join(lines)

    lines.append("Alias agrupados:")
    for a in af["matched_aliases"]:
        lines.append(
            f"  - {a['name']} <{a['email']}> ({a['non_merge_commits']} commits propios, {a['merge_commits']} merges)"
        )
    if af["possible_related_aliases"]:
        lines.append("Posibles alias adicionales detectados por email (usar --aliases si corresponde):")
        for a in af["possible_related_aliases"]:
            lines.append(f"  ? {a['name']} <{a['email']}> ({a['non_merge_commits']} commits)")

    s = reporte["summary"]
    lines.append(
        "\nResumen: "
        f"{s['total_author_non_merge_commits']} commits propios | "
        f"{s['prs_propios_count']} PRs propios | "
        f"{s['prs_colaborativos_count']} PRs colaborativos | "
        f"{s['direct_commits_count']} commits directos | "
        f"{s['unmerged_branches_count']} ramas sin mergear | "
        f"{s['prs_ajenos_mergeados_count']} PRs ajenos mergeados (EXCLUIR)"
    )

    lines.append("\n--- 1. PRs PROPIOS (autoría 100% del desarrollador) ---")
    if not reporte["prs_propios"]:
        lines.append("  (ninguno)")
    for pr in reporte["prs_propios"]:
        also = f" (también en PR #{', #'.join(map(str, pr['also_merged_in_prs']))})" if pr["also_merged_in_prs"] else ""
        lines.append(
            f"  PR #{pr['pr_number']}{also} | rama: {pr['source_branch']} -> {pr['target_branch'] or '?'} "
            f"| inicio: {pr['start_date']} | merge: {pr['merge_date']} ({pr['merge_sha']})"
        )
        _imprimir_commits_bloque(lines, pr["commits"])

    if reporte["prs_colaborativos"]:
        lines.append("\n--- 2. PRs COLABORATIVOS (commits del autor + otros compañeros) ---")
        for pr in reporte["prs_colaborativos"]:
            lines.append(
                f"  PR #{pr['pr_number']} | rama: {pr['source_branch']} -> {pr['target_branch'] or '?'} "
                f"| inicio: {pr['start_date']} | merge: {pr['merge_date']} "
                f"| propios: {pr['author_commit_count']}/{pr['total_commits_in_pr']} "
                f"| otros: {', '.join(pr['other_authors_in_pr'])}"
            )
            _imprimir_commits_bloque(lines, pr["commits"])

    if reporte["commits_directos"]:
        lines.append("\n--- 3. COMMITS DIRECTOS EN RAMA DE INTEGRACIÓN (sin PR propio) ---")
        for block in reporte["commits_directos"]:
            lines.append(f"  Rama: {block['branch']}")
            _imprimir_commits_bloque(lines, block["commits"])

    if reporte["ramas_sin_mergear"]:
        lines.append("\n--- 4. RAMAS SIN MERGEAR CON TRABAJO DEL AUTOR ---")
        for b in reporte["ramas_sin_mergear"]:
            lines.append(f"  Rama: {b['branch']} (tip {b['tip_sha']}, {b['start_date']}..{b['end_date']})")
            _imprimir_commits_bloque(lines, b["commits"])

    if reporte["commits_sueltos"]:
        lines.append("\n--- 5. COMMITS SUELTOS EN OTRAS REFERENCIAS ---")
        _imprimir_commits_bloque(lines, reporte["commits_sueltos"], indent="  ")

    lines.append("\n--- 6. EXCLUSIONES: PRs AJENOS DONDE EL AUTOR SOLO HIZO MERGE (NO ATRIBUIR) ---")
    if not reporte["prs_ajenos_mergeados"]:
        lines.append("  (ninguno)")
    for pr in reporte["prs_ajenos_mergeados"]:
        lines.append(
            f"  [EXCLUIR] PR #{pr['pr_number']} ({pr['merge_date']}) | rama: {pr['source_branch']} -> {pr['target_branch'] or '?'} "
            f"| autores reales: {', '.join(pr['other_authors']) or 'N/A'}"
        )

    if reporte["sync_merges_por_autor"]:
        lines.append("\n--- 7. MERGES DE SINCRONIZACIÓN / CONFLICTOS REALIZADOS POR EL AUTOR ---")
        for sm in reporte["sync_merges_por_autor"]:
            pr_txt = f"PR #{sm['pr_number']} " if sm["pr_number"] else ""
            lines.append(f"  {sm['merge_sha']} ({sm['merge_date']}) {pr_txt}{sm['subject']}")

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analiza en solo lectura el historial Git de un repo y separa autoría real."
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Ruta al repositorio Git objetivo (por defecto: directorio actual).",
    )
    parser.add_argument(
        "--author",
        help="Nombre, usuario o email (subcadena) del desarrollador a analizar.",
    )
    parser.add_argument(
        "--aliases",
        default="",
        help="Alias adicionales separados por coma (nombres o emails) del mismo desarrollador.",
    )
    parser.add_argument(
        "--base-branches",
        default="",
        help="Ramas de integración separadas por coma (por defecto detecta develop, main, master).",
    )
    parser.add_argument(
        "--no-stat",
        action="store_true",
        help="Omitir detalles de archivos modificados (--numstat) para salidas más compactas.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Formato de salida por stdout (text o json).",
    )
    parser.add_argument(
        "--out",
        help="Ruta opcional donde guardar el reporte completo en JSON (ej. outputs/git_usuario.json).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_path = validar_repo(Path(args.repo_path))
        extra_aliases = [x.strip() for x in args.aliases.split(",") if x.strip()]
        base_branches = [x.strip() for x in args.base_branches.split(",") if x.strip()]
        reporte = analizar_historial(
            repo_path=repo_path,
            author_query=args.author,
            extra_aliases=extra_aliases,
            base_branches=base_branches,
            include_stat=not args.no_stat,
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
