"""按字体优先级解析每个字素簇的实际字体来源，并检测优先级循环。

解析顺序（effective order）：
  依次遍历优先级列表；每访问一个字体后，沿其 fallbackTo 链继续深入，
  直到链结束、遇到已访问字体或检测到循环。所有优先级条目遍历完后
  去重即得最终匹配顺序。
"""
from __future__ import annotations

from .coverage import Font


def build_effective_order(
    fonts: dict[str, Font], priority: list[str]
) -> tuple[list[str], list[list[str]], list[str], list[str]]:
    """返回 (匹配顺序, 循环列表, 未知字体, 重复字体)。"""
    order: list[str] = []
    seen: set[str] = set()
    cycles: list[list[str]] = []
    cycle_keys: set[frozenset[str]] = set()
    unknown: list[str] = []
    duplicates: list[str] = []

    counted: set[str] = set()
    for name in priority:
        if name in counted and name not in duplicates:
            duplicates.append(name)
        counted.add(name)

    for name in priority:
        if name not in fonts:
            if name not in unknown:
                unknown.append(name)
            continue
        if name in seen:
            continue
        chain: list[str] = []
        cur: str | None = name
        dangling: str | None = None
        while cur:
            if cur not in fonts:
                dangling = cur
                break
            if cur in chain:  # 沿 fallbackTo 走回了链内字体 → 循环
                cyc = chain[chain.index(cur):] + [cur]
                key = frozenset(cyc)
                if key not in cycle_keys:
                    cycle_keys.add(key)
                    cycles.append(cyc)
                break
            if cur in seen:  # 已被先前条目覆盖，直接衔接
                break
            chain.append(cur)
            cur = fonts[cur].fallback_to
        if dangling and dangling not in unknown:
            unknown.append(dangling)
        for n in chain:
            if n not in seen:
                seen.add(n)
                order.append(n)

    return order, cycles, unknown, duplicates


def resolve_cluster(
    cluster: str, fonts: dict[str, Font], order: list[str]
) -> dict:
    """对单个字素簇执行回退链匹配。"""
    cps = [ord(c) for c in cluster]
    chain: list[dict] = []
    resolved: str | None = None

    for name in order:
        font = fonts[name]
        covered = [cp for cp in cps if font.covers(cp)]
        missing = [cp for cp in cps if not font.covers(cp)]
        verdict = "hit" if not missing else "miss"
        chain.append(
            {
                "font": name,
                "verdict": verdict,
                "covered": [f"U+{cp:04X}" for cp in covered],
                "missing": [f"U+{cp:04X}" for cp in missing],
            }
        )
        if verdict == "hit":
            resolved = name
            break

    # 无完整命中时，找覆盖码点最多的字体作为最佳部分匹配
    best_partial: str | None = None
    if resolved is None and chain:
        best = max(chain, key=lambda e: len(e["covered"]))
        if best["covered"]:
            best_partial = best["font"]

    # 所有清单字体都不覆盖的码点
    uncovered = [
        cp for cp in cps if not any(f.covers(cp) for f in fonts.values())
    ]

    if resolved is not None:
        status = "ok"
    elif best_partial is not None:
        status = "partial"
    else:
        status = "missing"

    return {
        "codepoints": cps,
        "status": status,
        "resolved_font": resolved,
        "best_partial_font": best_partial,
        "chain": chain,
        "uncovered": uncovered,
    }
