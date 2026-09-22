"""字素簇切分入口：优先使用 `regex` 库的完整 UAX #29 实现，
未安装时回退到内置的纯 Python 实现（app.gcb）。"""
from __future__ import annotations

from . import gcb

try:  # pragma: no cover - 取决于运行环境
    import regex as _regex
except ImportError:  # pragma: no cover
    _regex = None


def grapheme_clusters(text: str) -> list[str]:
    if _regex is not None:
        return _regex.findall(r"\X", text)
    return gcb.grapheme_clusters(text)


def backend_name() -> str:
    return "regex(\\X)" if _regex is not None else "builtin"
