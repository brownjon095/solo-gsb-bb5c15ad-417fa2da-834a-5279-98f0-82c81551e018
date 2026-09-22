"""核心逻辑单元测试（仅依赖标准库，直接运行：
    python3 -m unittest discover -s backend/tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import gcb, segmenter  # noqa: E402
from app.coverage import parse_manifest  # noqa: E402
from app.resolver import build_effective_order, resolve_cluster  # noqa: E402
from app.service import run_diagnose  # noqa: E402


class TestGraphemeClusters(unittest.TestCase):
    def clusters(self, text):
        # 固定使用内置实现，保证无第三方依赖时也可测试
        return gcb.grapheme_clusters(text)

    def test_ascii(self):
        self.assertEqual(self.clusters("abc"), ["a", "b", "c"])

    def test_combining_mark(self):
        # e + U+0301 组合 acute
        self.assertEqual(self.clusters("café"), ["c", "a", "f", "é"])

    def test_devanagari_conjunct(self):
        # स + ् + त + े 构成一个簇
        self.assertIn("स्ते", self.clusters("नमस्ते"))

    def test_emoji_zwj_sequence(self):
        fam = "👨‍👩‍👧‍👦"
        self.assertEqual(self.clusters(fam), [fam])

    def test_flag_pairs(self):
        self.assertEqual(self.clusters("🇨🇳🇯🇵"), ["🇨🇳", "🇯🇵"])

    def test_emoji_modifier(self):
        wave = "👋🏽"
        self.assertEqual(self.clusters(wave), [wave])

    def test_hangul_jamo(self):
        # ᄀ + ᅡ + ᆨ 组合音节
        self.assertEqual(self.clusters("각"), ["각"])

    def test_crlf_single_cluster(self):
        self.assertEqual(self.clusters("a\r\nb"), ["a", "\r\n", "b"])

    def test_mixed_script(self):
        self.assertEqual(self.clusters("Hi你好"), ["H", "i", "你", "好"])

    def test_segmenter_module_fallback(self):
        # segmenter 模块在无 regex 时也能工作
        self.assertTrue(segmenter.grapheme_clusters("ab"))


MANIFEST = {
    "fonts": [
        {"name": "Latin", "coverage": ["U+0020-U+007E"], "fallbackTo": "CJK"},
        {"name": "CJK", "coverage": ["U+4E00-U+9FFF"], "fallbackTo": "Emoji"},
        {"name": "Emoji", "coverage": ["U+1F600-U+1F64F", "U+200D"]},
    ],
    "priority": ["Latin", "CJK", "Emoji"],
}


class TestResolver(unittest.TestCase):
    def setUp(self):
        self.fonts, errors, _ = parse_manifest(MANIFEST)
        self.assertEqual(errors, [])

    def test_priority_order(self):
        order, cycles, unknown, dups = build_effective_order(
            self.fonts, ["Latin", "CJK", "Emoji"]
        )
        self.assertEqual(cycles, [])
        self.assertEqual(unknown, [])
        self.assertEqual(order, ["Latin", "CJK", "Emoji"])

    def test_fallback_chain_extends_order(self):
        # 只给入口字体，fallbackTo 链应补全后续
        order, *_ = build_effective_order(self.fonts, ["Latin"])
        self.assertEqual(order, ["Latin", "CJK", "Emoji"])

    def test_cycle_detection(self):
        fonts, errors, _ = parse_manifest(
            {
                "fonts": [
                    {"name": "A", "coverage": ["U+0041"], "fallbackTo": "B"},
                    {"name": "B", "coverage": ["U+0042"], "fallbackTo": "A"},
                ]
            }
        )
        self.assertEqual(errors, [])
        order, cycles, _, _ = build_effective_order(fonts, ["A"])
        self.assertEqual(order, ["A", "B"])
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0][0], "A")
        self.assertEqual(cycles[0][-1], "A")  # 循环闭合

    def test_unknown_font(self):
        _, _, unknown, _ = build_effective_order(self.fonts, ["Latin", "Ghost"])
        self.assertEqual(unknown, ["Ghost"])

    def test_resolve_hit_and_miss(self):
        order = ["Latin", "CJK", "Emoji"]
        hit = resolve_cluster("你", self.fonts, order)
        self.assertEqual(hit["status"], "ok")
        self.assertEqual(hit["resolved_font"], "CJK")
        self.assertEqual([e["verdict"] for e in hit["chain"]], ["miss", "hit"])

        miss = resolve_cluster("🧬", self.fonts, order)
        self.assertEqual(miss["status"], "missing")
        self.assertEqual(miss["uncovered"], [ord("🧬")])

    def test_partial_coverage(self):
        fonts, _, _ = parse_manifest(
            {
                "fonts": [
                    {"name": "Base", "coverage": ["U+0065"]},          # e
                    {"name": "Marks", "coverage": ["U+0300-U+036F"]},  # ́
                ]
            }
        )
        order = ["Base", "Marks"]
        res = resolve_cluster("é", fonts, order)
        self.assertEqual(res["status"], "partial")
        self.assertEqual(res["best_partial_font"], "Base")
        self.assertEqual(res["uncovered"], [])


class TestDiagnoseService(unittest.TestCase):
    def test_end_to_end(self):
        text = "Hi 你 😀 é"
        out = run_diagnose(text, MANIFEST, None)
        # H i ␣ 你 ␣ 😀 ␣ é(组合) 共 8 个字素簇
        self.assertEqual(out["summary"]["total"], 8)
        by_text = {c["text"]: c for c in out["clusters"]}
        self.assertEqual(by_text["你"]["resolvedFont"], "CJK")
        self.assertEqual(by_text["😀"]["resolvedFont"], "Emoji")
        # é（e + 组合符）无单一字体覆盖 → partial，并给出组合簇诊断
        self.assertEqual(by_text["é"]["status"], "partial")
        codes = {d["code"] for d in by_text["é"]["diagnostics"]}
        self.assertIn("PARTIAL_COVERAGE", codes)
        self.assertIn("COMBINING_SPLIT", codes)

    def test_missing_glyph_fix_mentions_block(self):
        out = run_diagnose("न", MANIFEST, None)
        diags = out["clusters"][0]["diagnostics"]
        missing = [d for d in diags if d["code"] == "MISSING_GLYPH"]
        self.assertTrue(missing)
        self.assertIn("Devanagari", missing[0]["message"])
        self.assertTrue(missing[0]["fix"])

    def test_cycle_reported_globally(self):
        manifest = {
            "fonts": [
                {"name": "A", "coverage": ["U+0041"], "fallbackTo": "B"},
                {"name": "B", "coverage": ["U+0042"], "fallbackTo": "A"},
            ],
            "priority": ["A", "B"],
        }
        out = run_diagnose("AB", manifest, None)
        codes = {d["code"] for d in out["globalDiagnostics"]}
        self.assertIn("PRIORITY_CYCLE", codes)

    def test_manifest_error(self):
        out = run_diagnose("x", {"fonts": []}, None)
        codes = {d["code"] for d in out["globalDiagnostics"]}
        self.assertIn("MANIFEST_ERROR", codes)


if __name__ == "__main__":
    unittest.main()
