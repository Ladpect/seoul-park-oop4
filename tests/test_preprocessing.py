import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "preprocessing") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "preprocessing"))

from extract_age_data import AGE_GROUPS, AgePopPreprocessor
from newdata import (
    CsvSource,
    DaytimePopPreprocessor,
    HolidayCalendar,
    MonthlyPopSource,
    ParkMapper,
    PreprocessConfig,
)


class _FakeParkSource(CsvSource):
    """테스트용 인메모리 공원 데이터 소스 (DIP 검증)"""

    def __init__(self, df: pd.DataFrame):
        self.fpath = Path("fake_parks.csv")
        self._df = df

    def load(self) -> pd.DataFrame:
        return self._df.copy()


class _FakeMonthlyPopSource(MonthlyPopSource):
    """테스트용 인메모리 월별 생활인구 소스"""

    def __init__(self, year: int, month: int, df: pd.DataFrame):
        self.fpath = Path(f"fake_{year}{month:02d}.csv")
        self.year = year
        self.month = month
        self._df = df

    def load(self) -> pd.DataFrame:
        return self._df.copy()


class TestHolidayCalendar(unittest.TestCase):
    def setUp(self):
        self.cal = HolidayCalendar()

    def test_rest_day_and_excluded(self):
        dates = pd.Series(pd.to_datetime([
            "2025-05-03",  # 토요일
            "2025-05-05",  # 어린이날(월, 공휴일)
            "2025-05-07",  # 평일(수)
            "2025-01-28",  # 설 연휴 제외일
        ]))
        self.assertEqual(self.cal.is_rest_day(dates).tolist(), [True, True, False, False])
        self.assertEqual(self.cal.is_excluded(dates).tolist(), [False, False, False, True])


class TestParkMapper(unittest.TestCase):
    def test_restrict_to_preserves_original_parks(self):
        parks_df = pd.DataFrame({
            "park_nm": ["서울숲", "보라매공원", "개편공원"],
            "dong_cd": ["11200650", "11590680", "99999999"],
        })
        mapper = ParkMapper(_FakeParkSource(parks_df))
        excluded = mapper.restrict_to({"11200650", "11590680", "11110515"})

        self.assertEqual(len(mapper.parks), 3)
        self.assertEqual(mapper.park_dongs, {"11200650", "11590680"})
        self.assertEqual(excluded["park_nm"].tolist(), ["개편공원"])
        self.assertEqual(
            mapper.has_park(pd.Series(["11200650", "11110515", "99999999"])).tolist(),
            [True, False, False],
        )


class TestPreprocessors(unittest.TestCase):
    def setUp(self):
        self.cal = HolidayCalendar()
        self.config = PreprocessConfig(years=[2025], months={1: "winter", 5: "spring"})
        self.mapper = ParkMapper(_FakeParkSource(pd.DataFrame({
            "park_nm": ["서울숲"],
            "dong_cd": ["11200650"],
        })))

    def test_daytime_preprocessor_filters_hours_and_holidays(self):
        raw = pd.DataFrame({
            "date": pd.to_datetime(["2025-01-28", "2025-01-11", "2025-01-11", "2025-01-11"]),
            "hour": [12, 8, 12, 14],   # 설 연휴(제외), 08시(제외), 12시/14시(포함)
            "dong_cd": ["11200650", "11200650", "11200650", "11110515"],
            "pop": [9999.0, 5000.0, 200.0, 100.0],
        })
        prep = DaytimePopPreprocessor(self.config, self.cal)
        out = prep.run(self.mapper, sources=[_FakeMonthlyPopSource(2025, 1, raw)])

        self.assertEqual(len(out), 2)
        park_row = out[out["dong_cd"] == "11200650"].iloc[0]
        none_row = out[out["dong_cd"] == "11110515"].iloc[0]
        self.assertTrue(park_row["has_park"])
        self.assertFalse(none_row["has_park"])
        self.assertAlmostEqual(park_row["pop"], 200.0)

    def test_age_preprocessor_inherits_pipeline_and_melts_groups(self):
        raw = pd.DataFrame({
            "date": pd.to_datetime(["2025-05-10"]),
            "hour": [13],
            "dong_cd": ["11200650"],
            "kids": [10.0], "teens": [20.0], "youth": [30.0],
            "middle": [40.0], "senior": [50.0], "total": [150.0],
        })
        prep = AgePopPreprocessor(self.config, self.cal)
        out = prep.run(self.mapper, sources=[_FakeMonthlyPopSource(2025, 5, raw)])

        self.assertEqual(len(out), len(AGE_GROUPS))
        self.assertSetEqual(set(out["age_group"]), set(AGE_GROUPS.values()))
        self.assertTrue(out["has_park"].all())


if __name__ == "__main__":
    unittest.main()
