"""
[주제 1] 서울시 공원 유무별 주말 낮 생활인구 집계 OOP 전처리 파이프라인

1. 파일 내용 (What is inside):
   - CsvSource (추상 기본 클래스): CSV 파일 인코딩(cp949/utf-8) 자동 판별 및 행정동 코드 정규화 규격 제공.
   - LivingPopSource: 서울시 원천 생활인구 CSV에서 일자, 시간대, 행정동코드, 총생활인구수를 추출하는 로더.
   - ParkMapSource: 서울시 주요 공원 현황 데이터를 로드하고 면적 오류 보정(북한산 등)을 수행하는 로더.
   - HolidayCalendar: 주말 및 법정공휴일 판별 및 인구 왜곡을 유발하는 설 연휴(2023/2025년) 제외 달력.
   - ParkMapper: 행정동 불일치 공원(5개소)을 제외하고 행정동별 공원 보유 여부(has_park)를 매핑.
   - DaytimePopPreprocessor: 혹한기(1월)와 봄철(5월) 낮 시간대(10~17시) 주말·평일 평균 생활인구를 집계하는 파이프라인.

2. 파일 역할 (Role & Function):
   - 4개년(2023~2026) 1월·5월 원천 생활인구 빅데이터를 정제하여 주제 1의 가설 검정에 필요한 기초 데이터셋을 생성합니다.

3. 입출력 (I/O):
   - 입력: data/raw/LPD/LOCAL_PEOPLE_DONG_*.csv (원천 생활인구)
           data/raw/park_dong_map.csv (공원-행정동 맵핑)
   - 출력: data/processed/daytime_weekend_pop.csv (424개 행정동 x 4개년 x 2개 계절 집계 데이터셋, 6,784행)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

@dataclass
class PreprocessConfig:
    data_dir: Path = PROJECT_ROOT / "data" / "raw" / "LPD"
    park_map_file: Path = PROJECT_ROOT / "data" / "raw" / "park_dong_map.csv"
    output_file: Path = PROJECT_ROOT / "data" / "processed" / "daytime_weekend_pop.csv"
    years: list = field(default_factory=lambda: [2023, 2024, 2025, 2026])
    months: dict = field(default_factory=lambda: {1: "winter", 5: "spring"})
    hour_start: int = 10                               # 10시대 ~ 17시대 (10:00 ~ 17:59)
    hour_end: int = 17


# ──────────────────────────────────────────────
# 공휴일 달력
# ──────────────────────────────────────────────
class HolidayCalendar:
    """주말·공휴일(휴일) 판별 및 분석 제외일(설 연휴) 관리"""

    # 휴일로 취급 → is_weekend = True
    HOLIDAYS = [
        "2023-01-01", "2023-05-05", "2023-05-27", "2023-05-29",   # 신정, 어린이날, 부처님오신날, 대체공휴일
        "2024-01-01", "2024-05-05", "2024-05-06", "2024-05-15",   # 신정, 어린이날, 대체공휴일, 부처님오신날
        "2025-01-01", "2025-05-05", "2025-05-06",                 # 신정, 어린이날·부처님오신날, 대체공휴일
        "2026-01-01", "2026-05-01", "2026-05-05",                 # 신정, 노동절, 어린이날
        "2026-05-24", "2026-05-25",                               # 부처님오신날, 대체공휴일
    ]

    # 귀성으로 인구 패턴이 왜곡되므로 분석에서 제외 (설 연휴 + 관련 대체·임시공휴일)
    EXCLUDED = [
        "2023-01-21", "2023-01-22", "2023-01-23", "2023-01-24",
        "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30",
    ]

    def __init__(self, holidays=None, excluded=None):
        self.holidays = pd.to_datetime(holidays or self.HOLIDAYS)
        self.excluded = pd.to_datetime(excluded or self.EXCLUDED)

    def is_rest_day(self, dates: pd.Series) -> pd.Series:
        """토·일 또는 공휴일이면 True"""
        return (dates.dt.dayofweek >= 5) | dates.isin(self.holidays)

    def is_excluded(self, dates: pd.Series) -> pd.Series:
        return dates.isin(self.excluded)


# ──────────────────────────────────────────────
# CSV 로더
# ──────────────────────────────────────────────
class CsvSource(ABC):
    """CSV 데이터 소스의 공통 기반 클래스"""

    def __init__(self, fpath: Path):
        self.fpath = Path(fpath)
        if not self.fpath.exists():
            raise FileNotFoundError(f"파일 없음: {self.fpath}")

    @property
    def encoding(self) -> str:
        """BOM 유무로 utf-8-sig / cp949 판별"""
        with open(self.fpath, "rb") as f:
            return "utf-8-sig" if f.read(3) == b"\xef\xbb\xbf" else "cp949"

    @staticmethod
    def normalize_dong_cd(s: pd.Series) -> pd.Series:
        return s.astype(str).str.strip().str[:8]

    @abstractmethod
    def load(self) -> pd.DataFrame:
        ...


class LivingPopSource(CsvSource):
    """서울시 행정동별 생활인구 월별 CSV"""

    def __init__(self, fpath: Path, year: int, month: int):
        super().__init__(fpath)
        self.year = year
        self.month = month

    def load(self) -> pd.DataFrame:
        # [0: 기준일ID, 1: 시간대구분, 2: 행정동코드, 3: 총생활인구] 4개 열만 로드
        df = pd.read_csv(
            self.fpath,
            encoding=self.encoding,
            encoding_errors="replace",      # 헤더는 건너뛰므로 깨져도 무방
            index_col=False,
            skiprows=1,
            header=None,
            usecols=[0, 1, 2, 3],
            names=["date", "hour", "dong_cd", "pop"],
            dtype=str,
        )
        df["dong_cd"] = self.normalize_dong_cd(df["dong_cd"])
        df["hour"] = pd.to_numeric(df["hour"], errors="coerce")
        df["pop"] = pd.to_numeric(df["pop"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"].str.strip(), format="%Y%m%d", errors="coerce")
        return df.dropna(subset=["date", "hour", "pop"])


class ParkMapSource(CsvSource):
    """공원-행정동 매핑 CSV (서울시 주요 공원 현황 기반)"""

    # 원본 면적 오류 보정 (park_nm → 올바른 면적 ㎡)
    AREA_CORRECTIONS = {
        "북한산국립공원": 77_334_000.0,   # 원본 7.7334e10 (단위 1,000배 오류)
    }

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.fpath, encoding=self.encoding, dtype={"dong_cd": str})
        df["dong_cd"] = self.normalize_dong_cd(df["dong_cd"])
        name = df["park_nm"].astype(str).str.strip()
        for park_nm, area in self.AREA_CORRECTIONS.items():
            df.loc[name == park_nm, "area_m2"] = area
        return df[df["park_nm"].notna() & (name != "")]   # 공원 이름이 있으면 보유 (면적 무관)


# ──────────────────────────────────────────────
# 공원 보유 판별
# ──────────────────────────────────────────────
class ParkMapper:
    """행정동별 공원 보유 여부 판별"""

    def __init__(self, source: ParkMapSource):
        self.parks = source.load()
        self.excluded_parks = pd.DataFrame()

    def restrict_to(self, valid_dongs: set) -> pd.DataFrame:
        """생활인구 데이터에 없는 행정동코드의 공원 제외 (행정동 개편으로 코드 불일치)"""
        mask = self.parks["dong_cd"].isin(valid_dongs)
        self.excluded_parks = self.parks.loc[~mask, ["park_nm", "dong_cd"]]
        self.parks = self.parks[mask]
        return self.excluded_parks

    @property
    def park_dongs(self) -> set:
        return set(self.parks["dong_cd"])

    def has_park(self, dong_cd: pd.Series) -> pd.Series:
        return dong_cd.isin(self.park_dongs)


# ──────────────────────────────────────────────
# 전처리 파이프라인
# ──────────────────────────────────────────────
class DaytimePopPreprocessor:
    """월별 생활인구 → [행정동, 연, 월, 주말여부] 단위 낮 시간대 평균 생활인구"""

    def __init__(self, config: PreprocessConfig, calendar: HolidayCalendar):
        self.config = config
        self.calendar = calendar
        self.result = None

    def _sources(self):
        for year in self.config.years:
            for month in self.config.months:
                fpath = self.config.data_dir / f"LOCAL_PEOPLE_DONG_{year}{month:02d}.csv"
                try:
                    yield LivingPopSource(fpath, year, month)
                except FileNotFoundError as e:
                    print(f"[경고] {e}")

    def _process(self, source: LivingPopSource) -> pd.DataFrame:
        df = source.load()

        # 1. 낮 시간대 필터링
        df = df[df["hour"].between(self.config.hour_start, self.config.hour_end)]

        # 2. 설 연휴 제외
        excluded = self.calendar.is_excluded(df["date"])
        if excluded.any():
            print(f"    설 연휴 {df.loc[excluded, 'date'].nunique()}일 제외")
        df = df[~excluded].copy()

        # 3. 주말 여부 (토·일·공휴일 = True)
        df["is_weekend"] = self.calendar.is_rest_day(df["date"])

        # 4. [행정동, 주말여부] 단위 시간당 평균 생활인구
        grouped = (
            df.groupby(["dong_cd", "is_weekend"])
            .agg(pop=("pop", "mean"), n_days=("date", "nunique"))
            .reset_index()
        )
        grouped.insert(1, "year", source.year)
        grouped.insert(2, "month", source.month)
        grouped.insert(3, "season", self.config.months[source.month])
        return grouped

    def run(self, park_mapper: ParkMapper) -> pd.DataFrame:
        records = []
        for source in self._sources():
            print(f"[{source.year}{source.month:02d}] 처리 중: {source.fpath.name}")
            records.append(self._process(source))

        if not records:
            raise RuntimeError("처리된 파일이 없습니다. data_dir 경로를 확인하세요.")
        df = pd.concat(records, ignore_index=True)

        # 5. 공원 보유 여부 (코드 불일치 공원은 제외)
        excluded = park_mapper.restrict_to(set(df["dong_cd"]))
        if not excluded.empty:
            print(f"[안내] 행정동코드 불일치로 제외된 공원 {len(excluded)}개:")
            for _, row in excluded.iterrows():
                print(f"    - {row['park_nm']} ({row['dong_cd']})")
        df["has_park"] = park_mapper.has_park(df["dong_cd"])

        self.result = df
        return df

    def save(self) -> None:
        if self.result is None:
            raise RuntimeError("run()을 먼저 실행하세요.")
        self.result.to_csv(self.config.output_file, index=False, encoding="utf-8-sig")

        n_park = self.result.loc[self.result["has_park"], "dong_cd"].nunique()
        n_none = self.result.loc[~self.result["has_park"], "dong_cd"].nunique()
        print(f"[완료] {self.config.output_file} 생성 (총 {len(self.result):,}행)")
        print(f"    공원 보유 행정동: {n_park}개 / 미보유 행정동: {n_none}개")


if __name__ == "__main__":
    config = PreprocessConfig()
    preprocessor = DaytimePopPreprocessor(config, HolidayCalendar())
    preprocessor.run(ParkMapper(ParkMapSource(config.park_map_file)))
    preprocessor.save()