"""
주제 1 시각화: 공원 보유 여부에 따른 낮 시간대 생활인구의 계절적 증가폭 (1월 vs 5월)

입력: daytime_weekend_pop.csv (newdata.py 출력)
출력: docs/topic1/*.html  (GitHub Pages용 정적 인터랙티브 그래프, 브라우저에서 SVG 다운로드 가능)
      docs/topic1/stats_summary.csv
"""
import json
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats

WEEKEND, WEEKDAY, ALL_DAYS = "주말·공휴일", "평일", "전체"
DAY_TYPES = [WEEKEND, WEEKDAY, ALL_DAYS]
PARK_LABEL = {True: "공원 있음", False: "공원 없음"}


# ──────────────────────────────────────────────
# 스타일
# ──────────────────────────────────────────────
class Theme:
    COLORS = {True: "#2a9d8f", False: "#e76f51"}
    DAY_COLORS = {WEEKEND: "#264653", WEEKDAY: "#8a5a83", ALL_DAYS: "#e9a23b"}
    FONT = "Pretendard, 'Noto Sans KR', 'Malgun Gothic', sans-serif"

    @classmethod
    def apply(cls, fig: go.Figure, title: str, subtitle: str = "") -> go.Figure:
        text = f"<b>{title}</b>" + (f"<br><span style='font-size:13px;color:#6b7280'>{subtitle}</span>" if subtitle else "")
        fig.update_layout(
            template="plotly_white",
            title=dict(text=text, x=0.02, xanchor="left"),
            font=dict(family=cls.FONT, size=13, color="#1f2937"),
            hoverlabel=dict(font_family=cls.FONT),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=110, l=70, r=30, b=60),
        )
        return fig


# ──────────────────────────────────────────────
# 행정동 이름 조회
# ──────────────────────────────────────────────
class DongNameLookup:
    """행정동코드(8자리) → '구 동' 이름 (geojson 기반, 없으면 코드 그대로)"""

    def __init__(self, geojson_path: Path):
        with open(geojson_path, encoding="utf-8") as f:
            features = json.load(f)["features"]
        self._names = {
            str(ft["properties"]["adm_cd2"])[:8]: " ".join(ft["properties"]["adm_nm"].split()[1:])
            for ft in features
            if str(ft["properties"].get("adm_cd2", "")).startswith("11")
        }

    def name(self, dong_cd: str) -> str:
        return self._names.get(dong_cd, f"행정동 {dong_cd}")


# ──────────────────────────────────────────────
# 분석
# ──────────────────────────────────────────────
class SeasonalChangeAnalyzer:
    """행정동별 1월 → 5월 생활인구 증가율 계산 및 공원 유무 그룹 비교"""

    def __init__(self, csv_path: Path, names: DongNameLookup):
        df = pd.read_csv(csv_path, dtype={"dong_cd": str})
        self.years = sorted(df["year"].unique())
        self.monthly = self._with_all_days(df)
        self.monthly["dong_nm"] = self.monthly["dong_cd"].map(names.name)

    @staticmethod
    def _with_all_days(df: pd.DataFrame) -> pd.DataFrame:
        """주말·평일 + 일수 가중 평균한 '전체' 행 추가"""
        df = df.copy()
        df["day_type"] = df["is_weekend"].map({True: WEEKEND, False: WEEKDAY})
        df["weighted"] = df["pop"] * df["n_days"]
        keys = ["dong_cd", "year", "month", "has_park"]
        all_days = df.groupby(keys).agg(weighted=("weighted", "sum"), n_days=("n_days", "sum")).reset_index()
        all_days["pop"] = all_days["weighted"] / all_days["n_days"]
        all_days["day_type"] = ALL_DAYS
        cols = keys + ["day_type", "pop"]
        return pd.concat([df[cols], all_days[cols]], ignore_index=True)

    def rates(self, by_year: bool = False) -> pd.DataFrame:
        """행정동별 증가율(%) — by_year=False면 4개년 1월 평균 vs 5월 평균"""
        keys = ["dong_cd", "dong_nm", "has_park", "day_type"] + (["year"] if by_year else [])
        p = self.monthly.pivot_table(index=keys, columns="month", values="pop", aggfunc="mean").reset_index()
        p = p.rename(columns={1: "jan", 5: "may"})
        p["rate"] = (p["may"] / p["jan"] - 1) * 100
        return p

    @staticmethod
    def compare(rates: pd.DataFrame) -> dict:
        """공원 있음 − 공원 없음 평균 증가율 차이 (Welch t 95% CI, Mann-Whitney U)"""
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

    def summary(self) -> pd.DataFrame:
        """요일유형 × (연도별 + 4개년) 비교 결과표"""
        rows = []
        yearly, pooled = self.rates(by_year=True), self.rates()
        for dt in DAY_TYPES:
            for y in self.years:
                sub = yearly[(yearly["day_type"] == dt) & (yearly["year"] == y)]
                rows.append({"day_type": dt, "period": str(y), **self.compare(sub)})
            rows.append({"day_type": dt, "period": "4개년", **self.compare(pooled[pooled["day_type"] == dt])})
        return pd.DataFrame(rows)


