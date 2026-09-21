"""Fallback resolution engine: assign each grapheme cluster to a font and
explain missing glyphs, combining-character splits and alias priority cycles.
"""
from __future__ import annotations

from .manifest import FontEntry, Manifest
from .segmentation import Cluster


def _covered_cps(entry: FontEntry, cps: list[int]) -> list[int]:
    return [i for i, cp in enumerate(cps) if entry.covers(cp)]


def _resolve_font_name(manifest: Manifest, name: str):
    """Return (effective_font_entry, alias_source_name, chain, cycles)."""
    target, chain, cycles = manifest.resolve_alias(name)
    entry = manifest.fonts.get(target) if target else None
    return entry, name if target != name else None, chain, cycles


def _font_label(manifest: Manifest, name: str) -> str:
    target, _, _ = manifest.resolve_alias(name)
    if target and target != name:
        return f"{name} → {target}"
    return name


def _resolve_cluster_level(cluster: Cluster, manifest: Manifest,
                           cycles_out: list[dict]) -> dict:
    """First font (by priority) that covers every codepoint in the cluster."""
    cps = [c.cp for c in cluster.codepoints]
    chain: list[dict] = []
    chosen: str | None = None
    chosen_via: str | None = None

    for raw_name in manifest.order:
        entry, via, _, cycles = _resolve_font_name(manifest, raw_name)
        cycles_out.extend(cycles)
        if entry is None:
            continue
        covered = _covered_cps(entry, cps)
        missing = [i for i in range(len(cps)) if i not in covered]
        chain.append({"font": raw_name, "viaAlias": via,
                      "covered": covered, "missing": missing})
        if not missing:
            chosen = raw_name
            chosen_via = via
            break

    used_default = False
    if chosen is None and manifest.default:
        entry, via, _, dcycles = _resolve_font_name(manifest, manifest.default)
        cycles_out.extend(dcycles)
        if entry is not None:
            covered = _covered_cps(entry, cps)
            missing = [i for i in range(len(cps)) if i not in covered]
            chain.append({"font": manifest.default, "viaAlias": via,
                          "covered": covered, "missing": missing,
                          "default": True})
            if not missing:
                chosen = manifest.default
                chosen_via = via
                used_default = True

    return {"chosen": chosen, "viaAlias": chosen_via, "chain": chain,
            "usedDefault": used_default}


def _resolve_codepoint_level(cluster: Cluster, manifest: Manifest, order: list[str],
                             cycles_out: list[dict]) -> dict:
    """Every codepoint independently walks the priority list (font-fallback
    as browsers do when a cluster cannot be rendered by one face)."""
    cps = [c.cp for c in cluster.codepoints]
    per_cp: list[dict] = []

    for i, cp in enumerate(cps):
        chain: list[dict] = []
        chosen: str | None = None
        for raw_name in order:
            entry, via, _, cycles = _resolve_font_name(manifest, raw_name)
            cycles_out.extend(cycles)
            if entry is None:
                continue
            ok = entry.covers(cp)
            chain.append({"font": raw_name, "viaAlias": via,
                          "covered": [i] if ok else [], "missing": [] if ok else [i]})
            if ok:
                chosen = raw_name
                break
        if chosen is None and manifest.default:
            entry, via, _, dcycles = _resolve_font_name(manifest, manifest.default)
            cycles_out.extend(dcycles)
            if entry is not None:
                ok = entry.covers(cp)
                chain.append({"font": manifest.default, "viaAlias": via,
                              "covered": [i] if ok else [],
                              "missing": [] if ok else [i], "default": True})
                if ok:
                    chosen = manifest.default
        per_cp.append({"index": i, "chosen": chosen, "chain": chain})

    # The "cluster" font is the base's font; fragmentation is flagged separately.
    chosen = per_cp[0]["chosen"] if per_cp else None
    fragmented = len({p["chosen"] for p in per_cp if p["chosen"]}) > 1
    return {"chosen": chosen, "perCodepoint": per_cp,
            "fragmented": fragmented, "chain": per_cp[0]["chain"] if per_cp else [],
            "usedDefault": chosen == manifest.default if manifest.default else False}


