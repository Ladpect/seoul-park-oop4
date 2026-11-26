import json
import re
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "analysis") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "analysis"))

from build_dashboard import DashboardBuilder, TranslationCatalog
from newdata import ParkMapper, ParkMapSource
from topic1_visualize import (
    BaseAnalyzer,
    DongNameLookup,
    PARK_MAP_CSV_PATH,
    SEOUL_GEOJSON_PATH,
    SeasonalChangeAnalyzer,
    SeoulParkMapChart,
    map_park_gu,
)
from topic2_visualize import AGE_ORDER, AgeGroupAnalyzer


class _FakeNameLookup:
    """GeoJSON 없이 NameLookup 프로토콜만 구현한 테스트용 조회 객체 (ISP 검증)"""

    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping

    def name(self, dong_cd: str) -> str:
        return self._mapping.get(dong_cd, f"행정동 {dong_cd}")


class _FakeGeoNameLookup(_FakeNameLookup):
    """최소 GeoJSON을 제공하는 대시보드 페이로드 테스트용 조회 객체"""

    def __init__(self, mapping: dict[str, str]):
        super().__init__(mapping)
        self.dong_to_gu = {cd: nm.split()[0] for cd, nm in mapping.items()}
        dong_coords = {
            "11200650": [[[127.03, 37.54], [127.05, 37.54], [127.05, 37.55], [127.03, 37.55], [127.03, 37.54]]],
            "11110515": [[[126.96, 37.58], [126.98, 37.58], [126.98, 37.60], [126.96, 37.60], [126.96, 37.58]]],
        }
        self.geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": cd,
                    "properties": {"dong_cd": cd, "dong_nm": nm, "gu_nm": self.dong_to_gu[cd]},
                    "geometry": {"type": "MultiPolygon", "coordinates": [dong_coords[cd]]},
                }
                for cd, nm in mapping.items()
            ],
        }
        self.gu_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": self.dong_to_gu[cd],
                    "properties": {"gu_nm": self.dong_to_gu[cd]},
                    "geometry": {"type": "MultiPolygon", "coordinates": [dong_coords[cd]]},
                }
                for cd in mapping
            ],
        }