# ──────────────────────────────────────────────
# 차트
# ──────────────────────────────────────────────
class Chart(ABC):
    """모든 차트의 공통 기반: build()로 Figure 생성, save()로 HTML 저장"""

    filename: str = "chart"

    def __init__(self, analyzer: SeasonalChangeAnalyzer):
        self.analyzer = analyzer
        self._fig = None

    @abstractmethod
    def build(self) -> go.Figure:
        ...

    @property
    def figure(self) -> go.Figure:
        if self._fig is None:
            self._fig = self.build()
        return self._fig

    @property
    def config(self) -> dict:
        # 브라우저 툴바의 카메라 버튼 → SVG(벡터) 다운로드
        return {
            "displaylogo": False,
            "responsive": True,
            "toImageButtonOptions": {"format": "svg", "filename": self.filename, "scale": 1},
        }

    def save(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.filename}.html"
        self.figure.write_html(path, include_plotlyjs="cdn", config=self.config, full_html=True)
        return path

    def to_div(self, include_js: bool) -> str:
        return self.figure.to_html(include_plotlyjs="cdn" if include_js else False, full_html=False, config=self.config)

    @staticmethod
    def p_text(p: float) -> str:
        return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


class RateDistributionChart(Chart):
    """① 요일유형별 증가율 분포 (박스 + 개별 행정동 점)"""

    filename = "topic1_distribution"

    def build(self) -> go.Figure:
        r = self.analyzer.rates()
        fig = go.Figure()
        for hp in [True, False]:
            s = r[r["has_park"] == hp]
            fig.add_trace(go.Box(
                x=s["day_type"], y=s["rate"], name=PARK_LABEL[hp],
                marker=dict(color=Theme.COLORS[hp], size=4, opacity=0.55),
                line=dict(width=1.6), boxpoints="all", jitter=0.45, pointpos=0, boxmean=True,
                customdata=np.stack([s["dong_nm"], s["jan"], s["may"]], axis=-1),
                hovertemplate="<b>%{customdata[0]}</b><br>1월 %{customdata[1]:,.0f}명 → 5월 %{customdata[2]:,.0f}명"
                              "<br>증가율 %{y:+.2f}%<extra>" + PARK_LABEL[hp] + "</extra>",
            ))
        for dt in DAY_TYPES:
            c = self.analyzer.compare(r[r["day_type"] == dt])
            fig.add_annotation(
                x=dt, y=1.0, yref="paper", yanchor="bottom", showarrow=False,
                text=f"<b>{c['diff']:+.2f}%p</b> · Mann-Whitney {self.p_text(c['p_mwu'])}",
                font=dict(size=12),
            )
        fig.add_hline(y=0, line=dict(color="#9ca3af", width=1))
        fig.update_layout(boxmode="group", boxgroupgap=0.25, height=560,
                          xaxis=dict(categoryorder="array", categoryarray=DAY_TYPES),
                          yaxis=dict(title="1월 → 5월 증가율 (%)", ticksuffix="%", zeroline=False))
        return Theme.apply(fig, "공원 유무별 1월 → 5월 생활인구 증가율 분포",
                           "10~17시 · 2023~2026년 1월 평균 대비 5월 평균 · 점 하나 = 행정동 하나 (점선 = 평균)")


class DifferenceForestChart(Chart):
    """② 공원 효과 크기: (공원 있음 − 없음) 평균 증가율 차이와 95% 신뢰구간"""

    filename = "topic1_forest"

    def build(self) -> go.Figure:
        s = self.analyzer.summary()
        fig = go.Figure()
        for dt in DAY_TYPES:
            d = s[s["day_type"] == dt]
            pooled = d["period"] == "4개년"
            fig.add_trace(go.Scatter(
                x=d["diff"], y=[d["day_type"].tolist(), d["period"].tolist()],
                mode="markers", name=dt,
                marker=dict(color=Theme.DAY_COLORS[dt], size=np.where(pooled, 15, 10),
                            symbol=np.where(pooled, "diamond", "circle"), line=dict(color="white", width=1)),
                error_x=dict(type="data", symmetric=False, array=d["ci_high"] - d["diff"],
                             arrayminus=d["diff"] - d["ci_low"], thickness=2, width=5),
                customdata=np.stack([d["mean_park"], d["mean_none"], d["ci_low"], d["ci_high"], d["p_welch"]], axis=-1),
                hovertemplate="<b>%{y}</b><br>차이 %{x:+.2f}%p (95% CI %{customdata[2]:+.2f} ~ %{customdata[3]:+.2f})"
                              "<br>공원 있음 %{customdata[0]:+.2f}% · 없음 %{customdata[1]:+.2f}%"
                              "<br>Welch p = %{customdata[4]:.4f}<extra></extra>",
            ))
        fig.add_vline(x=0, line=dict(color="#9ca3af", width=1.5, dash="dash"))
        fig.update_layout(height=640, showlegend=False,
                          xaxis=dict(title="증가율 차이 (공원 있음 − 공원 없음, %p)", ticksuffix="%p", zeroline=False),
                          yaxis=dict(autorange="reversed"))
        return Theme.apply(fig, "공원 효과의 크기와 일관성",
                           "막대 = 95% 신뢰구간 · 막대가 0에 걸치지 않으면 유의미한 차이 · ◆ = 4개년 종합")


