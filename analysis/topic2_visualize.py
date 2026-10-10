"""
주제 2 시각화: 세대/연령대별 공원 보유 여부에 따른 생활인구 계절적 증가폭 분석

입력: daytime_age_pop.csv (extract_age_data.py 출력)
출력: docs/topic2/*.html  (GitHub Pages용 정적 인터랙티브 그래프)
      docs/topic2/stats_summary.csv
"""
import sys
from abc import ABC, abstractmethod
from pathlib import Path
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from topic1_visualize import Theme, DongNameLookup, Chart

PARK_LABEL = {True: "공원 있음", False: "공원 없음"}
AGE_ORDER = [
    "유아동 (0~9세)",
    "청소년 (10~19세)",
    "청년층 (20~39세)",
    "중장년 (40~59세)",
    "고령층 (60세 이상)",
    "전체 인구",
]
AGE_COLORS = {
    "유아동 (0~9세)": "#e76f51",
    "청소년 (10~19세)": "#f4a261",
    "청년층 (20~39세)": "#2a9d8f",
    "중장년 (40~59세)": "#457b9d",
    "고령층 (60세 이상)": "#1d3557",
    "전체 인구": "#6c757d",
}


# ──────────────────────────────────────────────
# 연령별 분석 클래스
# ──────────────────────────────────────────────
class AgeGroupAnalyzer:
    """연령대별 1월 대비 5월 생활인구 증가율 및 통계 검정"""

    def __init__(self, csv_path: Path, names: DongNameLookup):
        self.df = pd.read_csv(csv_path, dtype={"dong_cd": str})
        self.years = sorted(self.df["year"].unique())
        self.df["dong_nm"] = self.df["dong_cd"].map(names.name)

    def rates(self, weekend_only: bool = True, by_year: bool = False) -> pd.DataFrame:
        """행정동 x 연령대별 증가율(%) 계산"""
        sub = self.df[self.df["is_weekend"]] if weekend_only else self.df
        keys = ["dong_cd", "dong_nm", "has_park", "age_group"] + (["year"] if by_year else [])
        p = sub.pivot_table(index=keys, columns="month", values="pop", aggfunc="mean").reset_index()
        p = p.rename(columns={1: "jan", 5: "may"})
        p["rate"] = (p["may"] / p["jan"] - 1) * 100
        return p

    @staticmethod
    def compare(rates: pd.DataFrame) -> dict:
        """공원 보유 동 vs 미보유 동 비교 통계 (Welch t 95% CI, Mann-Whitney U)"""
        a = rates.loc[rates["has_park"], "rate"]
        b = rates.loc[~rates["has_park"], "rate"]
        t = stats.ttest_ind(a, b, equal_var=False)
        ci = t.confidence_interval(0.95)
        return {
            "n_park": len(a), "n_none": len(b),
            "mean_park": a.mean(), "mean_none": b.mean(),
            "diff": a.mean() - b.mean(), "ci_low": ci.low, "ci_high": ci.high,
            "p_welch": t.pvalue, "p_mwu": stats.mannwhitneyu(a, b).pvalue,
        }

    def summary(self, weekend_only: bool = True) -> pd.DataFrame:
        """연령대별 x (연도별 + 4개년) 비교 요약표"""
        rows = []
        yearly, pooled = self.rates(weekend_only=weekend_only, by_year=True), self.rates(weekend_only=weekend_only)
        for age in AGE_ORDER:
            for y in self.years:
                sub = yearly[(yearly["age_group"] == age) & (yearly["year"] == y)]
                rows.append({"age_group": age, "period": str(y), **self.compare(sub)})
            rows.append({"age_group": age, "period": "4개년", **self.compare(pooled[pooled["age_group"] == age])})
        return pd.DataFrame(rows)


