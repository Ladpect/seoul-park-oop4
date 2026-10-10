"""
주제 2 전처리: 세대/연령대별 1월·5월 주말 낮 시간대 생활인구 데이터셋 생성

newdata.py의 OOP 클래스(CsvSource, HolidayCalendar, ParkMapper 등)를 상속 및 재사용하여
5개 연령대(유아동, 청소년, 청년, 중장년, 노년)별 인구를 가공합니다.

출력: daytime_age_pop.csv
    dong_cd, year, month, season, is_weekend, age_group, pop, has_park
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from newdata import CsvSource, HolidayCalendar, ParkMapSource, ParkMapper, PreprocessConfig


# ──────────────────────────────────────────────
# 연령 그룹 정의 및 설정
# ──────────────────────────────────────────────
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


# ──────────────────────────────────────────────
# 연령별 생활인구 데이터 소스 (상속)
# ──────────────────────────────────────────────
class AgeLivingPopSource(CsvSource):
    """32개 전체 열(성별/연령별 생활인구)을 로드하고 5개 세대 그룹으로 집계"""

    def __init__(self, fpath: Path, year: int, month: int):
        super().__init__(fpath)
        self.year = year
        self.month = month

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(
            self.fpath,
            encoding=self.encoding,
            encoding_errors="replace",
            index_col=False,
            skiprows=1,
            header=None,
            dtype=str,
        )
        # 0: 일자, 1: 시간, 2: 행정동코드
        df[0] = pd.to_datetime(df[0].str.strip(), format="%Y%m%d", errors="coerce")
        df[1] = pd.to_numeric(df[1], errors="coerce")
        df[2] = self.normalize_dong_cd(df[2])

        # 3~31번 열(생활인구) 수치 변환
        for c in range(3, 32):
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=[0, 1, 2, 3])

        # 연령대별 합산
        df["kids"] = df[4] + df[18]
        df["teens"] = df[5] + df[6] + df[19] + df[20]
        df["youth"] = df[7] + df[8] + df[9] + df[10] + df[21] + df[22] + df[23] + df[24]
        df["middle"] = df[11] + df[12] + df[13] + df[14] + df[25] + df[26] + df[27] + df[28]
        df["senior"] = df[15] + df[16] + df[17] + df[29] + df[30] + df[31]
        df["total"] = df[3]

        return df[[0, 1, 2, "kids", "teens", "youth", "middle", "senior", "total"]].rename(
            columns={0: "date", 1: "hour", 2: "dong_cd"}
        )


# ──────────────────────────────────────────────
# 연령별 전처리 파이프라인
# ──────────────────────────────────────────────
class AgePopPreprocessor:
    """월별 연령별 생활인구 가공 및 동별/연령대별 평균 집계"""

    def __init__(self, config: AgePreprocessConfig, calendar: HolidayCalendar):
        self.config = config
        self.calendar = calendar
        self.result = None

    def _sources(self):
        for year in self.config.years:
            for month in self.config.months:
                fpath = self.config.data_dir / f"LOCAL_PEOPLE_DONG_{year}{month:02d}.csv"
                try:
                    yield AgeLivingPopSource(fpath, year, month)
                except FileNotFoundError as e:
                    print(f"[경고] {e}")

    def _process(self, source: AgeLivingPopSource) -> pd.DataFrame:
        df = source.load()

        # 1. 낮 시간대 필터링 (10~17시)
        df = df[df["hour"].between(self.config.hour_start, self.config.hour_end)]

        # 2. 설 연휴 제외
        excluded = self.calendar.is_excluded(df["date"])
        df = df[~excluded].copy()

        # 3. 휴일/주말 여부
        df["is_weekend"] = self.calendar.is_rest_day(df["date"])

        # 4. [행정동, 주말여부] 단위 각 연령별 평균 산출
        age_cols = ["kids", "teens", "youth", "middle", "senior", "total"]
        grouped = df.groupby(["dong_cd", "is_weekend"])[age_cols].mean().reset_index()

        # 5. Long-format 변환 (동, 주말, 연령대, 인구)
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

    def run(self, park_mapper: ParkMapper) -> pd.DataFrame:
        records = []
        for source in self._sources():
            print(f"[{source.year}{source.month:02d}] 연령 데이터 처리 중: {source.fpath.name}")
            records.append(self._process(source))

        if not records:
            raise RuntimeError("처리된 파일이 없습니다.")

        df = pd.concat(records, ignore_index=True)

        # 공원 보유 여부 매핑
        park_mapper.restrict_to(set(df["dong_cd"]))
        df["has_park"] = park_mapper.has_park(df["dong_cd"])

        self.result = df
        return df

    def save(self) -> None:
        if self.result is None:
            raise RuntimeError("run()을 먼저 실행하세요.")
        self.result.to_csv(self.config.output_file, index=False, encoding="utf-8-sig")
        print(f"[완료] {self.config.output_file} 생성 (총 {len(self.result):,}행)")


if __name__ == "__main__":
    config = AgePreprocessConfig()
    preprocessor = AgePopPreprocessor(config, HolidayCalendar())
    preprocessor.run(ParkMapper(ParkMapSource(config.park_map_file)))
    preprocessor.save()