def _issues_for_cluster(cluster: Cluster, res: dict, manifest: Manifest,
                        mode: str) -> tuple[list[str], list[dict]]:
    """Return (severity tags, issue records with location & explanation)."""
    tags: list[str] = []
    issues: list[dict] = []
    cps = cluster.codepoints

    if mode == "cluster":
        if res["chosen"] is None:
            # No single font covers the whole cluster. Distinguish true tofu
            # (missing in every face) from cross-font fragmentation.
            tried = res["chain"]
            fonts_for_cp: dict[int, list[str]] = {}
            for i, c in enumerate(cps):
                fonts = [step["font"] for step in tried if i in step["covered"]]
                fonts_for_cp[i] = fonts
                if not fonts:
                    tags.append("missing")
                    issues.append({
                        "kind": "missing_glyph",
                        "cpIndex": i,
                        "cp": c.hex,
                        "char": c.char,
                        "block": c.block,
                        "at": f"簇 #{cluster.index} 的第 {i + 1} 个码位 {c.hex}",
                        "message": (
                            f"缺字：{c.hex}（{c.name}，{c.block or '无区块'}）在优先级"
                            f"清单的所有字体（含兜底）中均无覆盖。"
                        ),
                    })
            fragmented_indices = [i for i, fs in fonts_for_cp.items() if fs]
            if fragmented_indices:
                # Does the base come from a different font than attached marks?
                mark_roles = {"combining-mark", "combining-enclosing-keycap",
                              "variation-selector", "emoji-modifier"}
                involves_marks = any(cps[i].role in mark_roles for i in fragmented_indices)
                tags.append("combining-split" if involves_marks else "fragmented")
                groups = [
                    {"font": fs[0], "cpIndexes": [i]}
                    for i in fragmented_indices if (fs := fonts_for_cp[i])
                ]
                issues.append({
                    "kind": "fragmented_cluster",
                    "at": f"簇 #{cluster.index}（{cluster.text!r}）",
                    "groups": groups,
                    "message": (
                        "整簇无单一字体可覆盖，逐码位回退时将拆分为："
                        + "；".join(
                            f"{cps[i].hex}→{_font_label(manifest, fonts_for_cp[i][0])}"
                            for i in fragmented_indices
                        )
                        + ("。组合记号可能与基字错配或显示为豆腐块。" if involves_marks
                           else "。多字体拼接会造成字宽/风格不一致。")
                    ),
                })
        else:
            # Cluster resolved as a whole by one font; a higher-priority font
            # that had the base but dropped marks is still worth surfacing.
            for step in res["chain"][:-1]:
                tgt = manifest.resolve_alias(step["font"])[0]
                base_ok = 0 in step["covered"]
                dropped_marks = [i for i in step["missing"]
                                 if cps[i].role in ("combining-mark",
                                                    "combining-enclosing-keycap",
                                                    "variation-selector",
                                                    "emoji-modifier")]
                if base_ok and dropped_marks and tgt:
                    for i in dropped_marks:
                        c = cps[i]
                        tags.append("combining-split")
                        issues.append({
                            "kind": "combining_split",
                            "cpIndex": i,
                            "cp": c.hex,
                            "char": c.char,
                            "block": c.block,
                            "at": f"簇 #{cluster.index} 的第 {i + 1} 个码位 {c.hex}",
                            "message": (
                                f"组合字符分离：更高优先的 {step['font']} 含基字 "
                                f"{cps[0].hex} 但不含组合记号 {c.hex}（{c.name}），"
                                f"整簇让位于 {_font_label(manifest, res['chosen'])}；"
                                f"若渲染器逐码位回退，该记号会显示为豆腐块或与基字错配。"
                            ),
                        })
    else:
        fragmented = res.get("fragmented", False)
        for p in res["perCodepoint"]:
            i = p["index"]
            c = cps[i]
            if p["chosen"] is None:
                tags.append("missing")
                issues.append({
                    "kind": "missing_glyph",
                    "cpIndex": i,
                    "cp": c.hex,
                    "char": c.char,
                    "block": c.block,
                    "at": f"簇 #{cluster.index} 的第 {i + 1} 个码位 {c.hex}",
                    "message": (
                        f"缺字：{c.hex}（{c.name}，{c.block or '无区块'}）在所有字体"
                        f"（含兜底）中均无覆盖。"
                    ),
                })
        if fragmented:
            groups: dict[str, list[int]] = {}
            for p in res["perCodepoint"]:
                if p["chosen"]:
                    groups.setdefault(p["chosen"], []).append(p["index"])
            if any(cps[i].role in ("combining-mark", "combining-enclosing-keycap")
                   for p in res["perCodepoint"] for i in [p["index"]]):
                tags.append("combining-split")
            else:
                tags.append("fragmented")
            issues.append({
                "kind": "fragmented_cluster",
                "at": f"簇 #{cluster.index}（{cluster.text!r}）",
                "groups": [{"font": f, "cpIndexes": ix} for f, ix in groups.items()],
                "message": (
                    "字素簇被拆分到多个字体渲染："
                    + "；".join(f"{_font_label(manifest, f)} 覆盖码位 {[i + 1 for i in ix]}"
                               for f, ix in groups.items())
                    + "。不同字体的字宽/基线/造型差异会导致组合记号错位或连字断裂。"
                ),
            })

    # ZWJ sequences only survive when one font covers the whole cluster.
    if cluster.has_zwj and mode == "codepoint" and (
            res.get("fragmented") or res["chosen"] is None):
        tags.append("zwj-break")
        issues.append({
            "kind": "zwj_sequence_broken",
            "at": f"簇 #{cluster.index}（ZWJ 序列）",
            "message": "该字素簇含 U+200D 零宽连接符；被拆到多字体或缺字时，"
                       "ZWJ 连字（如家庭/职业 emoji）会退化为多个独立符号。",
        })

    if res.get("usedDefault"):
        tags.append("default")
    return sorted(set(tags)), issues


