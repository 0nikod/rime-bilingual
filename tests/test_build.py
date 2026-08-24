from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bilingual_build", ROOT / "scripts" / "build.py")
assert SPEC and SPEC.loader
build_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build_module
SPEC.loader.exec_module(build_module)


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("opencc_dict"):
            raise RuntimeError("opencc_dict is required to run build tests")

    def setUp(self) -> None:
        self.cedict = ROOT / "tests" / "fixtures" / "cedict_sample.txt"
        self.ecdict = ROOT / "tests" / "fixtures" / "ecdict_sample.csv"

    @staticmethod
    def dictionary(path: Path) -> dict[str, list[str]]:
        return build_module.read_text_dictionary(path)

    def test_builds_both_directions_and_preserves_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = build_module.build(self.cedict, self.ecdict, output)

            self.assertIn("malformed CC-CEDICT line", stderr.getvalue())
            for stem in ("bilingual_zh_en", "bilingual_en_zh"):
                self.assertGreater((output / f"{stem}.ocd2").stat().st_size, 0)
                config = json.loads((output / f"{stem}.json").read_text(encoding="utf-8"))
                self.assertEqual(list(config), ["name", "conversion_chain"])
                self.assertNotIn("segmentation", config)
                self.assertEqual(len(config["conversion_chain"]), 1)
                self.assertEqual(
                    config["conversion_chain"][0]["dict"],
                    {"type": "ocd2", "file": f"{stem}.ocd2"},
                )

            zh = self.dictionary(output / "bilingual_zh_en.txt")
            en = self.dictionary(output / "bilingual_en_zh.txt")
            self.assertEqual(zh["你好"], ["hello", "hi"])
            self.assertEqual(zh["学习"], ["study", "learn", "to\u00a0learn"])
            self.assertEqual(zh["输入法"], ["input\u00a0method", "typing\u00a0method"])
            self.assertNotIn("CL:個|个[ge4]", zh["你好"])
            self.assertEqual(en["computer"], ["计算机", "电脑"])
            self.assertEqual(en["escaped"], ["电脑", "计算机"])
            self.assertNotIn("Computer", en)
            self.assertEqual(en["study"], ["学习", "研究", "研习"])
            self.assertEqual(en["typing"][0], "打字\u00a0方法")
            self.assertEqual(result["cedict"].malformed, 1)
            self.assertEqual(result["ecdict"].malformed, 1)
            self.assertGreaterEqual(result["ecdict"].skipped, 2)
            self.assertGreaterEqual(result["ecdict"].removed_invalid, 1)
            self.assertGreaterEqual(result["cedict"].removed_duplicate, 1)
            self.assertGreaterEqual(result["cedict"].removed_long, 1)
            self.assertEqual(
                set(result["validations"]), {"zh_to_en", "en_to_zh"}
            )

    def test_length_and_count_limits_are_applied_in_source_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            build_module.build(
                self.cedict,
                self.ecdict,
                output,
                max_translation_length=12,
                max_translations_per_entry=2,
            )
            zh = self.dictionary(output / "bilingual_zh_en.txt")
            en = self.dictionary(output / "bilingual_en_zh.txt")
            self.assertEqual(zh["学习"], ["study", "learn"])
            self.assertEqual(en["study"], ["学习", "研究"])
            self.assertEqual(zh["冗长"], ["long"])
            self.assertNotIn("longword", en)
            self.assertTrue(all(len(values) <= 2 for values in zh.values()))
            self.assertTrue(all(len(values) <= 2 for values in en.values()))

    def test_excessive_parse_errors_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad = Path(temporary) / "bad.txt"
            bad.write_text("not cedict\nalso bad\n甲 甲 [jia3] /one/\n", encoding="utf-8")
            entries, stats = build_module.parse_cedict(bad)
            self.assertIn("甲", entries)
            with self.assertRaises(build_module.BuildError):
                build_module.check_parse_ratio(stats)


if __name__ == "__main__":
    unittest.main()
