"""
[주제 1 & 서울 지도] 공원 유무별 생활인구 계절 변동 통계 검정 및 Plotly 시각화 모듈

1. 파일 내용 (What is inside):
   - Theme: Pretendard 폰트 및 모노크롬 + 단일 포인트 컬러(#0F766E) 차트 스타일 정의.
   - DongNameLookup: 서울 424개 행정동 · 25개 자치구 경량 GeoJSON 로더 및 행정동명('구 동') 조회.
   - BaseAnalyzer: 1월 대비 5월 증가율 및 요약표 계산을 표준화한 통계 분석 추상 기반 클래스.
   - SeasonalChangeAnalyzer: 1월 대비 5월 낮 시간대 인구 증가율 계산 및 공원 유무 그룹 비교 엔진.
   - Chart (추상 기본 클래스): 인터랙티브 그래프 생성(`build()`), 파일 저장(`save()`), HTML div 추출(`to_div()`) 규격화.
   - SeoulParkMapChart: 서울시 424개 행정동 · 25개 자치구 구분 벡터 지도 + 127개 주요 공원 위치 오버레이.
   - RateDistributionChart: 주말·평일·전체 증가율 분포 비교 박스플롯.
   - YearlyTrendChart: 2023~2026년 4개년 연속 공원 동 우세를 확인하는 연도별 추이선 그래프.
"""
import json
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEOUL_GEOJSON_PATH = PROJECT_ROOT / "data" / "processed" / "seoul_dongs.geojson"
SEOUL_GU_GEOJSON_PATH = PROJECT_ROOT / "data" / "processed" / "seoul_gus.geojson"
RAW_GEOJSON_PATH = PROJECT_ROOT / "data" / "raw" / "HangJeongDong_ver20260701.geojson"
PARK_MAP_CSV_PATH = PROJECT_ROOT / "data" / "raw" / "park_dong_map.csv"

WEEKEND, WEEKDAY, ALL_DAYS = "주말·공휴일", "평일", "전체"
DAY_TYPES = [WEEKEND, WEEKDAY, ALL_DAYS]
PARK_LABEL = {True: "공원 보유", False: "공원 미보유"}

CODE_REMAP = {
    "11230515": "11230536", "11230533": "11230536",
    "11305595": "11305590", "11305603": "11305600", "11305608": "11305606",
    "11305615": "11305610", "11305625": "11305620", "11305635": "11305630",
    "11680675": "11680740",
    "11740525": "11740520", "11740526": "11740520",
    "11530800": "11530780",
}
MERGED_DONG_NAMES = {
    "11230536": "동대문구 용신동",
    "11740520": "강동구 상일동",
    "11680740": "강남구 개포3동(일원2)",
    "11530780": "구로구 오류2·항동",
}


class Theme:
    ACCENT = "#0F766E"
    MUTED = "#9CA3AF"
    COLORS = {True: ACCENT, False: MUTED}
    FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Inter', sans-serif"

    @classmethod
    def apply(cls, fig: go.Figure, title: str, subtitle: str = "") -> go.Figure:
        text = (
            f"<span style='color:#111827;font-size:16px;font-weight:600;letter-spacing:-0.02em'>{title}</span>"
            + (f"<br><span style='font-size:12.5px;color:#6B7280;font-weight:400'>{subtitle}</span>" if subtitle else "")
        )
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            title=dict(text=text, x=0.01, xanchor="left"),
            font=dict(family=cls.FONT, size=12.5, color="#374151"),
            hoverlabel=dict(font_family=cls.FONT, bgcolor="#111827", font_color="#FAFAFA", bordercolor="#111827"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=12, color="#374151")),
            margin=dict(t=88, l=56, r=24, b=48),
        )
        fig.update_xaxes(showgrid=False, linecolor="#E5E7EB", tickfont=dict(color="#6B7280"))
        fig.update_yaxes(gridcolor="#F3F4F6", zerolinecolor="#E5E7EB", tickfont=dict(color="#6B7280"))
        return fig


class NameLookup(Protocol):
    """행정동 코드 → 이름 조회 전용 경량 인터페이스 (ISP)"""

    def name(self, dong_cd: str) -> str:
        ...