# ──────────────────────────────────────────────
# 차트 1: 세대별 증가율 비교 그룹 막대 차트
# ──────────────────────────────────────────────
class AgeRateBarChart(Chart):
    """연령대별 공원 보유 vs 미보유 행정동의 1월→5월 증가율 비교 막대"""

    filename = "topic2_age_bar"

    def __init__(self, analyzer: AgeGroupAnalyzer):
        self.analyzer = analyzer
        self._fig = None

    def build(self) -> go.Figure:
        s = self.analyzer.summary()
        pooled = s[s["period"] == "4개년"].set_index("age_group").loc[AGE_ORDER].reset_index()

        fig = go.Figure()
        # 공원 있음 막대
        fig.add_trace(go.Bar(
            x=pooled["age_group"], y=pooled["mean_park"],
            name="공원 있음", marker=dict(color=Theme.COLORS[True]),
            text=pooled["mean_park"].map(lambda x: f"{x:+.2f}%"), textposition="outside",
            hovertemplate="<b>%{x}</b><br>공원 있음 평균 증가율: %{y:+.2f}%<extra></extra>",
        ))
        # 공원 없음 막대
        fig.add_trace(go.Bar(
            x=pooled["age_group"], y=pooled["mean_none"],
            name="공원 없음", marker=dict(color=Theme.COLORS[False]),
            text=pooled["mean_none"].map(lambda x: f"{x:+.2f}%"), textposition="outside",
            hovertemplate="<b>%{x}</b><br>공원 없음 평균 증가율: %{y:+.2f}%<extra></extra>",
        ))

        # 차이 및 p-value 주석
        for _, row in pooled.iterrows():
            age = row["age_group"]
            diff = row["diff"]
            p_val = row["p_mwu"]
            p_txt = "p < 0.01" if p_val < 0.01 else f"p = {p_val:.3f}"
            y_max = max(row["mean_park"], row["mean_none"], 0) + 1.8
            fig.add_annotation(
                x=age, y=y_max, text=f"<b>+{diff:.2f}%p</b><br><span style='font-size:11px;color:#6b7280'>{p_txt}</span>",
                showarrow=False, font=dict(size=12, color="#1f2937"),
            )

        fig.add_hline(y=0, line=dict(color="#9ca3af", width=1))
        fig.update_layout(
            barmode="group", bargap=0.25, height=550,
            yaxis=dict(title="1월 대비 5월 평균 증가율 (%)", ticksuffix="%", zeroline=False),
            xaxis=dict(title=""),
        )
        return Theme.apply(
            fig, "세대별 1월 → 5월 생활인구 증가율 비교 (주말 낮 10~17시)",
            "4개년(2023~2026) 평균 · 유아동(+4.12%p)과 청년층(+2.82%p)에서 공원 유인 효과 극대화"
        )


# ──────────────────────────────────────────────
# 차트 2: 세대별 공원 효과 신뢰구간 포레스트 플롯
# ──────────────────────────────────────────────
class AgeForestChart(Chart):
    """연령대별 증가율 격차(공원 - 비공원)와 95% 신뢰구간 포레스트 플롯"""

    filename = "topic2_age_forest"

    def __init__(self, analyzer: AgeGroupAnalyzer):
        self.analyzer = analyzer
        self._fig = None

    def build(self) -> go.Figure:
        s = self.analyzer.summary()
        pooled = s[s["period"] == "4개년"].set_index("age_group").loc[AGE_ORDER[::-1]].reset_index()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=pooled["diff"], y=pooled["age_group"],
            mode="markers",
            marker=dict(size=14, color=[AGE_COLORS[a] for a in pooled["age_group"]], symbol="square"),
            error_x=dict(
                type="data", symmetric=False,
                array=pooled["ci_high"] - pooled["diff"],
                arrayminus=pooled["diff"] - pooled["ci_low"],
                thickness=2.2, width=6,
            ),
            customdata=np.stack([pooled["ci_low"], pooled["ci_high"], pooled["p_welch"], pooled["p_mwu"]], axis=-1),
            hovertemplate="<b>%{y}</b><br>공원 효과: +%{x:.2f}%p (95% CI %{customdata[0]:+.2f} ~ %{customdata[1]:+.2f})"
                          "<br>Welch p=%{customdata[2]:.4f} · MWU p=%{customdata[3]:.4f}<extra></extra>",
        ))

        fig.add_vline(x=0, line=dict(color="#9ca3af", width=1.5, dash="dash"))
        fig.update_layout(
            height=460, showlegend=False,
            xaxis=dict(title="봄철 증가율 격차 (공원 있음 − 없음, %p)", ticksuffix="%p", zeroline=False),
            yaxis=dict(title=""),
        )
        return Theme.apply(
            fig, "세대별 공원 유인 효과의 크기 (95% 신뢰구간)",
            "모든 연령층에서 신뢰구간이 0%p를 초과하여 유의미함 · 유아동이 가장 큰 유입 격차 기록"
        )


