"""Font coverage manifest parsing, validation and alias/cycle analysis.

Manifest JSON shape (see data/sample-coverage.json)::

    {
      "fallback_order": ["Noto Sans", "Noto Sans CJK SC", "Noto Sans Arabic"],
      "default": "LastResort",
      "fonts": {
        "Noto Sans": {
          "ranges": [["U+0020", "U+007E"], "Latin-1 Supplement"],
          "codepoints": ["U+2026", "…"],
          "blocks": ["General Punctuation"],
          "alias_for": "Noto Sans CJK SC"   // optional: redirect this font entry
        }
      }
    }

`ranges` / `blocks` / `codepoints` may appear together and are merged.
A range endpoint is either a ``U+XXXX`` scalar, a literal single-character
string, or an exact Unicode block name (case-insensitive).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .unicode_blocks import block_range

_MAX_CP = 0x10FFFF
_SENTINEL_FONTS = {"LastResort", "last-resort"}


class ManifestError(ValueError):
    """Raised when the coverage manifest is malformed."""


def parse_cp(token: str, *, what: str = "value") -> int:
    """Parse one scalar: ``U+XXXX`` (hex), ``0x..`` hex, or a single char."""
    if not isinstance(token, str) or token == "":
        raise ManifestError(f"invalid {what}: {token!r} (expected U+XXXX or one character)")
    t = token.strip()
    if t.lower().startswith(("u+", "0x")):
        hexs = t[2:]
        if hexs.startswith(("U+", "u+", "0x", "0X")):
            hexs = hexs[2:]
        try:
            cp = int(hexs, 16)
        except ValueError as e:
            raise ManifestError(f"invalid hex scalar {token!r} in {what}") from e
    else:
        if len(t) != 1:
            raise ManifestError(
                f"invalid {what}: {token!r} — use U+XXXX, a block name, or a single character"
            )
        cp = ord(t)
    if cp > _MAX_CP:
        raise ManifestError(f"codepoint U+{cp:04X} out of Unicode range")
    if 0xD800 <= cp <= 0xDFFF:
        raise ManifestError(f"U+{cp:04X} is a surrogate and cannot be covered")
    return cp


def _normalize_intervals(pieces: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge an iterable of inclusive [lo, hi] intervals into disjoint runs."""
    if not pieces:
        return []
    pieces = sorted((min(a, b), max(a, b)) for a, b in pieces)
    out: list[list[int]] = [list(pieces[0])]
    for lo, hi in pieces[1:]:
        if lo <= out[-1][1] + 1:
            if hi > out[-1][1]:
                out[-1][1] = hi
        else:
            out.append([lo, hi])
    return [(a, b) for a, b in out]


def _expand_entry(spec: object, font_name: str) -> list[tuple[int, int]]:
    """Expand one font's coverage spec into inclusive intervals."""
    if spec is None:
        return []
    if isinstance(spec, list):
        spec = {"ranges": spec}
    if not isinstance(spec, dict):
        raise ManifestError(f"font {font_name!r}: coverage entry must be an object or array")

    pieces: list[tuple[int, int]] = []

    for key in ("blocks", "ranges", "codepoints"):
        if key not in spec:
            continue
        val = spec[key]
        if not isinstance(val, list):
            raise ManifestError(f"font {font_name!r}: {key} must be an array")

    for block in spec.get("blocks", []):
        if not isinstance(block, str):
            raise ManifestError(f"font {font_name!r}: block name must be a string, got {block!r}")
        rng = block_range(block)
        if rng is None:
            raise ManifestError(f"font {font_name!r}: unknown Unicode block {block!r}")
        pieces.append(rng)

    for item in spec.get("ranges", []):
        if isinstance(item, str):
            # Bare strings inside ranges are treated as block names.
            rng = block_range(item)
            if rng is not None:
                pieces.append(rng)
                continue
            # Or a single scalar/character.
            cp = parse_cp(item, what=f"range in font {font_name!r}")
            pieces.append((cp, cp))
            continue
        if isinstance(item, (list, tuple)) and len(item) == 2:
            lo = parse_cp(item[0], what=f"range start in font {font_name!r}")
            hi = parse_cp(item[1], what=f"range end in font {font_name!r}")
            pieces.append((lo, hi))
            continue
        raise ManifestError(
            f"font {font_name!r}: range entries must be [start, end] pairs or block names"
        )

    for cp_tok in spec.get("codepoints", []):
        cp = parse_cp(cp_tok, what=f"codepoint in font {font_name!r}")
        pieces.append((cp, cp))

    return _normalize_intervals(pieces)