def _repair_suggestions(manifest: Manifest, all_issues: list[dict],
                        clusters: list[Cluster]) -> list[dict]:
    """Aggregate problems into copyable fix recommendations."""
    suggestions: list[dict] = []

    # 1) Missing glyphs grouped by block → add a font / extend coverage.
    missing_by_block: dict[str, list[str]] = {}
    for iss in all_issues:
        if iss["kind"] == "missing_glyph":
            missing_by_block.setdefault(iss.get("block") or "未知区块", []).append(iss["cp"])
    for block, hex_cps in sorted(missing_by_block.items()):
        cps_sorted = sorted(set(hex_cps))
        snippet_block = ""
        from .unicode_blocks import block_range
        rng = block_range(block)
        if rng:
            snippet_block = f'"blocks": ["{block}"]'
        cp_list = ", ".join(f'"{h}"' for h in cps_sorted[:12])
        more = f" 等 {len(cps_sorted)} 个" if len(cps_sorted) > 12 else ""
        suggestions.append({
            "id": f"add-coverage:{block}",
            "severity": "error",
            "title": f"为「{block}」补充字体覆盖",
            "problem": f"检测到 {len(cps_sorted)} 个缺字码位（{', '.join(cps_sorted[:6])}{more}）",
            "fix": (
                "在覆盖该区块的字体条目加入声明，或在 fallback_order 前置一款支持该区块的字体，"
                "例如 Noto 系列对应字体。可直接粘贴："
            ),
            "snippet": (
                f"// 方案 A：整区块声明\n{snippet_block}\n\n"
                f"// 方案 B：仅补实际缺字（合并到 fonts[\"...\"] 中）\n"
                f'"codepoints": [{cp_list}]{more}'
            ),
            "copyable": True,
        })

    # 2) Combining splits → prefer one font covering base + marks.
    if any(i["kind"] in ("combining_split", "fragmented_cluster",
                         "zwj_sequence_broken") for i in all_issues):
        suggestions.append({
            "id": "reorder-combining",
            "severity": "warning",
            "title": "调整优先级，让同一字体覆盖「基字 + 组合记号」",
            "problem": "存在组合记号/ZWJ 序列被拆分到多字体的情况，可能出现豆腐块或错位。",
            "fix": ("把同时覆盖基字与组合记号区块（如 Combining Diacritical Marks、"
                    "Variation Selectors、emoji 区块）的字体在 fallback_order 中前置；"
                    "或给高优先字体追加组合记号区块："),
            "snippet": (
                '// 追加到高优先字体的 blocks 中：\n'
                '"blocks": ["Combining Diacritical Marks", '
                '"Combining Diacritical Marks Supplement", '
                '"Variation Selectors", "Combining Diacritical Marks for Symbols"]'
            ),
            "copyable": True,
        })

    # 3) Cycles are reported at manifest level; add a generic hint.
    if any(i["kind"] == "alias_cycle" for i in all_issues):
        suggestions.append({
            "id": "break-alias-cycle",
            "severity": "error",
            "title": "打断字体别名优先级循环",
            "problem": "alias_for 链中存在闭环，闭环上的字体永远无法提供字形。",
            "fix": "删除或重定向闭环中的某一条 alias_for，使链终止于一个真实覆盖字体。",
            "snippet": '// 将闭环末端字体改为真实覆盖字体，例如：\n'
                       '"BadAlias": { "alias_for": "Noto Sans" }   // 而不是指回环内字体',
            "copyable": True,
        })

    return suggestions


