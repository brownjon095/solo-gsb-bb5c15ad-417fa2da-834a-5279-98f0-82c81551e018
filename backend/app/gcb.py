"""纯 Python 的 Unicode 字素簇（grapheme cluster）切分。

实现 UAX #29 的核心断行规则（GB1–GB13）的实用子集，覆盖：
  - 组合附加符号（Extend / SpacingMark）
  - emoji 修饰符、变体选择符、TAG 序列
  - ZWJ emoji 序列（GB11）
  - 区域指示符成对旗帜（GB12/13）
  - 谚文（Hangul）字母组合（GB6–GB8）

运行环境若安装了 `regex` 库，segmenter 会优先使用其 \\X 实现
（完整 UAX #29）；本模块作为零依赖回退，并供单元测试使用。
"""
from __future__ import annotations

import unicodedata

# Grapheme_Cluster_Break 属性值
OTHER = "Other"
PREPEND = "Prepend"
CR = "CR"
LF = "LF"
CONTROL = "Control"
EXTEND = "Extend"
ZWJ = "ZWJ"
RI = "Regional_Indicator"
SPACING_MARK = "SpacingMark"
L = "L"
V = "V"
T = "T"
LV = "LV"
LVT = "LVT"
EXT_PICT = "Extended_Pictographic"


def _in_ranges(cp: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


# Prepend：阿拉伯数字符号等（GB9b 左侧）
_PREPEND_RANGES: tuple[tuple[int, int], ...] = (
    (0x0600, 0x0605),
    (0x06DD, 0x06DD),
    (0x070F, 0x070F),
    (0x08E2, 0x08E2),
    (0x0D4E, 0x0D4E),
    (0x110BD, 0x110BD),
    (0x111C2, 0x111C3),
    (0x1193D, 0x1193D),
    (0x11941, 0x11941),
    (0x11A3A, 0x11A3A),
    (0x11A84, 0x11A89),
    (0x11D46, 0x11D46),
    (0x11F02, 0x11F02),
)

# 通用类别之外的 Extend 补充（Mn/Me 已由类别判断覆盖）
_EXTEND_EXTRA: tuple[tuple[int, int], ...] = (
    (0x200C, 0x200C),        # ZWNJ
    (0x302E, 0x302F),        # Hangul tone marks
    (0xFF9E, 0xFF9F),        # halfwidth voicing marks
    (0x1F3FB, 0x1F3FF),      # emoji skin tone modifiers (Sk)
    (0xE0020, 0xE007F),      # TAG characters (Cf)
)

# 通用类别之外的 SpacingMark 补充（Mc 已由类别判断覆盖）
_SPACING_MARK_EXTRA: tuple[tuple[int, int], ...] = (
    (0x0E33, 0x0E33),        # THAI CHARACTER SARA AM (Lo)
    (0x0EB3, 0x0EB3),        # LAO VOWEL SIGN AM (Lo)
)

# 各印度系文字的 virama/halant（GB9c 连字规则的 Linker，实用近似）
_VIRAMAS: frozenset[int] = frozenset(
    {
        0x094D,  # DEVANAGARI SIGN VIRAMA
        0x09CD,  # BENGALI
        0x0A4D,  # GURMUKHI
        0x0ACD,  # GUJARATI
        0x0B4D,  # ORIYA
        0x0BCD,  # TAMIL
        0x0C4D,  # TELUGU
        0x0CCD,  # KANNADA
        0x0D4D,  # MALAYALAM
        0x0DCA,  # SINHALA
        0x0F84,  # TIBETAN
        0x1039, 0x103A,  # MYANMAR
        0x1714, 0x1734,  # TAGALOG / HANUNOO
        0x1A60,  # TAI THAM
        0x1B44,  # BALINESE
        0xA9C0,  # JAVANESE
        0x11046,  # BRAHMI
        0x11133, 0x11134,  # CHAKMA
        0x111C0,  # SHARADA
        0x11235,  # KHOJKI
        0x112EA,  # KHUDAWADI
        0x1134D,  # GRANTHA
        0x11442,  # NEWA
        0x114C2,  # TIRHUTA
        0x115BF,  # SIDDHAM
        0x1163F,  # MODI
        0x116B6,  # TAKRI
        0x1172B,  # AHOM
        0x11839,  # DOGRA
        0x1193D,  # DIVES AKURU
        0x119E0,  # NANDINAGARI
        0x11A34,  # ZANABAZAR SQUARE
        0x11A47,  # SOYOMBO
        0x11A99,  # MASARAM GONDI
        0x11C3F,  # BHAIKSUKI
        0x11D44, 0x11D45,  # MASARAM GONDI
        0x11D97,  # GUNJALA GONDI
    }
)

# Extended_Pictographic 的主要区间（实用近似）
_EXT_PICT_RANGES: tuple[tuple[int, int], ...] = (
    (0x00A9, 0x00A9),
    (0x00AE, 0x00AE),
    (0x203C, 0x203C),
    (0x2049, 0x2049),
    (0x2122, 0x2122),
    (0x2139, 0x2139),
    (0x2194, 0x2199),
    (0x21A9, 0x21AA),
    (0x231A, 0x231B),
    (0x2328, 0x2328),
    (0x23CF, 0x23CF),
    (0x23E9, 0x23F3),
    (0x23F8, 0x23FA),
    (0x24C2, 0x24C2),
    (0x25AA, 0x25AB),
    (0x25B6, 0x25B6),
    (0x25C0, 0x25C0),
    (0x25FB, 0x25FE),
    (0x2600, 0x27BF),
    (0x2934, 0x2935),
    (0x2B05, 0x2B07),
    (0x2B1B, 0x2B1C),
    (0x2B50, 0x2B50),
    (0x2B55, 0x2B55),
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3297),
    (0x3299, 0x3299),
    (0x1F000, 0x1FAFF),
)


