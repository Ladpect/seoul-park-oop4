import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "analysis") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "analysis"))

from topic1_visualize import BaseAnalyzer, SeasonalChangeAnalyzer
from topic2_visualize import AGE_ORDER, AgeGroupAnalyzer


class _FakeNameLookup:
    """GeoJSON 없이 NameLookup 프로토콜만 구현한 테스트용 조회 객체 (ISP 검증)"""

    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping

    def name(self, dong_cd: str) -> str:
        return self._mapping.get(dong_cd, f"행정동 {dong_cd}")


class TestAnalyzers(unittest.TestCase):
    def setUp(self):
        self.names = _FakeNameLookup({
            "11200650": "성동구 성수1가1동",
            "11200660": "성동구 성수1가2동",
            "11110515": "종로구 청운효자동",
            "11110530": "종로구 사직동",
        })

    def test_base_analyzer_compare_math(self):
        rates = pd.DataFrame({
            "has_park": [True, True, True, False, False, False],
            "rate": [10.0, 12.0, 14.0, 0.0, 1.0, 2.0],
        })
        res = BaseAnalyzer.compare(rates)
        self.assertEqual(res["n_park"], 3)
        self.assertEqual(res["n_none"], 3)
        self.assertAlmostEqual(res["mean_park"], 12.0)
        self.assertAlmostEqual(res["mean_none"], 1.0)
        self.assertAlmostEqual(res["diff"], 11.0)

    def test_lsp_polymorphic_summary_across_analyzers(self):
        rows_t1 = []
        for cd, hp, jan_p, may_p in [
            ("11200650", True, 100.0, 120.0),
            ("11110515", True, 100.0, 110.0),
            ("11200660", False, 100.0, 100.0),
            ("11110530", False, 100.0, 95.0),
        ]:
            for is_wk in [True, False]:
                rows_t1.append({"dong_cd": cd, "year": 2025, "month": 1, "is_weekend": is_wk, "pop": jan_p, "n_days": 8, "has_park": hp})
                rows_t1.append({"dong_cd": cd, "year": 2025, "month": 5, "is_weekend": is_wk, "pop": may_p, "n_days": 8, "has_park": hp})

        rows_t2 = []
        for cd, hp, jan_p, may_p in [
            ("11200650", True, 100.0, 115.0),
            ("11110515", True, 100.0, 110.0),
            ("11200660", False, 100.0, 98.0),
            ("11110530", False, 100.0, 96.0),
        ]:
            for age in AGE_ORDER:
                rows_t2.append({"dong_cd": cd, "year": 2025, "month": 1, "is_weekend": True, "age_group": age, "pop": jan_p, "has_park": hp})
                rows_t2.append({"dong_cd": cd, "year": 2025, "month": 5, "is_weekend": True, "age_group": age, "pop": may_p, "has_park": hp})

        analyzers: list[BaseAnalyzer] = [
            SeasonalChangeAnalyzer(pd.DataFrame(rows_t1), self.names),
            AgeGroupAnalyzer(pd.DataFrame(rows_t2), self.names),
        ]

        # 두 분석기 모두 동일한 BaseAnalyzer.summary() 계약으로 치환 실행 (LSP)
        for analyzer in analyzers:
            summary = analyzer.summary()
            self.assertIn(analyzer.group_col, summary.columns)
            self.assertTrue({"period", "mean_park", "mean_none", "diff"}.issubset(summary.columns))
            self.assertTrue((summary["period"] == "4개년").any())

        # AgeGroupAnalyzer 상세 세대 데이터 검증
        age_details = analyzers[1].dong_age_details()
        self.assertEqual(len(age_details["11200650"]), 5)
        self.assertAlmostEqual(age_details["11200650"][0]["rate"], 15.0)


if __name__ == "__main__":
    unittest.main()
