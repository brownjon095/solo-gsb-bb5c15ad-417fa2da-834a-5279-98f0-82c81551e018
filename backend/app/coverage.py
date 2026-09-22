"""字体覆盖清单的解析与覆盖判定。

清单格式（JSON）：
{
  "fonts": [
    {
      "name": "Acme Sans",
      "coverage": ["U+0020-U+007E", "U+0300"],   // 区间或单码点
      "fallbackTo": "Acme CJK"                    // 可选：未命中时的跳转
    }
  ],
  "priority": ["Acme Sans", "Acme CJK"]           // 可选：默认优先级
}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_RANGE_RE = re.compile(
    r"^U\+([0-9A-Fa-f]{4,6})(?:\s*-\s*(?:U\+)?([0-9A-Fa-f]{4,6}))?$"
)


@dataclass
class Font:
    name: str
    ranges: list[tuple[int, int]] = field(default_factory=list)
    fallback_to: str | None = None

    def covers(self, cp: int) -> bool:
        return any(lo <= cp <= hi for lo, hi in self.ranges)

    @property
    def codepoint_count(self) -> int:
        return sum(hi - lo + 1 for lo, hi in self.ranges)


def parse_range(token: str) -> tuple[int, int] | None:
    """解析 'U+4E00-U+9FFF' 或 'U+0300'，失败返回 None。"""
    m = _RANGE_RE.match(token.strip())
    if not m:
        return None
    lo = int(m.group(1), 16)
    hi = int(m.group(2), 16) if m.group(2) else lo
    if lo > hi or hi > 0x10FFFF:
        return None
    return (lo, hi)


def parse_manifest(data: dict) -> tuple[dict[str, Font], list[str], list[str]]:
    """解析清单，返回 (字体表, 错误列表, 清单内默认优先级)。"""
    errors: list[str] = []
    fonts: dict[str, Font] = {}
    priority: list[str] = []

    if not isinstance(data, dict):
        return {}, ["清单必须是 JSON 对象"], []

    raw_fonts = data.get("fonts")
    if not isinstance(raw_fonts, list) or not raw_fonts:
        errors.append("清单缺少非空的 fonts 数组")
        raw_fonts = []

    for i, entry in enumerate(raw_fonts):
        where = f"fonts[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: 必须是对象")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{where}: 缺少有效的 name 字段")
            continue
        name = name.strip()
        if name in fonts:
            errors.append(f"{where}: 字体名称 “{name}” 重复定义")
            continue
        font = Font(name=name)
        raw_cov = entry.get("coverage", [])
        if not isinstance(raw_cov, list) or not raw_cov:
            errors.append(f"{where}（{name}）: coverage 必须是非空数组")
        else:
            for token in raw_cov:
                if not isinstance(token, str):
                    errors.append(f"{where}（{name}）: coverage 项必须是字符串")
                    continue
                parsed = parse_range(token)
                if parsed is None:
                    errors.append(
                        f"{where}（{name}）: 无法解析的范围 “{token}”，"
                        "应为 U+XXXX 或 U+XXXX-U+XXXX"
                    )
                else:
                    font.ranges.append(parsed)
        fb = entry.get("fallbackTo")
        if fb is not None:
            if not isinstance(fb, str) or not fb.strip():
                errors.append(f"{where}（{name}）: fallbackTo 必须是非空字符串")
            else:
                font.fallback_to = fb.strip()
        fonts[name] = font

    raw_priority = data.get("priority", [])
    if raw_priority is not None:
        if not isinstance(raw_priority, list) or not all(
            isinstance(p, str) for p in raw_priority
        ):
            errors.append("priority 必须是字符串数组")
        else:
            priority = [p.strip() for p in raw_priority if p.strip()]

    return fonts, errors, priority
