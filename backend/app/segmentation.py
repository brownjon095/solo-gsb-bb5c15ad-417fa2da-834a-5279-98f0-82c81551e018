"""Grapheme cluster segmentation and per-codepoint annotation."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

import regex

# Grapheme cluster boundary: \X from UAX #29 as implemented by the `regex` module.
_GRAPHEME_RE = regex.compile(r"\X")

ZWJ = 0x200D
ZWNJ = 0x200C

VARIATION_SELECTORS = {*range(0xFE00, 0xFE10), *range(0xE0100, 0xE01F0)}
EMOJI_MODIFIERS = set(range(0x1F3FB, 0x1F400))
REGIONAL_INDICATORS = set(range(0x1F1E6, 0x1F200))
KEYCAP_ENCLOSING = 0x20E3


def cp_hex(cp: int) -> str:
    return f"U+{cp:04X}" if cp <= 0xFFFF else f"U+{cp:0X}"


def cp_name(cp: int) -> str:
    try:
        return unicodedata.name(chr(cp))
    except ValueError:
        if 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD:
            return "<private use>"
        if cp == 0x00A0:
            return "NO-BREAK SPACE"
        return f"<unnamed codepoint {cp_hex(cp)}>"


def category(cp: int) -> str:
    return unicodedata.category(chr(cp))


def is_combining_mark(cp: int) -> bool:
    """General categories Mn/Me/Mc — attached combining characters."""
    return category(cp)[0] == "M"


def is_variation_selector(cp: int) -> bool:
    return cp in VARIATION_SELECTORS


def is_join_control(cp: int) -> bool:
    return cp in (ZWJ, ZWNJ)


def role_of(index: int, cp: int) -> str:
    if index == 0:
        return "base"
    if cp in EMOJI_MODIFIERS:
        return "emoji-modifier"
    if cp in REGIONAL_INDICATORS:
        return "regional-indicator"
    if cp == KEYCAP_ENCLOSING:
        return "combining-enclosing-keycap"
    if is_variation_selector(cp):
        return "variation-selector"
    if is_join_control(cp):
        return "join-control"
    if is_combining_mark(cp):
        return "combining-mark"
    return "sequence-member"


@dataclass
class CodepointInfo:
    cp: int
    hex: str
    char: str
    name: str
    block: str | None
    category: str
    combining_class: int
    role: str

    def to_dict(self) -> dict:
        return {
            "cp": self.hex,
            "value": self.cp,
            "char": self.char,
            "name": self.name,
            "block": self.block,
            "category": self.category,
            "ccc": self.combining_class,
            "role": self.role,
        }


@dataclass
class Cluster:
    index: int
    text: str
    start: int
    end: int
    codepoints: list[CodepointInfo] = field(default_factory=list)

    @property
    def base(self) -> CodepointInfo:
        return self.codepoints[0]

    @property
    def marks(self) -> list[CodepointInfo]:
        return [c for c in self.codepoints[1:] if c.role in
                ("combining-mark", "emoji-modifier", "combining-enclosing-keycap",
                 "variation-selector")]

    @property
    def has_combining(self) -> bool:
        return any(c.role in ("combining-mark", "combining-enclosing-keycap") for c in self.codepoints)

    @property
    def has_zwj(self) -> bool:
        return any(c.cp == ZWJ for c in self.codepoints)

    @property
    def kind(self) -> str:
        cps = self.codepoints
        if len(cps) == 1:
            return "single"
        if any(c.role == "regional-indicator" for c in cps):
            return "flag-or-tag"
        if self.has_zwj:
            return "zwj-sequence"
        if any(c.role == "emoji-modifier" for c in cps):
            return "emoji-modifier-sequence"
        if any(c.role == "variation-selector" for c in cps):
            return "variation-sequence"
        if self.has_combining:
            return "combining-sequence"
        return "cluster"


def segment(text: str) -> list[Cluster]:
    """Split *text* into extended grapheme clusters (UAX #29) with annotations."""
    from .unicode_blocks import block_for

    clusters: list[Cluster] = []
    pos = 0
    for idx, m in enumerate(_GRAPHEME_RE.finditer(text)):
        piece = m.group(0)
        infos: list[CodepointInfo] = []
        for j, ch in enumerate(piece):
            cp = ord(ch)
            infos.append(
                CodepointInfo(
                    cp=cp,
                    hex=cp_hex(cp),
                    char=ch,
                    name=cp_name(cp),
                    block=block_for(cp),
                    category=category(cp),
                    combining_class=unicodedata.combining(ch),
                    role=role_of(j, cp),
                )
            )
        clusters.append(Cluster(index=idx, text=piece, start=pos, end=pos + len(piece),
                                codepoints=infos))
        pos += len(piece)
    return clusters
