"""诊断编排：切分 → 解析 → 诊断，与 HTTP 层解耦，便于测试。"""
from __future__ import annotations

import unicodedata

from . import diagnostics, resolver, segmenter
from .coverage import parse_manifest


def run_diagnose(text: str, manifest: dict, priority: list[str] | None) -> dict:
    fonts, manifest_errors, manifest_priority = parse_manifest(manifest)
    effective_priority = (
        [p.strip() for p in priority if p.strip()]
        if priority
        else manifest_priority
    )

    order, cycles, unknown, duplicates = resolver.build_effective_order(
        fonts, effective_priority
    )

    clusters_raw = segmenter.grapheme_clusters(text)
    clusters: list[dict] = []
    offset = 0
    for i, cluster in enumerate(clusters_raw):
        result = resolver.resolve_cluster(cluster, fonts, order)
        cps: list[int] = result["codepoints"]
        diags = diagnostics.cluster_diagnostics(cluster, result, fonts, order)
        clusters.append(
            {
                "index": i,
                "text": cluster,
                "start": offset,
                "end": offset + len(cluster),
                "codepoints": [diagnostics.fmt_cp(cp) for cp in cps],
                "names": [diagnostics.cp_name(cp) for cp in cps],
                "categories": [unicodedata.category(ch) for ch in cluster],
                "status": result["status"],
                "resolvedFont": result["resolved_font"],
                "bestPartialFont": result["best_partial_font"],
                "chain": result["chain"],
                "diagnostics": diags,
            }
        )
        offset += len(cluster)

    global_diags = diagnostics.global_diagnostics(
        fonts,
        effective_priority,
        order,
        cycles,
        unknown,
        duplicates,
        manifest_errors,
    )

    def count_sev(sev: str) -> int:
        return sum(
            1
            for d in global_diags + [d for c in clusters for d in c["diagnostics"]]
            if d["severity"] == sev
        )

    summary = {
        "total": len(clusters),
        "ok": sum(1 for c in clusters if c["status"] == "ok"),
        "partial": sum(1 for c in clusters if c["status"] == "partial"),
        "missing": sum(1 for c in clusters if c["status"] == "missing"),
        "errors": count_sev("error"),
        "warnings": count_sev("warning"),
    }

    return {
        "clusters": clusters,
        "globalDiagnostics": global_diags,
        "summary": summary,
        "effectiveOrder": order,
        "segmenter": segmenter.backend_name(),
    }