class DongNameLookup:
    """서울 424개 행정동 · 25개 자치구 경량 GeoJSON 및 행정동명('구 동') 조회"""

    def __init__(self, geojson_path: Path = SEOUL_GEOJSON_PATH):
        self.geojson, self.gu_geojson = self._load_or_build(Path(geojson_path))
        self._names = {ft["properties"]["dong_cd"]: ft["properties"]["dong_nm"] for ft in self.geojson["features"]}
        self.dong_to_gu = {cd: nm.split()[0] for cd, nm in self._names.items()}

    @staticmethod
    def _stitch_gu_polygons(polys: list) -> list:
        """구 내부 공유 경계를 상쇄해 25개 자치구 외곽 경계 폴리곤을 추출"""
        directed = Counter()
        for poly in polys:
            for ring in poly:
                pts = [(round(p[0], 5), round(p[1], 5)) for p in ring]
                for i in range(len(pts) - 1):
                    if pts[i] != pts[i + 1]:
                        directed[(pts[i], pts[i + 1])] += 1

        adj = defaultdict(list)
        for (a, b), cnt in directed.items():
            if cnt - directed.get((b, a), 0) > 0:
                adj[a].append(b)

        rings = []
        while adj:
            start = next(iter(adj))
            ring = [start]
            cur = adj[start].pop(0)
            if not adj[start]:
                del adj[start]
            while cur != start and cur in adj:
                ring.append(cur)
                nxt = adj[cur].pop(0)
                if not adj[cur]:
                    del adj[cur]
                cur = nxt
            ring.append(start)
            rings.append([[[round(p[0], 4), round(p[1], 4)] for p in ring]])
        return rings

    @classmethod
    def _load_or_build(cls, path: Path) -> tuple[dict, dict]:
        dongs_ok = path.exists()
        gus_ok = SEOUL_GU_GEOJSON_PATH.exists()
        if dongs_ok and gus_ok:
            d_data = json.loads(path.read_text(encoding="utf-8"))
            if d_data.get("features") and "dong_cd" in d_data["features"][0].get("properties", {}):
                return d_data, json.loads(SEOUL_GU_GEOJSON_PATH.read_text(encoding="utf-8"))

        raw_path = path if (path.exists() and path != SEOUL_GEOJSON_PATH) else RAW_GEOJSON_PATH
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        round_coords = lambda obj: round(obj, 4) if isinstance(obj, float) else ([round_coords(x) for x in obj] if isinstance(obj, list) else obj)

        merged = {}
        by_gu = defaultdict(list)
        for ft in raw["features"]:
            cd = str(ft["properties"].get("adm_cd2", ""))[:8]
            if not cd.startswith("11"):
                continue
            gu_nm = ft["properties"]["sggnm"]
            canon = CODE_REMAP.get(cd, cd)
            geom = ft["geometry"]
            raw_polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            by_gu[gu_nm].extend(raw_polys)

            polys = round_coords(raw_polys)
            if canon not in merged:
                name = MERGED_DONG_NAMES.get(canon, " ".join(ft["properties"]["adm_nm"].split()[1:]))
                merged[canon] = {
                    "type": "Feature",
                    "id": canon,
                    "properties": {"dong_cd": canon, "dong_nm": name, "gu_nm": gu_nm},
                    "geometry": {"type": "MultiPolygon", "coordinates": polys},
                }
            else:
                merged[canon]["geometry"]["coordinates"].extend(polys)

        dong_out = {"type": "FeatureCollection", "features": list(merged.values())}
        gu_features = [
            {
                "type": "Feature",
                "id": gu_nm,
                "properties": {"gu_nm": gu_nm},
                "geometry": {"type": "MultiPolygon", "coordinates": cls._stitch_gu_polygons(polys)},
            }
            for gu_nm, polys in sorted(by_gu.items())
        ]
        gu_out = {"type": "FeatureCollection", "features": gu_features}

        SEOUL_GEOJSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        SEOUL_GEOJSON_PATH.write_text(json.dumps(dong_out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        SEOUL_GU_GEOJSON_PATH.write_text(json.dumps(gu_out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return dong_out, gu_out

    def name(self, dong_cd: str) -> str:
        return self._names.get(dong_cd, f"행정동 {dong_cd}")


class BaseAnalyzer(ABC):
    """통계 분석 엔진 추상 기본 클래스 (공통 로딩, 증가율 격차 및 요약표 표준화)"""

    group_col: str = ""
    categories: list[str] = []

    def __init__(self, csv_source: Path | pd.DataFrame, names: NameLookup):
        self.df = csv_source.copy() if isinstance(csv_source, pd.DataFrame) else pd.read_csv(csv_source, dtype={"dong_cd": str})
        self.years = sorted(self.df["year"].unique())
        self.df["dong_nm"] = self.df["dong_cd"].map(names.name)

    @staticmethod
    def compare(rates: pd.DataFrame) -> dict:
        a = rates.loc[rates["has_park"], "rate"]
        b = rates.loc[~rates["has_park"], "rate"]
        return {
            "n_park": len(a),
            "n_none": len(b),
            "mean_park": a.mean(),
            "mean_none": b.mean(),
            "diff": a.mean() - b.mean(),
        }

    @staticmethod
    def _calc_rates(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        p = df.pivot_table(index=keys, columns="month", values="pop", aggfunc="mean").reset_index()
        p = p.rename(columns={1: "jan", 5: "may"})
        p["rate"] = (p["may"] / p["jan"] - 1) * 100
        return p

    def summary(self, **kwargs) -> pd.DataFrame:
        """카테고리 × (연도별 + 4개년) 가설 검정 요약표 공통 생성 (LSP)"""
        yearly = self.rates(by_year=True, **kwargs)
        pooled = self.rates(**kwargs)
        rows = []
        for cat in self.categories:
            for y in self.years:
                sub = yearly[(yearly[self.group_col] == cat) & (yearly["year"] == y)]
                rows.append({self.group_col: cat, "period": str(y), **self.compare(sub)})
            rows.append({self.group_col: cat, "period": "4개년", **self.compare(pooled[pooled[self.group_col] == cat])})
        return pd.DataFrame(rows)

    @abstractmethod
    def rates(self, **kwargs) -> pd.DataFrame:
        ...


class SeasonalChangeAnalyzer(BaseAnalyzer):
    """행정동별 1월 → 5월 생활인구 증가율 계산 및 공원 유무 그룹 비교"""

    group_col = "day_type"
    categories = DAY_TYPES

    def __init__(self, csv_source: Path | pd.DataFrame, names: NameLookup):
        super().__init__(csv_source, names)
        self.monthly = self._with_all_days(self.df)

    @staticmethod
    def _with_all_days(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["day_type"] = df["is_weekend"].map({True: WEEKEND, False: WEEKDAY})
        df["weighted"] = df["pop"] * df["n_days"]
        keys = ["dong_cd", "dong_nm", "year", "month", "has_park"]
        all_days = df.groupby(keys).agg(weighted=("weighted", "sum"), n_days=("n_days", "sum")).reset_index()
        all_days["pop"] = all_days["weighted"] / all_days["n_days"]
        all_days["day_type"] = ALL_DAYS
        cols = keys + ["day_type", "pop"]
        return pd.concat([df[cols], all_days[cols]], ignore_index=True)

    def rates(self, by_year: bool = False) -> pd.DataFrame:
        keys = ["dong_cd", "dong_nm", "has_park", "day_type"] + (["year"] if by_year else [])
        return self._calc_rates(self.monthly, keys)

    def dong_details(self, names: DongNameLookup, parks_by_dong: dict, ages_by_dong: dict) -> dict:
        """행정동별 상세 통계(요일별·연도별·세대별·공원) 집계 반환"""
        pooled = self.rates()
        wk_yearly = self.rates(by_year=True)
        wk_yearly = wk_yearly[wk_yearly["day_type"] == WEEKEND]
        details = {}
        for cd, grp in pooled.groupby("dong_cd"):
            day_stats = {
                r["day_type"]: {"jan": round(float(r["jan"])), "may": round(float(r["may"])), "rate": round(float(r["rate"]), 2)}
                for _, r in grp.iterrows()
            }
            yr_sub = wk_yearly[wk_yearly["dong_cd"] == cd].sort_values("year")
            details[cd] = {
                "name": names.name(cd),
                "gu": names.dong_to_gu.get(cd, ""),
                "has_park": bool(grp["has_park"].iloc[0]),
                "day_stats": day_stats,
                "yearly": {str(int(r["year"])): round(float(r["rate"]), 2) for _, r in yr_sub.iterrows()},
                "ages": ages_by_dong.get(cd, []),
                "parks": parks_by_dong.get(cd, []),
            }
        return details

    def gu_summaries(self, dong_to_gu: dict[str, str], parks_by_gu: dict) -> dict:
        """자치구별 평균 증가율·소속 행정동 목록·주요 공원 요약 반환"""
        wk = self.rates()
        wk = wk[wk["day_type"] == WEEKEND].copy()
        wk["gu_nm"] = wk["dong_cd"].map(dong_to_gu)
        gus = {}
        for gu_nm, grp in wk.groupby("gu_nm"):
            p_grp = grp[grp["has_park"]]
            n_grp = grp[~grp["has_park"]]
            gus[gu_nm] = {
                "name": gu_nm,
                "n_dongs": int(len(grp)),
                "n_park": int(grp["has_park"].sum()),
                "mean_rate": round(float(grp["rate"].mean()), 2),
                "park_rate": round(float(p_grp["rate"].mean()), 2) if len(p_grp) else None,
                "none_rate": round(float(n_grp["rate"].mean()), 2) if len(n_grp) else None,
                "dongs": [
                    {
                        "cd": r["dong_cd"],
                        "name": r["dong_nm"].split()[-1],
                        "rate": round(float(r["rate"]), 2),
                        "has_park": bool(r["has_park"]),
                    }
                    for _, r in grp.sort_values("rate", ascending=False).iterrows()
                ],
                "parks": sorted(parks_by_gu.get(gu_nm, []), key=lambda x: -x["area_ha"]),
            }
        return gus


class Chart(ABC):
    """모든 차트의 공통 기반: build()로 Figure 생성, save()로 HTML 저장"""

    filename: str = "chart"

    def __init__(self, analyzer: BaseAnalyzer):
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
    def build_yearly_panels(r: pd.DataFrame, group_col: str, categories: list[str], shared_yaxes: bool = True) -> go.Figure:
        fig = make_subplots(rows=1, cols=len(categories), subplot_titles=categories,
                            shared_yaxes=shared_yaxes, horizontal_spacing=0.05)
        for col, cat in enumerate(categories, start=1):
            sub = r[r[group_col] == cat]
            for hp in [True, False]:
                m = sub[sub["has_park"] == hp].groupby("year")["rate"].mean()
                fig.add_trace(go.Scatter(
                    x=m.index.astype(str), y=m.values, name=PARK_LABEL[hp],
                    legendgroup=str(hp), showlegend=(col == 1),
                    mode="lines+markers", line=dict(color=Theme.COLORS[hp], width=2.2), marker=dict(size=7),
                    hovertemplate="%{x}년 · " + PARK_LABEL[hp] + " %{y:+.2f}%<extra>" + cat + "</extra>",
                ), row=1, col=col)
            fig.add_hline(y=0, line=dict(color="#E5E7EB", width=1), row=1, col=col)
        return fig


class SeoulParkMapChart(Chart):
    """[첫 화면 개요] 서울시 424개 행정동 · 25개 자치구 경계 벡터 지도 + 127개 공원 오버레이"""

    filename = "seoul_overview_map"

    def __init__(self, analyzer: SeasonalChangeAnalyzer, names: DongNameLookup, park_csv: Path = PARK_MAP_CSV_PATH):
        super().__init__(analyzer)
        self.names = names
        self.park_csv = Path(park_csv)

    def _gu_border_lines(self) -> tuple[list, list]:
        lons, lats = [], []
        for ft in self.names.gu_geojson["features"]:
            for poly in ft["geometry"]["coordinates"]:
                ring = poly[0]
                lons.extend([p[0] for p in ring] + [None])
                lats.extend([p[1] for p in ring] + [None])
        return lons, lats

    def _park_dong_border_lines(self, park_cds: set) -> tuple[list, list]:
        lons, lats = [], []
        for ft in self.names.geojson["features"]:
            if ft["properties"]["dong_cd"] not in park_cds:
                continue
            for poly in ft["geometry"]["coordinates"]:
                ring = poly[0]
                lons.extend([p[0] for p in ring] + [None])
                lats.extend([p[1] for p in ring] + [None])
        return lons, lats

    def build(self) -> go.Figure:
        r = self.analyzer.rates()
        wk = r[r["day_type"] == WEEKEND].copy()
        wk["park_status"] = wk["has_park"].map(PARK_LABEL)
        park_cds = set(wk.loc[wk["has_park"], "dong_cd"])

        parks = pd.read_csv(self.park_csv, dtype={"dong_cd": str})
        parks["canon_cd"] = parks["dong_cd"].astype(str).str[:8].map(lambda c: CODE_REMAP.get(c, c))
        rgn_series = parks["rgn"].astype(str).str.strip()
        parks["rgn_clean"] = parks["rgn"].where(
            parks["rgn"].notna() & (rgn_series != "") & (rgn_series.str.lower() != "nan"),
            parks["canon_cd"].map(self.names.dong_to_gu),
        ).fillna("")
        parks["area_m2"] = pd.to_numeric(parks["area_m2"], errors="coerce").fillna(10000)
        parks["area_ha"] = parks["area_m2"] / 10000.0
        sizes = np.clip(np.log1p(parks["area_m2"]) * 0.9 - 2.5, 4.5, 11.5)

        rate_scale = [[0.0, "#CBD5E1"], [0.44, "#F8FAFC"], [1.0, Theme.ACCENT]]

        fig = go.Figure()
        # Trace 0: 424개 행정동 단계구분도
        fig.add_trace(go.Choropleth(
            geojson=self.names.geojson,
            locationmode="geojson-id",
            locations=wk["dong_cd"].tolist(),
            z=wk["rate"].tolist(),
            zmin=-12, zmid=0, zmax=15,
            colorscale=rate_scale,
            marker_line_width=0.6,
            marker_line_color="#E5E7EB",
            colorbar=dict(
                title=dict(text="증가율(%)", font=dict(size=11, color="#6B7280")),
                ticksuffix="%", thickness=11, len=0.68, y=0.5, tickfont=dict(size=11, color="#6B7280"),
            ),
            customdata=np.stack([wk["dong_nm"], wk["park_status"], wk["jan"], wk["may"], wk["rate"]], axis=-1).tolist(),
            hovertemplate=(
                "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
                "1월 %{customdata[2]:,.0f}명 → 5월 %{customdata[3]:,.0f}명 · <b>%{customdata[4]:+.2f}%</b><extra></extra>"
            ),
            name="행정동",
            showlegend=False,
        ))

        # Trace 1: 25개 자치구 외곽 경계선
        gu_lons, gu_lats = self._gu_border_lines()
        fig.add_trace(go.Scattergeo(
            lon=gu_lons,
            lat=gu_lats,
            mode="lines",
            line=dict(color="#6B7280", width=1.1, dash="dot"),
            hoverinfo="skip",
            name="자치구 경계",
            showlegend=True,
        ))

        # Trace 2 & 3: 공원 보유 행정동(102개) 강조 테두리 (흰색 외곽선 + 짙은 청록색 실선)
        pk_lons, pk_lats = self._park_dong_border_lines(park_cds)
        fig.add_trace(go.Scattergeo(
            lon=pk_lons,
            lat=pk_lats,
            mode="lines",
            line=dict(color="#FFFFFF", width=3.4),
            hoverinfo="skip",
            showlegend=False,
        ))
        fig.add_trace(go.Scattergeo(
            lon=pk_lons,
            lat=pk_lats,
            mode="lines",
            line=dict(color=Theme.ACCENT, width=1.9),
            hoverinfo="skip",
            name="공원 보유 동 경계",
            showlegend=True,
        ))

        # Trace 4: 127개 주요 공원 위치
        fig.add_trace(go.Scattergeo(
            lat=parks["ycrd"].tolist(),
            lon=parks["xcrd"].tolist(),
            meta="park",
            mode="markers",
            marker=dict(size=sizes.tolist(), color="#111827", opacity=0.85, line=dict(color="#FFFFFF", width=0.9)),
            customdata=np.stack([parks["park_nm"], parks["rgn_clean"], parks["area_ha"], parks["park_addr"].fillna(""), parks["park_nm"]], axis=-1).tolist(),
            hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]}) · 면적 %{customdata[2]:,.1f} ha<extra>주요 공원</extra>",
            name="주요 공원",
            showlegend=True,
        ))

        fig.update_geos(
            fitbounds="locations",
            visible=False,
            projection_type="mercator",
            bgcolor="rgba(0,0,0,0)",
        )
        fig.update_layout(height=580)
        Theme.apply(
            fig,
            "서울시 행정동 봄철 생활인구 증가율 및 주요 공원 분포",
            "짙은 청록색 실선 테두리 = 공원 보유 동 · 점선 = 자치구 경계 · 자치구 클릭 또는 상단 필터로 구별 확대",
        )
        fig.update_layout(margin=dict(t=68, l=8, r=8, b=8), legend=dict(x=0.98, y=0.04, yanchor="bottom"))
        return fig


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
                marker=dict(color=Theme.COLORS[hp], size=3.5, opacity=0.45),
                line=dict(width=1.5), boxpoints="all", jitter=0.42, pointpos=0, boxmean=True,
                customdata=np.stack([s["dong_nm"], s["jan"], s["may"]], axis=-1),
                hovertemplate="<b>%{customdata[0]}</b><br>1월 %{customdata[1]:,.0f}명 → 5월 %{customdata[2]:,.0f}명"
                              "<br>증가율 %{y:+.2f}%<extra>" + PARK_LABEL[hp] + "</extra>",
            ))
        for dt in DAY_TYPES:
            c = self.analyzer.compare(r[r["day_type"] == dt])
            fig.add_annotation(
                x=dt, y=1.01, yref="paper", yanchor="bottom", showarrow=False,
                text=f"<b style='color:#0F766E'>{c['diff']:+.2f}%p</b>",
                font=dict(size=12, color="#374151"),
            )
        fig.add_hline(y=0, line=dict(color="#D1D5DB", width=1))
        fig.update_layout(boxmode="group", boxgroupgap=0.28, height=480,
                          xaxis=dict(categoryorder="array", categoryarray=DAY_TYPES),
                          yaxis=dict(title="1월 → 5월 증가율 (%)", ticksuffix="%", zeroline=False))
        Theme.apply(fig, "공원 보유 여부에 따른 계절 증가율 분포",
                    "2023~2026년 낮(10~17시) 평균 · 점 하나 = 행정동 하나")
        fig.update_layout(legend=dict(y=1.12), margin=dict(t=106, l=56, r=24, b=48))
        return fig


class YearlyTrendChart(Chart):
    """② 연도별 평균 증가율 추이 (요일유형별 패널)"""

    filename = "topic1_yearly"

    def build(self) -> go.Figure:
        fig = self.build_yearly_panels(self.analyzer.rates(by_year=True), "day_type", DAY_TYPES, shared_yaxes=True)
        fig.update_yaxes(title_text="평균 증가율 (%)", ticksuffix="%", row=1, col=1)
        fig.update_layout(height=420)
        Theme.apply(fig, "연도별 1월 → 5월 생활인구 증가율 추이", "4개년 연속 공원 보유 동의 증가율이 우세한지 검증")
        fig.update_layout(legend=dict(y=1.16), margin=dict(t=108, l=56, r=24, b=44))
        return fig


class ReportExporter:
    """차트 묶음 HTML + 통계표 CSV + 단독 미리보기 웹페이지 통합 내보내기 공통 기반 클래스"""

    title: str = "분석 리포트"
    subtitle: str = ""

    def __init__(self, analyzer: BaseAnalyzer, charts: list, out_dir: Path):
        self.analyzer = analyzer
        self.charts = charts
        self.out_dir = Path(out_dir)

    def export(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for chart in self.charts:
            print(f"  저장: {chart.save(self.out_dir)}")
        path = self.out_dir / "stats_summary.csv"
        self.analyzer.summary().round(4).to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  저장: {path}")
        self._export_preview()

    def _export_preview(self) -> None:
        divs = "\n".join(
            f"<section class='card'>{c.to_div(include_js=(i == 0))}</section>" for i, c in enumerate(self.charts)
        )
        html = (
            f"<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{self.title}</title>"
            f"<link rel='stylesheet' href='https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css'>"
            f"<style>body{{margin:0;background:#FAFAFA;font-family:{Theme.FONT};color:#374151;}}"
            f"header{{padding:48px 32px 16px;max-width:1120px;margin:auto;}}h1{{font-size:24px;color:#111827;letter-spacing:-0.025em;margin:0 0 6px;}}"
            f"header p{{color:#6B7280;margin:0;font-size:14px;}}main{{max-width:1120px;margin:auto;padding:24px 32px 64px;display:grid;gap:28px;}}"
            f".card{{background:#FFF;border:1px solid #E5E7EB;border-radius:6px;padding:16px;}}</style></head>"
            f"<body><header><h1>{self.title}</h1><p>{self.subtitle}</p></header><main>{divs}</main></body></html>"
        )
        path = self.out_dir / "index.html"
        path.write_text(html, encoding="utf-8")
        print(f"  저장: {path}")


class Topic1Report(ReportExporter):
    title = "공원 보유 여부에 따른 낮 시간대 생활인구의 계절적 증가폭"
    subtitle = "서울시 424개 행정동 · 2023~2026년 1월 vs 5월 · 10~17시"


if __name__ == "__main__":
    names = DongNameLookup()
    analyzer = SeasonalChangeAnalyzer(PROJECT_ROOT / "data" / "processed" / "daytime_weekend_pop.csv", names)
    charts = [RateDistributionChart(analyzer), YearlyTrendChart(analyzer)]
    Topic1Report(analyzer, charts, PROJECT_ROOT / "docs" / "topic1").export()
    print(analyzer.summary()[["day_type", "period", "mean_park", "mean_none", "diff"]].round(4).to_string())