class _FakeParkMapSource:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def load(self) -> pd.DataFrame:
        return self._df.copy()


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

    def test_dashboard_payload_contains_valid_gu_bounds(self):
        mapping = {
            "11200650": "성동구 성수1가1동",
            "11110515": "종로구 청운효자동",
        }
        names = _FakeGeoNameLookup(mapping)
        rows_t1 = [
            {"dong_cd": cd, "year": 2025, "month": m, "is_weekend": True, "pop": 100.0 + m, "n_days": 8, "has_park": True}
            for cd in mapping
            for m in (1, 5)
        ]
        rows_t2 = [
            {"dong_cd": cd, "year": 2025, "month": m, "is_weekend": True, "age_group": age, "pop": 100.0 + m, "has_park": True}
            for cd in mapping
            for m in (1, 5)
            for age in AGE_ORDER
        ]
        parks_df = pd.DataFrame({
            "park_nm": ["서울숲"],
            "rgn": ["광진구"],
            "dong_cd": ["11200650"],
            "area_m2": [1156498],
            "park_addr": ["성동구 뚝섬로 273"],
            "main_fclt": ["산책로"],
        })
        builder = DashboardBuilder(
            SeasonalChangeAnalyzer(pd.DataFrame(rows_t1), names),
            AgeGroupAnalyzer(pd.DataFrame(rows_t2), names),
            names,
            _FakeParkMapSource(parks_df),
            {},
        )
        payload = builder._build_detail_payload()
        gu_bounds = payload["gu_bounds"]

        self.assertIn("ALL", gu_bounds)
        for gu_key in ["ALL", *payload["gus"].keys()]:
            self.assertIn(gu_key, gu_bounds)
            min_lon, max_lon, min_lat, max_lat = gu_bounds[gu_key]
            self.assertLess(min_lon, max_lon)
            self.assertLess(min_lat, max_lat)

        self.assertTrue(payload["parks"])
        park = payload["parks"][0]
        self.assertEqual(park["name_en"], "Seoul Forest")
        self.assertIn("Ttukseom-ro", park["addr_en"])
        self.assertEqual(park["gu"], "성동구")
        self.assertIn(park, payload["gus"]["성동구"]["parks"])
        self.assertEqual(payload["gus"]["성동구"]["name_en"], "Seongdong-gu")
        self.assertEqual(park["dong_nm_en"], "Seongsu 1-ga 1-dong, Seongdong-gu")
        self.assertEqual(park["fclt"], "산책로")

        dong = payload["dongs"]["11200650"]
        self.assertEqual(dong["gu_en"], "Seongdong-gu")
        self.assertEqual(dong["short_en"], "Seongsu 1-ga 1-dong")
        self.assertEqual(dong["name_en"], "Seongsu 1-ga 1-dong, Seongdong-gu")

    def test_unknown_park_dong_code_reports_park_name(self):
        names = _FakeGeoNameLookup({"11200650": "성동구 성수1가1동", "11110515": "종로구 청운효자동"})
        parks_df = pd.DataFrame({
            "park_nm": ["서울숲", "개편공원"],
            "dong_cd": ["11200650", "99999999"],
        })
        with self.assertRaisesRegex(ValueError, r"개편공원\(99999999\)"):
            map_park_gu(parks_df, names.dong_to_gu)
        self.assertEqual(map_park_gu(parks_df.iloc[:1], names.dong_to_gu).tolist(), ["성동구"])

    def test_park_mapping_matches_population_groups_and_map(self):
        names = DongNameLookup()
        park_mapper = ParkMapper(ParkMapSource(PARK_MAP_CSV_PATH))
        for filename in ("daytime_weekend_pop.csv", "daytime_age_pop.csv"):
            with self.subTest(filename=filename):
                path = SEOUL_GEOJSON_PATH.parent / filename
                population = pd.read_csv(path, dtype={"dong_cd": str})
                excluded = park_mapper.restrict_to(set(population["dong_cd"]))
                self.assertTrue(excluded.empty)
                self.assertTrue(population["has_park"].equals(park_mapper.has_park(population["dong_cd"])))

        season = SeasonalChangeAnalyzer(SEOUL_GEOJSON_PATH.parent / "daytime_weekend_pop.csv", names)
        marker_trace = next(
            trace for trace in SeoulParkMapChart(season, names).figure.data
            if trace.type == "scattergeo" and trace.mode == "markers"
        )
        markers = {row[0]: (row[1], lon, lat)
                   for row, lon, lat in zip(marker_trace.customdata, marker_trace.lon, marker_trace.lat)}
        self.assertEqual(markers["답십리근린공원"], ("동대문구", 127.0638172, 37.57332011))
        self.assertEqual(markers["남산공원"][0], "용산구")
        self.assertIn("11230610", park_mapper.park_dongs)
        self.assertNotIn("11680610", park_mapper.park_dongs)

    def test_i18n_catalog_completeness_and_no_hangul(self):
        catalog_path = PROJECT_ROOT / "analysis" / "i18n_en.json"
        self.assertTrue(catalog_path.exists())
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

        geo = json.loads(SEOUL_GEOJSON_PATH.read_text(encoding="utf-8"))
        expected_gus = {f["properties"]["gu_nm"] for f in geo["features"]} | {"강북구 등"}
        expected_dongs = {f["properties"]["dong_cd"] for f in geo["features"]}
        parks_df = pd.read_csv(PARK_MAP_CSV_PATH, dtype={"dong_cd": str})
        expected_parks = set(parks_df["park_nm"].astype(str))

        self.assertEqual(set(catalog["gus"].keys()), expected_gus)
        self.assertEqual(set(catalog["dongs"].keys()), expected_dongs)
        self.assertEqual(set(catalog["parks"].keys()), expected_parks)

        hangul_re = re.compile(r"[\uac00-\ud7a3\u3130-\u318f]")
        for val in catalog["gus"].values():
            self.assertTrue(val)
            self.assertIsNone(hangul_re.search(val))
        for val in catalog["dongs"].values():
            self.assertTrue(val)
            self.assertIsNone(hangul_re.search(val))
        for p in catalog["parks"].values():
            self.assertTrue(p["name_en"])
            self.assertTrue(p["addr_en"])
            self.assertIsNone(hangul_re.search(p["name_en"]))
            self.assertIsNone(hangul_re.search(p["addr_en"]))

    def test_generated_dashboard_has_korean_default_language_toggle(self):
        html_path = PROJECT_ROOT / "docs" / "index.html"
        self.assertTrue(html_path.exists())
        html = html_path.read_text(encoding="utf-8")
        self.assertIn('<html lang="ko">', html)
        self.assertIn('class="lang-btn active" data-lang="ko"', html)
        self.assertIn('class="lang-btn" data-lang="en"', html)
        self.assertIn("let currentLang = 'ko';", html)
        self.assertIn("TranslationCatalog", TranslationCatalog.__name__)


if __name__ == "__main__":
    unittest.main()
