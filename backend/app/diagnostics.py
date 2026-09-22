"""诊断规则与可复制的修复建议（中文文案）。"""
from __future__ import annotations

import unicodedata

from . import gcb
from .blocks import block_name
from .coverage import Font


def fmt_cp(cp: int) -> str:
    return f"U+{cp:04X}"


def cp_name(cp: int) -> str:
    try:
        return unicodedata.name(chr(cp))
    except ValueError:
        return "<未命名字符>"


def css_snippet(order: list[str]) -> str:
    quoted = ", ".join(f'"{n}"' for n in order)
    return f"font-family: {quoted}, sans-serif;" if quoted else "font-family: sans-serif;"


def _diag(code: str, severity: str, message: str, fix: str | None = None) -> dict:
    return {"code": code, "severity": severity, "message": message, "fix": fix}


def cluster_kind(cluster: str) -> str | None:
    """识别组合簇类型；单码点簇返回 None。"""
    if len(cluster) <= 1:
        return None
    props = [gcb.gcb(ord(c)) for c in cluster]
    if gcb.ZWJ in props and any(p == gcb.EXT_PICT for p in props):
        return "emoji ZWJ 序列"
    if all(p == gcb.RI for p in props):
        return "区域指示符（旗帜）"
    if any(0xE0020 <= ord(c) <= 0xE007F for c in cluster):
        return "TAG 标签序列"
    if any(p in (gcb.EXTEND, gcb.SPACING_MARK) for p in props[1:]):
        return "组合字符（基字 + 附加符号）"
    return "多码点簇"


def cluster_diagnostics(
    cluster: str,
    resolved: dict,
    fonts: dict[str, Font],
    order: list[str],
) -> list[dict]:
    diags: list[dict] = []
    cps: list[int] = resolved["codepoints"]
    uncovered: list[int] = resolved["uncovered"]
    status: str = resolved["status"]
    kind = cluster_kind(cluster)

    # 缺字：任何字体都不覆盖的码点
    for cp in uncovered:
        block = block_name(cp)
        diags.append(
            _diag(
                "MISSING_GLYPH",
                "error",
                f"{fmt_cp(cp)}（{cp_name(cp)}）不在任何字体的覆盖范围内，"
                f"所属区块：{block}。",
                fix=(
                    f"在覆盖清单中添加一款覆盖 {fmt_cp(cp)}（{block}）的字体并加入优先级列表，"
                    f"例如为某字体增加范围 \"{fmt_cp(cp)}\"。\n"
                    f"CSS 参考：{css_snippet(order)}"
                ),
            )
        )

    # 部分覆盖：没有单一字体能覆盖整个簇
    if status == "partial":
        best = resolved["best_partial_font"]
        per_cp = []
        for cp in cps:
            holders = [n for n in order if fonts[n].covers(cp)]
            per_cp.append(f"{fmt_cp(cp)} → {holders[0] if holders else '无'}")
        diags.append(
            _diag(
                "PARTIAL_COVERAGE",
                "warning",
                f"没有单一字体覆盖整个簇，将由多个字体拆分渲染"
                f"（最佳部分匹配：{best}）：" + "；".join(per_cp) + "。",
                fix=(
                    "为簇内全部码点选择同一款字体，避免拆分渲染导致的字形不一致。\n"
                    f"CSS 参考：{css_snippet(order)}"
                ),
            )
        )

    # 组合字符簇
    if kind is not None:
        if status == "ok":
            diags.append(
                _diag(
                    "COMBINING_CLUSTER",
                    "info",
                    f"组合字符簇（{kind}，{len(cps)} 个码点）整体由 "
                    f"“{resolved['resolved_font']}” 渲染，回退一致。",
                )
            )
        else:
            diags.append(
                _diag(
                    "COMBINING_SPLIT",
                    "warning",
                    f"组合字符簇（{kind}，{len(cps)} 个码点）无法由单一字体渲染，"
                    "基字与附加符号可能来自不同字体，易出现错位或豆腐块。",
                    fix=(
                        "确保目标字体同时覆盖基字与全部附加码点："
                        + " ".join(fmt_cp(cp) for cp in cps)
                        + "；或提高同时覆盖它们的字体在优先级中的位置。\n"
                        f"CSS 参考：{css_snippet(order)}"
                    ),
                )
            )

    return diags


def global_diagnostics(
    fonts: dict[str, Font],
    priority: list[str],
    order: list[str],
    cycles: list[list[str]],
    unknown: list[str],
    duplicates: list[str],
    manifest_errors: list[str],
) -> list[dict]:
    diags: list[dict] = []

    for err in manifest_errors:
        diags.append(_diag("MANIFEST_ERROR", "error", f"覆盖清单错误：{err}"))

    if not priority and not manifest_errors:
        diags.append(
            _diag(
                "EMPTY_STACK",
                "error",
                "字体优先级列表为空，所有字符都无法解析。",
                fix="在优先级编辑器中至少添加一个清单中已定义的字体名称。",
            )
        )

    for cyc in cycles:
        path = " → ".join(f"“{n}”" for n in cyc)
        last, nxt = cyc[-2], cyc[-1]
        diags.append(
            _diag(
                "PRIORITY_CYCLE",
                "error",
                f"检测到优先级循环：{path}。解析时已在回边处截断，"
                "循环内的字体可能永远轮不到。",
                fix=(
                    f"删除字体 “{last}” 的 \"fallbackTo\": \"{nxt}\" 以断开循环，"
                    "或改为指向链外字体。"
                ),
            )
        )

    for name in unknown:
        diags.append(
            _diag(
                "UNKNOWN_FONT",
                "warning",
                f"优先级或 fallbackTo 引用了未在清单中定义的字体 “{name}”，已跳过。",
                fix=f"在清单 fonts 数组中补充 “{name}” 的定义，或从优先级列表移除。",
            )
        )

    for name in duplicates:
        diags.append(
            _diag(
                "DUPLICATE_FONT",
                "info",
                f"字体 “{name}” 在优先级列表中出现多次，后续出现已被忽略。",
                fix=f"从优先级列表中删除重复的 “{name}”。",
            )
        )

    for name in fonts:
        if order and name not in order:
            diags.append(
                _diag(
                    "UNUSED_FONT",
                    "info",
                    f"字体 “{name}” 已在清单中定义，但不在任何解析路径上。",
                    fix=f"如需参与回退，将 “{name}” 加入优先级列表或被引用字体的 fallbackTo。",
                )
            )

    return diags
