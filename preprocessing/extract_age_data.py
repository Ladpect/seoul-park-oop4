"""
[주제 2] 세대/연령대별 1월·5월 주말 낮 생활인구 집계 OOP 전처리 파이프라인

1. 파일 내용 (What is inside):
   - AGE_GROUPS: 5개 생애주기 세대 그룹 정의
     * kids: 유아동 (0~9세)
     * teens: 청소년 (10~19세)
     * youth: 청년층 (20~39세)
     * middle: 중장년 (40~59세)
     * senior: 고령층 (60세 이상)
     * total: 전체 인구 (검증용 합계)
   - AgeLivingPopSource: CsvSource를 상속받아 32개 성별/연령별 인구 열을 파싱하고 5대 세대 그룹으로 집계하는 로더.
   - AgePopPreprocessor: newdata.py의 HolidayCalendar, ParkMapper를 재사용하여 세대별 주말 낮 평균 생활인구를 정제하는 파이프라인.

2. 파일 역할 (Role & Function):
   - 봄철 공원 방문을 주도하는 특정 연령층(영유아 가족, 청년층, 고령층)을 규명하기 위해 세대별 세분화 데이터셋을 생성합니다.

3. 입출력 (I/O):
   - 입력: data/raw/LPD/LOCAL_PEOPLE_DONG_*.csv (원천 생활인구 32개 열)
           data/raw/park_dong_map.csv (공원-행정동 맵핑)
   - 출력: data/processed/daytime_age_pop.csv (424개 행정동 x 4개년 x 2개 계절 x 5대 세대 집계 데이터셋, 40,704행)
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