def gcb(cp: int) -> str:
    """返回码点的 Grapheme_Cluster_Break 属性（近似实现）。"""
    if cp == 0x0D:
        return CR
    if cp == 0x0A:
        return LF
    if cp == 0x200D:
        return ZWJ
    if 0x1F1E6 <= cp <= 0x1F1FF:
        return RI
    # 谚文
    if 0x1100 <= cp <= 0x115F or 0xA960 <= cp <= 0xA97C:
        return L
    if 0x1160 <= cp <= 0x11A7 or 0xD7B0 <= cp <= 0xD7C6:
        return V
    if 0x11A8 <= cp <= 0x11FF or 0xD7CB <= cp <= 0xD7FB:
        return T
    if 0xAC00 <= cp <= 0xD7A3:
        return LV if (cp - 0xAC00) % 28 == 0 else LVT
    if _in_ranges(cp, _PREPEND_RANGES):
        return PREPEND
    if _in_ranges(cp, _EXTEND_EXTRA):
        return EXTEND
    if _in_ranges(cp, _SPACING_MARK_EXTRA):
        return SPACING_MARK
    if _in_ranges(cp, _EXT_PICT_RANGES):
        return EXT_PICT
    cat = unicodedata.category(chr(cp))
    if cat in ("Mn", "Me"):
        return EXTEND
    if cat == "Mc":
        return SPACING_MARK
    if cat in ("Cc", "Cf", "Zl", "Zp", "Cs"):
        return CONTROL
    return OTHER


def grapheme_clusters(text: str) -> list[str]:
    """按 UAX #29 规则把文本切成字素簇列表。"""
    clusters: list[str] = []
    current = ""
    props: list[str] = []  # 当前簇内各码点的属性

    for ch in text:
        p = gcb(ord(ch))
        if not current:
            current = ch
            props = [p]
            continue
        if _should_break(current, props, ch, p):
            clusters.append(current)
            current = ch
            props = [p]
        else:
            current += ch
            props.append(p)
    if current:
        clusters.append(current)
    return clusters


def _should_break(current: str, props: list[str], ch: str, cur: str) -> bool:
    """判断当前簇末尾（props[-1]）与新码点（属性 cur）之间是否断开。"""
    prev = props[-1]
    # GB3: CR × LF
    if prev == CR and cur == LF:
        return False
    # GB4 / GB5
    if prev in (CONTROL, CR, LF) or cur in (CONTROL, CR, LF):
        return True
    # GB6
    if prev == L and cur in (L, V, LV, LVT):
        return False
    # GB7
    if prev in (LV, V) and cur in (V, T):
        return False
    # GB8
    if prev in (LVT, T) and cur == T:
        return False
    # GB9: × (Extend | ZWJ)
    if cur in (EXTEND, ZWJ):
        return False
    # GB9a: × SpacingMark
    if cur == SPACING_MARK:
        return False
    # GB9b: Prepend ×
    if prev == PREPEND:
        return False
    # GB9c（近似）: virama (Extend*) × 辅音字母 —— 印度系文字连字
    if unicodedata.category(ch) == "Lo":
        i = len(current) - 1
        while i >= 0 and props[i] in (EXTEND, ZWJ):
            if ord(current[i]) in _VIRAMAS:
                return False
            i -= 1
    # GB11: ExtPict Extend* ZWJ × ExtPict
    if cur == EXT_PICT and prev == ZWJ:
        i = len(props) - 2
        while i >= 0 and props[i] == EXTEND:
            i -= 1
        if i >= 0 and props[i] == EXT_PICT:
            return False
    # GB12/13: RI × RI（成对）
    if prev == RI and cur == RI:
        count = 0
        i = len(props) - 1
        while i >= 0 and props[i] == RI:
            count += 1
            i -= 1
        if count % 2 == 1:
            return False
    return True