def diagnose(text: str, clusters: list[Cluster], manifest: Manifest,
             mode: str = "cluster") -> dict:
    order, order_issues = manifest.effective_order()
    manifest_issues: list[dict] = list(order_issues)
    manifest_issues.extend(manifest.detect_order_duplicates())

    cluster_records: list[dict] = []
    all_issues: list[dict] = list(manifest_issues)
    missing_count = 0
    split_count = 0
    default_count = 0

    for cluster in clusters:
        if mode == "codepoint":
            res = _resolve_codepoint_level(cluster, manifest, order, manifest_issues)
        else:
            res = _resolve_cluster_level(cluster, manifest, manifest_issues)
        tags, issues = _issues_for_cluster(cluster, res, manifest, mode)
        missing_count += tags.count("missing")
        split_count += 1 if {"combining-split", "fragmented", "zwj-break"} & set(tags) else 0
        default_count += 1 if "default" in tags else 0
        all_issues.extend(issues)

        record = {
            "index": cluster.index,
            "text": cluster.text,
            "kind": cluster.kind,
            "start": cluster.start,
            "end": cluster.end,
            "codepoints": [c.to_dict() for c in cluster.codepoints],
            "chosenFont": res["chosen"],
            "usedDefault": res.get("usedDefault", False),
            "status": ("missing" if "missing" in tags else
                       "split" if {"combining-split", "fragmented", "zwj-break"} & set(tags)
                       else "default" if "default" in tags else "ok"),
            "tags": tags,
            "issues": issues,
            "fallbackChain": res["chain"],
        }
        if mode == "codepoint":
            record["perCodepoint"] = res["perCodepoint"]
            record["fragmented"] = res.get("fragmented", False)
        cluster_records.append(record)

    # de-duplicate manifest-level alias cycles in issue list
    seen_keys: set[str] = set()
    deduped: list[dict] = []
    for iss in all_issues:
        if iss["kind"] in ("alias_cycle", "dangling_font", "duplicate_priority"):
            key = iss["message"]
            if key in seen_keys:
                continue
            seen_keys.add(key)
        deduped.append(iss)

    suggestions = _repair_suggestions(manifest, deduped, clusters)

    return {
        "summary": {
            "clusterCount": len(clusters),
            "codepointCount": sum(len(c.codepoints) for c in clusters),
            "missingCount": missing_count,
            "splitCount": split_count,
            "defaultedCount": default_count,
            "issueCount": len([i for i in deduped]),
            "mode": mode,
            "effectiveOrder": order,
        },
        "manifest": {
            "order": manifest.order,
            "default": manifest.default,
            "warnings": manifest.warnings,
            "fontCount": len(manifest.fonts),
            "fonts": [
                {"name": n, "coverageSize": f.coverage_size(),
                 "intervalCount": len(f.intervals), "aliasFor": f.alias_for}
                for n, f in manifest.fonts.items()
            ],
        },
        "issues": deduped,
        "suggestions": suggestions,
        "clusters": cluster_records,
    }