@dataclass
class FontEntry:
    name: str
    intervals: list[tuple[int, int]] = field(default_factory=list)
    alias_for: str | None = None
    raw: dict = field(default_factory=dict)

    def covers(self, cp: int) -> bool:
        import bisect

        if not self.intervals:
            return False
        starts = [a for a, _ in self.intervals]
        i = bisect.bisect_right(starts, cp) - 1
        return i >= 0 and self.intervals[i][0] <= cp <= self.intervals[i][1]

    def coverage_size(self) -> int:
        return sum(b - a + 1 for a, b in self.intervals)


@dataclass
class Manifest:
    order: list[str]
    default: str | None
    fonts: dict[str, FontEntry]
    warnings: list[str] = field(default_factory=list)

    # ----- alias graph helpers -------------------------------------------------

    def resolve_alias(self, name: str) -> tuple[str | None, list[str], list[dict]]:
        """Follow alias_for links.

        Returns ``(target, chain, cycles)``:
        * target — terminal font name, or None if the chain dangles/cycles;
        * chain — names visited starting with *name*;
        * cycles — one diagnostic dict per detected alias cycle.
        """
        chain: list[str] = []
        seen: dict[str, int] = {}
        cur = name
        cycles: list[dict] = []
        while True:
            if cur in seen:
                cyc = chain[seen[cur]:]
                cycles.append(
                    {
                        "kind": "alias_cycle",
                        "chain": chain + [cur],
                        "cycle": cyc,
                        "message": f"字体别名字体优先级循环：{' → '.join(cyc)} → {cur}",
                    }
                )
                return None, chain + [cur], cycles
            seen[cur] = len(chain)
            chain.append(cur)
            entry = self.fonts.get(cur)
            if entry is None or entry.alias_for is None:
                target = cur if entry is not None else None
                return target, chain, cycles
            cur = entry.alias_for

    def effective_order(self) -> tuple[list[str], list[dict]]:
        """Resolve fallback_order through aliases, dropping dangling/cyclic ones."""
        resolved: list[str] = []
        issues: list[dict] = []
        for name in self.order:
            target, chain, cycles = self.resolve_alias(name)
            issues.extend(cycles)
            if target is None:
                issues.append(
                    {
                        "kind": "dangling_font",
                        "font": name,
                        "message": f"字体 {name!r} 在 fonts 中没有定义，回退时将被跳过",
                    }
                )
                continue
            if target not in resolved:
                resolved.append(target)
            if target != name and target in self.fonts and len(chain) > 1:
                # Note the redirect as informational, not an error.
                pass
        return resolved, issues

    def detect_order_duplicates(self) -> list[dict]:
        seen: set[str] = set()
        dups: list[dict] = []
        for name in self.order:
            if name in seen:
                dups.append(
                    {
                        "kind": "duplicate_priority",
                        "font": name,
                        "message": f"字体 {name!r} 在 fallback_order 中重复出现，第二次将被忽略",
                    }
                )
            seen.add(name)
        return dups


def parse_manifest(data: object) -> Manifest:
    if not isinstance(data, dict):
        raise ManifestError("清单根节点必须是 JSON 对象")

    raw_fonts = data.get("fonts", {})
    if not isinstance(raw_fonts, dict):
        raise ManifestError("fonts 必须是对象：{字体名: 覆盖范围}")

    fonts: dict[str, FontEntry] = {}
    for name, spec in raw_fonts.items():
        if not isinstance(name, str) or not name.strip():
            raise ManifestError(f"非法字体名: {name!r}")
        intervals = _expand_entry(spec, name)
        alias = None
        if isinstance(spec, dict):
            alias = spec.get("alias_for")
            if alias is not None and (not isinstance(alias, str) or not alias.strip()):
                raise ManifestError(f"font {name!r}: alias_for 必须是非空字符串")
        fonts[name] = FontEntry(name=name, intervals=intervals, alias_for=alias,
                                raw=spec if isinstance(spec, dict) else {})

    order = data.get("fallback_order", [])
    if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
        raise ManifestError("fallback_order 必须是字体名字符串数组")

    default = data.get("default")
    if default is not None and not isinstance(default, str):
        raise ManifestError("default 必须是字体名字符串或 null")

    warnings: list[str] = []
    known = set(fonts) | _SENTINEL_FONTS
    probe = Manifest(order=list(order), default=default, fonts=fonts)
    for n in order:
        if n not in known:
            warnings.append(f"fallback_order 中的 {n!r} 未在 fonts 中定义")
    if default and default not in known:
        warnings.append(f"default 字体 {default!r} 未在 fonts 中定义（按末位兜底处理）")
    # Fonts that exist but are never reachable from the order/default list.
    reachable: set[str] = set()
    for seed in [*order, default]:
        if not seed:
            continue
        tgt, chain, _ = probe.resolve_alias(seed)
        reachable.update(chain)
        if tgt:
            reachable.add(tgt)
    for n in fonts:
        if n not in reachable and fonts[n].alias_for is None:
            warnings.append(f"字体 {n!r} 有覆盖数据但不在 fallback_order 中，永远不会被使用")

    return probe
