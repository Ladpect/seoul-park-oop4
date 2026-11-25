"""
[주제 2] 세대/연령대별 공원 반응도 통계 검정 및 Plotly 시각화 모듈

1. 파일 내용 (What is inside):
   - AgeGroupAnalyzer: BaseAnalyzer를 상속받아 5대 세대 그룹별 증가율 및 가설 검정 수행.
   - AgeRateBarChart: 5개 세대별 공원 보유 동 vs 미보유 동의 봄철 생활인구 증가율 비교 막대그래프.
   - AgeYearlyTrendChart: 4개년(2023~2026) 세대별 증가율 추이선 그래프.
   - Topic2Report: ReportExporter를 상속받아 주제 2 리포트 및 통계표 저장.
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

ANALYSIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ANALYSIS_DIR.parent
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

from topic1_visualize import BaseAnalyzer, Chart, DongNameLookup, ReportExporter, Theme

AGE_ORDER = [
    "유아동 (0~9세)",
    "청소년 (10~19세)",
    "청년층 (20~39세)",
    "중장년 (40~59세)",
    "고령층 (60세 이상)",
    "전체 인구",
]


class AgeGroupAnalyzer(BaseAnalyzer):
    """연령대별 1월 대비 5월 생활인구 증가율 및 가설 검정 (BaseAnalyzer 상속)"""

    group_col = "age_group"
    categories = AGE_ORDER

    def rates(self, weekend_only: bool = True, by_year: bool = False) -> pd.DataFrame:
        sub = self.df[self.df["is_weekend"]] if weekend_only else self.df
        keys = ["dong_cd", "dong_nm", "has_park", "age_group"] + (["year"] if by_year else [])
        return self._calc_rates(sub, keys)

    def summary(self, weekend_only: bool = True) -> pd.DataFrame:
        """주말·공휴일 낮(10~17시) 기준 기본 설정으로 세대별 통계 요약표 생성"""
        return super().summary(weekend_only=weekend_only)

    def dong_age_details(self) -> dict:
        """행정동별 5대 세대 봄철 증가율 목록 반환"""
        age_cats = [a for a in AGE_ORDER if a != "전체 인구"]
        pooled = self.rates(weekend_only=True)
        pooled = pooled[pooled["age_group"].isin(age_cats)]
        details = {}
        for cd, grp in pooled.groupby("dong_cd"):
            age_map = {r["age_group"]: round(float(r["rate"]), 2) for _, r in grp.iterrows()}
            details[cd] = [{"group": g.split(" ")[0], "rate": age_map[g]} for g in age_cats if g in age_map]
        return details


class AgeRateBarChart(Chart):
    """① 연령대별 공원 보유 vs 미보유 행정동의 1월→5월 증가율 비교 막대"""

    filename = "topic2_age_bar"

    def build(self) -> go.Figure:
        s = self.analyzer.summary()
        pooled = s[s["period"] == "4개년"].set_index("age_group").loc[AGE_ORDER].reset_index()

        fig = go.Figure()
        for hp, label in [(True, "공원 보유"), (False, "공원 미보유")]:
            col = "mean_park" if hp else "mean_none"
            fig.add_trace(go.Bar(
                x=pooled["age_group"], y=pooled[col], name=label,
                marker=dict(color=Theme.COLORS[hp]),
                text=pooled[col].map(lambda x: f"{x:+.2f}%"), textposition="outside",
                textfont=dict(size=11.5, color="#374151"),
                hovertemplate=f"<b>%{{x}}</b><br>{label} 평균 증가율: %{{y:+.2f}}%<extra></extra>",
            ))

        for _, row in pooled.iterrows():
            y_max = max(row["mean_park"], row["mean_none"], 0) + 1.6
            fig.add_annotation(
                x=row["age_group"], y=y_max, showarrow=False, font=dict(size=12, color="#374151"),
                text=f"<b style='color:#0F766E'>{row['diff']:+.2f}%p</b>",
            )

        fig.add_hline(y=0, line=dict(color="#D1D5DB", width=1))
        fig.update_layout(barmode="group", bargap=0.28, height=480,
                          yaxis=dict(title="1월 대비 5월 평균 증가율 (%)", ticksuffix="%", zeroline=False, range=[-8, 10]),
                          xaxis=dict(title=""))
        gaps = pooled.set_index("age_group")["diff"]
        return Theme.apply(
            fig, "세대별 1월 → 5월 생활인구 증가율 비교 (주말·공휴일 낮 10~17시 기준)",
            f"4개년(2023~2026) 평균 · 공원 보유·미보유 행정동 간 증가율 차이 "
            f"유아동({gaps['유아동 (0~9세)']:+.2f}%p), 청년층({gaps['청년층 (20~39세)']:+.2f}%p)",
        )


class AgeYearlyTrendChart(Chart):
    """② 주요 연령대별 4개년(2023~2026) 연도별 추이 일관성 점검"""

    filename = "topic2_age_trend"

    def build(self) -> go.Figure:
        target_ages = ["유아동 (0~9세)", "청년층 (20~39세)", "고령층 (60세 이상)"]
        fig = self.build_yearly_panels(self.analyzer.rates(weekend_only=True, by_year=True),
                                       "age_group", target_ages, shared_yaxes=False)
        fig.update_yaxes(title_text="평균 증가율 (%)", ticksuffix="%", row=1, col=1)
        fig.update_layout(height=420)
        Theme.apply(fig, "주요 세대별 4개년(2023~2026) 증가율 추이 (주말 낮 10~17시)", "매년 공원 보유 행정동이 우세함을 입증")
        fig.update_layout(legend=dict(y=1.16), margin=dict(t=108, l=56, r=24, b=44))
        return fig


class Topic2Report(ReportExporter):
    title = "세대/연령대별 공원 반응도 분석"
    subtitle = "서울시 424개 행정동 · 2023~2026년 주말 낮(10~17시) 1월 vs 5월 비교"


if __name__ == "__main__":
    names = DongNameLookup()
    analyzer = AgeGroupAnalyzer(PROJECT_ROOT / "data" / "processed" / "daytime_age_pop.csv", names)
    charts = [AgeRateBarChart(analyzer), AgeYearlyTrendChart(analyzer)]
    Topic2Report(analyzer, charts, PROJECT_ROOT / "docs" / "topic2").export()
    print(analyzer.summary()[["age_group", "period", "mean_park", "mean_none", "diff"]].round(4).to_string())
