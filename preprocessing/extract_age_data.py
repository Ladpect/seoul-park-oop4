"""
[주제 2] 세대/연령대별 1월·5월 주말 낮 생활인구 집계 OOP 전처리 파이프라인

1. 파일 내용 (What is inside):
   - AGE_GROUPS: 5개 생애주기 세대 그룹 정의
   - AgeLivingPopSource: MonthlyPopSource를 상속받아 32개 성별/연령별 인구 열을 파싱하고 5대 세대로 합산.
   - AgePopPreprocessor: DaytimePopPreprocessor를 상속받아 세대별 주말 낮 평균 생활인구를 Tidy 포맷으로 정제.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREPROC_DIR = Path(__file__).resolve().parent
if str(PREPROC_DIR) not in sys.path:
    sys.path.insert(0, str(PREPROC_DIR))

from newdata import (
    DaytimePopPreprocessor,
    HolidayCalendar,
    MonthlyPopSource,
    ParkMapSource,
    ParkMapper,
    PreprocessConfig,
)

AGE_GROUPS = {
    "kids": "유아동 (0~9세)",
    "teens": "청소년 (10~19세)",
    "youth": "청년층 (20~39세)",
    "middle": "중장년 (40~59세)",
    "senior": "고령층 (60세 이상)",
    "total": "전체 인구",
}


@dataclass
class AgePreprocessConfig(PreprocessConfig):
    output_file: Path = PROJECT_ROOT / "data" / "processed" / "daytime_age_pop.csv"


class AgeLivingPopSource(MonthlyPopSource):
    """32개 전체 열(성별/연령별 생활인구)을 로드하고 5개 세대 그룹으로 집계"""

    def load(self) -> pd.DataFrame:
        df = self._read_raw()
        df[0] = pd.to_datetime(df[0].str.strip(), format="%Y%m%d", errors="coerce")
        df[1] = pd.to_numeric(df[1], errors="coerce")
        df[2] = self.normalize_dong_cd(df[2])

        for c in range(3, 32):
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=[0, 1, 2, 3])

        df["kids"] = df[4] + df[18]
        df["teens"] = df[5] + df[6] + df[19] + df[20]
        df["youth"] = df[7] + df[8] + df[9] + df[10] + df[21] + df[22] + df[23] + df[24]
        df["middle"] = df[11] + df[12] + df[13] + df[14] + df[25] + df[26] + df[27] + df[28]
        df["senior"] = df[15] + df[16] + df[17] + df[29] + df[30] + df[31]
        df["total"] = df[3]

        age_cols = ["kids", "teens", "youth", "middle", "senior", "total"]
        df = df[[0, 1, 2, *age_cols]].rename(columns={0: "date", 1: "hour", 2: "dong_cd"})
        return self.remap_dongs(df, age_cols)


class AgePopPreprocessor(DaytimePopPreprocessor):
    """월별 연령별 생활인구 가공 및 동별/연령대별 평균 집계 (DaytimePopPreprocessor 상속)"""

    source_cls = AgeLivingPopSource

    def _process(self, source: MonthlyPopSource) -> pd.DataFrame:
        df = self._filter_common(source.load())

        age_cols = ["kids", "teens", "youth", "middle", "senior", "total"]
        grouped = df.groupby(["dong_cd", "is_weekend"])[age_cols].mean().reset_index()

        melted = pd.melt(
            grouped,
            id_vars=["dong_cd", "is_weekend"],
            value_vars=age_cols,
            var_name="age_key",
            value_name="pop",
        )
        melted["age_group"] = melted["age_key"].map(AGE_GROUPS)
        melted.insert(1, "year", source.year)
        melted.insert(2, "month", source.month)
        melted.insert(3, "season", self.config.months[source.month])
        return melted


if __name__ == "__main__":
    config = AgePreprocessConfig()
    preprocessor = AgePopPreprocessor(config, HolidayCalendar())
    preprocessor.run(ParkMapper(ParkMapSource(config.park_map_file)))
    preprocessor.save()