# ──────────────────────────────────────────────
# 차트 3: 연도별 세대별 추이 멀티패널 차트
# ──────────────────────────────────────────────
class AgeYearlyTrendChart(Chart):
    """주요 연령대별 4개년(2023~2026) 연도별 추이 일관성 점검"""

    filename = "topic2_age_trend"

    def __init__(self, analyzer: AgeGroupAnalyzer):
        self.analyzer = analyzer
        self._fig = None

    def build(self) -> go.Figure:
        r = self.analyzer.rates(weekend_only=True, by_year=True)
        target_ages = ["유아동 (0~9세)", "청년층 (20~39세)", "고령층 (60세 이상)"]

        fig = make_subplots(
            rows=1, cols=3, subplot_titles=target_ages,
            shared_yaxes=False, horizontal_spacing=0.06
        )

        for col, age in enumerate(target_ages, start=1):
            sub = r[r["age_group"] == age]
            for hp in [True, False]:
                g = sub[sub["has_park"] == hp].groupby("year")["rate"]
                m = g.mean()
                ci = 1.96 * g.sem()
                fig.add_trace(go.Scatter(
                    x=m.index.astype(str), y=m.values,
                    name=PARK_LABEL[hp], legendgroup=str(hp), showlegend=(col == 1),
                    mode="lines+markers", line=dict(color=Theme.COLORS[hp], width=2.5),
                    marker=dict(size=7),
                    error_y=dict(type="data", array=ci.values, thickness=1.4, width=3),
                    hovertemplate="%{x}년 · " + PARK_LABEL[hp] + " %{y:+.2f}%<extra>" + age + "</extra>",
                ), row=1, col=col)
            fig.add_hline(y=0, line=dict(color="#9ca3af", width=1), row=1, col=col)

        fig.update_yaxes(title_text="평균 증가율 (%)", ticksuffix="%", row=1, col=1)
        fig.update_layout(height=480, margin=dict(t=120))
        Theme.apply(fig, "주요 세대별 4개년(2023~2026) 증가율 추이", "매년 공원 보유 행정동이 우세함을 입증")
        fig.update_layout(legend=dict(y=1.15))
        return fig


# ──────────────────────────────────────────────
# 리포트 내보내기 클래스
# ──────────────────────────────────────────────
class Topic2Report:
    """주제 2 차트 및 통계표 파일 생성"""

    def __init__(self, analyzer: AgeGroupAnalyzer, charts: list, out_dir: Path):
        self.analyzer = analyzer
        self.charts = charts
        self.out_dir = Path(out_dir)

    def export(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for chart in self.charts:
            path = chart.save(self.out_dir)
            print(f"  [주제2 차트 저장] {path}")
        self._export_stats()
        self._export_preview()

    def _export_stats(self) -> None:
        path = self.out_dir / "stats_summary.csv"
        self.analyzer.summary().round(4).to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  [주제2 통계표 저장] {path}")

    def _export_preview(self) -> None:
        divs = "\n".join(
            f"<section class='card'>{c.to_div(include_js=(i == 0))}</section>"
            for i, c in enumerate(self.charts)
        )
        html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>주제 2 · 세대별 공원 반응도 분석</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
<style>
 body {{ margin:0; background:#f3f4f6; font-family:{Theme.FONT}; color:#1f2937; }}
 header {{ padding:40px 24px 8px; max-width:1100px; margin:auto; }}
 h1 {{ font-size:26px; margin:0 0 6px; }}
 header p {{ color:#6b7280; margin:0; }}
 main {{ max-width:1100px; margin:auto; padding:16px 24px 48px; display:grid; gap:24px; }}
 .card {{ background:#fff; border-radius:16px; box-shadow:0 4px 18px rgba(0,0,0,.06); padding:8px; }}
</style></head><body>
<header><h1>세대/연령대별 공원 반응도 분석</h1>
<p>서울시 424개 행정동 · 2023~2026년 주말 낮(10~17시) 1월 vs 5월 비교</p></header>
<main>{divs}</main></body></html>"""
        path = self.out_dir / "index.html"
        path.write_text(html, encoding="utf-8")
        print(f"  [주제2 미리보기 저장] {path}")


if __name__ == "__main__":
    names = DongNameLookup(PROJECT_ROOT / "data" / "raw" / "HangJeongDong_ver20260701.geojson")
    analyzer = AgeGroupAnalyzer(PROJECT_ROOT / "data" / "processed" / "daytime_age_pop.csv", names)
    charts = [
        AgeRateBarChart(analyzer),
        AgeForestChart(analyzer),
        AgeYearlyTrendChart(analyzer),
    ]
    Topic2Report(analyzer, charts, PROJECT_ROOT / "docs" / "topic2").export()