class YearlyTrendChart(Chart):
    """③ 연도별 평균 증가율 추이 (요일유형별 패널)"""

    filename = "topic1_yearly"

    def build(self) -> go.Figure:
        r = self.analyzer.rates(by_year=True)
        fig = make_subplots(rows=1, cols=3, subplot_titles=DAY_TYPES, shared_yaxes=True, horizontal_spacing=0.04)
        for col, dt in enumerate(DAY_TYPES, start=1):
            for hp in [True, False]:
                g = r[(r["day_type"] == dt) & (r["has_park"] == hp)].groupby("year")["rate"]
                m, ci = g.mean(), 1.96 * g.sem()
                fig.add_trace(go.Scatter(
                    x=m.index.astype(str), y=m.values, name=PARK_LABEL[hp], legendgroup=str(hp), showlegend=(col == 1),
                    mode="lines+markers", line=dict(color=Theme.COLORS[hp], width=2.5), marker=dict(size=8),
                    error_y=dict(type="data", array=ci.values, thickness=1.4, width=4),
                    hovertemplate="%{x}년 · 평균 %{y:+.2f}%<extra>" + PARK_LABEL[hp] + "</extra>",
                ), row=1, col=col)
            fig.add_hline(y=0, line=dict(color="#9ca3af", width=1), row=1, col=col)
        fig.update_yaxes(title_text="평균 증가율 (%) ± 95% CI", ticksuffix="%", row=1, col=1)
        fig.update_layout(height=500)
        Theme.apply(fig, "연도별 1월 → 5월 증가율 추이", "4개년 모두 같은 방향인지 확인")
        fig.update_layout(legend=dict(y=1.16), margin=dict(t=130))   # 패널 제목과 겹치지 않게
        return fig


# ──────────────────────────────────────────────
# 리포트
# ──────────────────────────────────────────────
class Topic1Report:
    """차트 묶음을 개별 HTML + 통합 미리보기 페이지 + 통계표로 내보내기"""

    def __init__(self, analyzer: SeasonalChangeAnalyzer, charts: list, out_dir: Path):
        self.analyzer = analyzer
        self.charts = charts
        self.out_dir = Path(out_dir)

    def export(self) -> None:
        for chart in self.charts:
            print(f"  저장: {chart.save(self.out_dir)}")
        self._export_stats()
        self._export_preview()

    def _export_stats(self) -> None:
        path = self.out_dir / "stats_summary.csv"
        self.analyzer.summary().round(4).to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  저장: {path}")

    def _export_preview(self) -> None:
        divs = "\n".join(
            f"<section class='card'>{c.to_div(include_js=(i == 0))}</section>" for i, c in enumerate(self.charts)
        )
        html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>주제 1 · 공원 유무와 계절별 생활인구</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
<style>
 body {{ margin:0; background:#f3f4f6; font-family:{Theme.FONT}; color:#1f2937; }}
 header {{ padding:40px 24px 8px; max-width:1100px; margin:auto; }}
 h1 {{ font-size:26px; margin:0 0 6px; }}
 header p {{ color:#6b7280; margin:0; }}
 main {{ max-width:1100px; margin:auto; padding:16px 24px 48px; display:grid; gap:24px; }}
 .card {{ background:#fff; border-radius:16px; box-shadow:0 4px 18px rgba(0,0,0,.06); padding:8px; }}
</style></head><body>
<header><h1>공원 보유 여부에 따른 낮 시간대 생활인구의 계절적 증가폭</h1>
<p>서울시 424개 행정동 · 2023~2026년 1월 vs 5월 · 10~17시</p></header>
<main>{divs}</main></body></html>"""
        path = self.out_dir / "index.html"
        path.write_text(html, encoding="utf-8")
        print(f"  저장: {path}")


if __name__ == "__main__":
    names = DongNameLookup(Path("HangJeongDong_ver20260701.geojson"))
    analyzer = SeasonalChangeAnalyzer(Path("daytime_weekend_pop.csv"), names)
    charts = [RateDistributionChart(analyzer), DifferenceForestChart(analyzer), YearlyTrendChart(analyzer)]
    Topic1Report(analyzer, charts, Path("docs/topic1")).export()
    print(analyzer.summary()[["day_type", "period", "diff", "ci_low", "ci_high", "p_welch", "p_mwu"]].round(4).to_string())
