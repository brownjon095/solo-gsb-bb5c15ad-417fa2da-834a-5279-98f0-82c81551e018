"""首次加载时提供的示例文本与示例覆盖清单。"""
from __future__ import annotations

SAMPLE_TEXT = (
    "Hello 你好世界！ café नमस्ते 👨‍👩‍👧‍👦 🇨🇳🇯🇵 스튜디오"
)

SAMPLE_MANIFEST = {
    "fonts": [
        {
            "name": "Acme Sans",
            "coverage": ["U+0020-U+007E", "U+00A0-U+00FF", "U+0300-U+036F"],
            "fallbackTo": "Acme CJK",
        },
        {
            "name": "Acme CJK",
            "coverage": [
                "U+3000-U+303F",
                "U+3040-U+30FF",
                "U+4E00-U+9FFF",
                "U+AC00-U+D7AF",
                "U+FF00-U+FFEF",
            ],
            "fallbackTo": "Acme Emoji",
        },
        {
            "name": "Acme Emoji",
            "coverage": [
                "U+1F1E6-U+1F1FF",
                "U+1F300-U+1FAFF",
                "U+2600-U+27BF",
                "U+200D",
                "U+FE0F",
            ],
        },
    ],
    "priority": ["Acme Sans", "Acme CJK", "Acme Emoji"],
}
