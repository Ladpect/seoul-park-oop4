"""
[통합 대시보드 빌더] 서울 전체 지도(개요) + 주제 1 + 주제 2를 미니멀 프로덕트 UI로 통합

1. 역할:
   - 비대칭 Split View와 리스트형 테이블, 벡터 SVG 지도를 조합해 `docs/index.html`을 생성합니다.
   - 상단 자치구 필터로 특정 구(예: 노원구, 종로구)를 고르면 해당 구의 행정동만 지도에 확대 표시되며,
     각 행정동 도형 호버 시 빛남 효과 및 클릭 시 상세 통계 인스펙터를 제공합니다.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ANALYSIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ANALYSIS_DIR.parent
for p in (ANALYSIS_DIR, PROJECT_ROOT / "preprocessing"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from newdata import ParkMapSource
from topic1_visualize import (
    CODE_REMAP,
    PARK_MAP_CSV_PATH,
    Chart,
    DongNameLookup,
    RateDistributionChart,
    SeasonalChangeAnalyzer,
    SeoulParkMapChart,
    YearlyTrendChart,
)
from topic2_visualize import AgeGroupAnalyzer, AgeRateBarChart, AgeYearlyTrendChart

ICON_MAP = (
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"></polygon>'
    '<line x1="9" y1="3" x2="9" y2="18"></line><line x1="15" y1="6" x2="15" y2="21"></line></svg>'
)
ICON_CHART = (
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line>'
    '<line x1="6" y1="20" x2="6" y2="14"></line></svg>'
)
ICON_USERS = (
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>'
    '<circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path>'
    '<path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>'
)


class DashboardBuilder:
    """통합 웹 대시보드 HTML 조립 클래스 (의존성 주입 및 프레젠테이션 책임 캡슐화)"""

    def __init__(
        self,
        t1: SeasonalChangeAnalyzer,
        t2: AgeGroupAnalyzer,
        names: DongNameLookup,
        park_source: ParkMapSource,
        charts: dict[str, Chart],
    ):
        self.t1 = t1
        self.t2 = t2
        self.names = names
        self.park_source = park_source
        self.charts = charts

    def _build_detail_payload(self) -> dict:
        """분석기(t1, t2)와 공원·지리 저장소 결과를 대시보드용 상세 JSON으로 결합"""
        parks_df = self.park_source.load()
        parks_df["canon_cd"] = parks_df["dong_cd"].str[:8].map(lambda c: CODE_REMAP.get(c, c))
        parks_df["area_m2"] = pd.to_numeric(parks_df["area_m2"], errors="coerce").fillna(0)

        parks_by_dong, parks_by_gu, parks_list = {}, {}, []
        for _, row in parks_df.iterrows():
            fclt = str(row["main_fclt"]) if pd.notna(row["main_fclt"]) else ""
            dong_gu = self.names.dong_to_gu.get(row["canon_cd"], str(row["rgn"]))
            info = {
                "name": str(row["park_nm"]),
                "gu": str(row["rgn"]),
                "dong_gu": dong_gu,
                "dong_cd": row["canon_cd"],
                "dong_nm": self.names.name(row["canon_cd"]),
                "area_ha": round(float(row["area_m2"]) / 10000.0, 1),
                "addr": str(row["park_addr"]) if pd.notna(row["park_addr"]) else "",
                "fclt": fclt[:140] + ("..." if len(fclt) > 140 else ""),
            }
            parks_list.append(info)
            parks_by_dong.setdefault(row["canon_cd"], []).append(info)
            parks_by_gu.setdefault(dong_gu, []).append(info)

        ages_by_dong = self.t2.dong_age_details()
        dongs = self.t1.dong_details(self.names, parks_by_dong, ages_by_dong)
        gus = self.t1.gu_summaries(self.names.dong_to_gu, parks_by_gu)

        def extract_lines(features, filter_set=None):
            res = {}
            for ft in features:
                key = ft["properties"].get("gu_nm") if filter_set is None else ft["properties"]["dong_cd"]
                if filter_set is not None and key not in filter_set:
                    continue
                group_key = key if filter_set is None else self.names.dong_to_gu.get(key, "")
                bucket = res.setdefault(group_key, {"lon": [], "lat": []})
                for poly in ft["geometry"]["coordinates"]:
                    ring = poly[0]
                    bucket["lon"].extend([p[0] for p in ring] + [None])
                    bucket["lat"].extend([p[1] for p in ring] + [None])
            return res

        park_cd_set = {cd for cd, info in dongs.items() if info["has_park"]}
        return {
            "dongs": dongs,
            "gus": gus,
            "parks": parks_list,
            "gu_borders": extract_lines(self.names.gu_geojson["features"]),
            "park_dong_borders": extract_lines(self.names.geojson["features"], filter_set=park_cd_set),
        }

    def build_html(self) -> str:
        t1_sum = self.t1.summary()
        t1_wknd_rows = t1_sum[t1_sum["day_type"] == "주말·공휴일"]
        t1_wknd = t1_wknd_rows[t1_wknd_rows["period"] == "4개년"].iloc[0]

        r_wk = self.t1.rates()
        top5_parks = (
            r_wk[(r_wk["day_type"] == "주말·공휴일") & (r_wk["has_park"])]
            .nlargest(5, "rate")[["dong_cd", "dong_nm", "jan", "may", "rate"]]
        )
        top5_rows_html = "\n".join(
            f"<tr class='clickable-row' onclick=\"showDongDetail('{row['dong_cd']}')\">"
            f"<td>{row['dong_nm']}</td>"
            f"<td class='num'>{row['jan']:,.0f} → {row['may']:,.0f}</td>"
            f"<td class='num accent'>{row['rate']:+.1f}%</td></tr>"
            for _, row in top5_parks.iterrows()
        )

        t1_table_rows = "\n".join(
            f"<tr class='{'row-highlight' if row['period'] == '4개년' else ''}'>"
            f"<td>{row['period']}</td>"
            f"<td class='num'>{row['mean_park']:+.2f}%</td>"
            f"<td class='num'>{row['mean_none']:+.2f}%</td>"
            f"<td class='num accent'>{row['diff']:+.2f}%p</td></tr>"
            for _, row in t1_wknd_rows.iterrows()
        )

        t2_pooled = self.t2.summary().query("period == '4개년'")
        t2_ranked = t2_pooled[t2_pooled["age_group"] != "전체 인구"].sort_values("diff", ascending=False)
        kids = t2_pooled[t2_pooled["age_group"] == "유아동 (0~9세)"].iloc[0]

        t2_table_rows = "\n".join(
            f"<tr><td>{row['age_group']}</td>"
            f"<td class='num'>{row['mean_park']:+.2f}%</td>"
            f"<td class='num'>{row['mean_none']:+.2f}%</td>"
            f"<td class='num accent'>{row['diff']:+.2f}%p</td></tr>"
            for _, row in t2_ranked.iterrows()
        )

        detail_payload = self._build_detail_payload()
        gu_options = "\n".join(f'<option value="{gu}">{gu}</option>' for gu in sorted(detail_payload["gus"].keys()))
        detail_json = json.dumps(detail_payload, ensure_ascii=False, separators=(",", ":"))
        map_chart = self.charts["map"]
        dist_chart = self.charts["dist"]
        yearly_chart = self.charts["yearly"]
        age_bar_chart = self.charts["age_bar"]
        age_trend_chart = self.charts["age_trend"]

        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>서울시 도시공원이 생활인구에 미치는 영향</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
  <style>
    :root {{
      --bg: #FAFAFA;
      --surface: #FFFFFF;
      --border: #E5E7EB;
      --text-strong: #111827;
      --text-body: #374151;
      --text-muted: #6B7280;
      --accent: #0F766E;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      font-family: Pretendard, -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
      color: var(--text-body);
      line-height: 1.65;
      -webkit-font-smoothing: antialiased;
    }}
    .container {{ max-width: 1260px; margin: 0 auto; padding: 0 36px; }}

    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 40px 0 28px;
    }}
    .eyebrow {{
      font-size: 11.5px; font-weight: 600; letter-spacing: 0.08em;
      text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;
    }}
    h1 {{
      margin: 0 0 10px; font-size: 28px; font-weight: 700;
      letter-spacing: -0.03em; color: var(--text-strong); line-height: 1.25;
    }}
    header p {{ margin: 0; font-size: 15px; color: var(--text-body); max-width: 740px; }}

    .nav-tabs {{
      background: var(--surface); border-bottom: 1px solid var(--border);
      position: sticky; top: 0; z-index: 50;
    }}
    .nav-list {{ display: flex; gap: 28px; }}
    .tab-btn {{
      display: inline-flex; align-items: center; gap: 7px;
      padding: 15px 2px; font-size: 14px; font-weight: 500;
      color: var(--text-muted); background: transparent;
      border: none; border-bottom: 2px solid transparent;
      cursor: pointer; font-family: inherit;
      transition: color 0.15s ease, border-color 0.15s ease;
    }}
    .tab-btn:hover {{ color: var(--text-strong); }}
    .tab-btn.active {{ color: var(--accent); font-weight: 600; border-bottom-color: var(--accent); }}

    main {{ padding: 40px 0 72px; }}
    .tab-pane {{ display: none; }}
    .tab-pane.active {{ display: block; }}

    .panel {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 6px; padding: 28px 30px;
    }}
    .chart-panel {{ padding: 20px 24px; }}
    .split-left {{
      display: grid; grid-template-columns: 375px 1fr;
      gap: 28px; align-items: start; margin-bottom: 28px;
    }}
    .split-right {{
      display: grid; grid-template-columns: 1fr 375px;
      gap: 28px; align-items: start; margin-top: 28px;
    }}
    @media (max-width: 980px) {{ .split-left, .split-right {{ grid-template-columns: 1fr; }} }}

    /* 지도 상단 자치구 선택 & 모드 컨트롤 바 */
    .map-toolbar {{
      display: flex; align-items: center; justify-content: space-between;
      flex-wrap: wrap; gap: 12px;
      padding-bottom: 16px; margin-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }}
    .toolbar-left {{ display: flex; align-items: center; gap: 8px; }}
    .toolbar-label {{ font-size: 12px; font-weight: 600; color: var(--text-muted); }}
    .gu-select {{
      font-family: inherit; font-size: 13px; font-weight: 500;
      color: var(--text-strong); background: #FAFAFA;
      border: 1px solid var(--border); border-radius: 4px;
      padding: 6px 10px; cursor: pointer; outline: none;
    }}
    .gu-select:focus {{ border-color: var(--accent); }}
    .segmented {{
      display: inline-flex; background: #FAFAFA; border: 1px solid var(--border);
      border-radius: 4px; padding: 2px;
    }}
    .seg-btn {{
      font-family: inherit; font-size: 12px; font-weight: 500;
      color: var(--text-muted); background: transparent;
      border: none; border-radius: 3px; padding: 5px 10px; cursor: pointer;
    }}
    .seg-btn.active {{
      background: var(--surface); color: var(--accent);
      font-weight: 600; border: 1px solid var(--border);
    }}

    .section-kicker {{ font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; }}
    .hero-stat {{
      font-size: 36px; font-weight: 700; letter-spacing: -0.03em;
      color: var(--accent); font-variant-numeric: tabular-nums;
      line-height: 1.1; margin-bottom: 8px;
    }}
    .hero-desc {{
      font-size: 13.5px; color: var(--text-body); margin: 0 0 20px;
      padding-bottom: 18px; border-bottom: 1px solid var(--border);
    }}
    .sub-heading {{
      font-size: 12.5px; font-weight: 600; color: var(--text-strong);
      letter-spacing: -0.01em; margin: 20px 0 8px;
    }}

    table.clean-table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
    table.clean-table th {{
      text-align: left; font-weight: 500; font-size: 11px;
      color: var(--text-muted); padding: 7px 4px; border-bottom: 1px solid var(--border);
    }}
    table.clean-table th.num, table.clean-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    table.clean-table td {{ padding: 8px 4px; border-bottom: 1px solid #F3F4F6; color: var(--text-body); }}
    table.clean-table tr:last-child td {{ border-bottom: none; }}
    table.clean-table tr.row-highlight td {{ font-weight: 600; color: var(--text-strong); background: #FAFAFA; }}
    tr.clickable-row {{ cursor: pointer; transition: background-color 0.12s ease; }}
    tr.clickable-row:hover td {{ background: #F3F4F6; }}
    .accent {{ color: var(--accent) !important; font-weight: 600; }}
    .muted {{ color: var(--text-muted) !important; }}

    .back-btn {{
      display: inline-flex; align-items: center; gap: 5px;
      font-size: 12px; font-weight: 500; color: var(--text-muted);
      background: #FAFAFA; border: 1px solid var(--border); border-radius: 4px;
      padding: 5px 10px; cursor: pointer; font-family: inherit; margin-bottom: 14px;
    }}
    .back-btn:hover {{ color: var(--text-strong); border-color: #D1D5DB; }}
    .detail-header {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px; }}
    .detail-title {{ font-size: 20px; font-weight: 700; letter-spacing: -0.02em; color: var(--text-strong); margin: 0; }}
    .status-tag {{
      font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 4px;
      border: 1px solid var(--border); color: var(--text-body); background: #FAFAFA; white-space: nowrap;
    }}
    .status-tag.has-park {{ border-color: #99F6E4; color: var(--accent); background: #F0FDFA; }}
    .gu-link {{ cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }}
    .gu-link:hover {{ color: var(--accent); }}
    .year-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-top: 6px; }}
    .year-cell {{
      background: #FAFAFA; border: 1px solid var(--border); border-radius: 4px;
      padding: 8px 6px; text-align: center; font-variant-numeric: tabular-nums;
    }}
    .year-cell .yr {{ font-size: 11px; color: var(--text-muted); }}
    .year-cell .val {{ font-size: 13px; font-weight: 600; color: var(--text-strong); margin-top: 2px; }}
    .age-bar-row {{ display: grid; grid-template-columns: 52px 1fr 56px; align-items: center; gap: 8px; padding: 5px 0; font-size: 12px; }}
    .bar-track {{ height: 6px; background: #F3F4F6; border-radius: 3px; overflow: hidden; }}
    .bar-fill {{ height: 100%; background: var(--accent); border-radius: 3px; }}
    .bar-fill.neg {{ background: #9CA3AF; }}
    .scroll-table-wrap {{ max-height: 280px; overflow-y: auto; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
    .park-item {{ border: 1px solid var(--border); border-radius: 4px; padding: 10px 12px; margin-top: 8px; background: #FAFAFA; }}
    .park-item-title {{ font-size: 13px; font-weight: 600; color: var(--text-strong); }}
    .park-item-meta {{ font-size: 11.5px; color: var(--text-muted); margin-top: 2px; }}

    /* SVG 행정동 도형 호버 빛남(Glow) & 선택 강조 */
    .choroplethlocation {{
      transition: filter 0.15s ease, stroke-width 0.15s ease;
      cursor: pointer;
    }}
    .choroplethlocation.is-hovered,
    .choroplethlocation:hover {{
      stroke: #0F766E !important;
      stroke-width: 2.3px !important;
      filter: brightness(1.08) drop-shadow(0 0 6px rgba(15, 118, 110, 0.6));
    }}
    .choroplethlocation.is-selected {{
      stroke: #111827 !important;
      stroke-width: 2.4px !important;
      filter: drop-shadow(0 0 5px rgba(17, 24, 39, 0.45));
    }}

    footer {{
      border-top: 1px solid var(--border); background: var(--surface);
      padding: 28px 0; font-size: 12.5px; color: var(--text-muted);
    }}
  </style>
</head>
<body>

<header>
  <div class="container">
    <div class="eyebrow">Seoul Urban Park Empirical Analysis · 2023–2026</div>
    <h1>서울시 도시공원이 주간 생활인구에 미치는 영향</h1>
    <p>서울 424개 행정동(공원 보유 102개 · 미보유 322개)과 주요 공원 127개소의 4개년 데이터를 결합해 봄철 인구 유입 격차와 세대별 반응도를 검정했습니다.</p>
  </div>
</header>

<nav class="nav-tabs">
  <div class="container nav-list">
    <button class="tab-btn active" onclick="switchTab('overview', this)">{ICON_MAP} 서울 한눈에 보기</button>
    <button class="tab-btn" onclick="switchTab('topic1', this)">{ICON_CHART} 계절별 변동 분석</button>
    <button class="tab-btn" onclick="switchTab('topic2', this)">{ICON_USERS} 세대별 반응도</button>
  </div>
</nav>

<main class="container">

  <section id="overview" class="tab-pane active">
    <div class="split-left">
      <div class="panel">
        <div id="overview-summary">
          <div class="section-kicker">핵심 발견 · 주말 낮(10–17시)</div>
          <div class="hero-stat">{t1_wknd['diff']:+.2f}%p</div>
          <p class="hero-desc">
            겨울(1월) 대비 봄(5월) 생활인구 증가율에서 공원 보유 동({t1_wknd['mean_park']:+.2f}%)이
            미보유 동({t1_wknd['mean_none']:+.2f}%)보다 유의미하게 앞섰습니다.
          </p>

          <table class="clean-table">
            <tbody>
              <tr><td>분석 행정동</td><td class="num">424개 동 (25개 자치구)</td></tr>
              <tr><td>표시 공원 수</td><td class="num">127개 주요 공원</td></tr>
              <tr><td>분석 시간대</td><td class="num">주말·공휴일 낮 10–17시</td></tr>
              <tr><td>최대 수혜 세대</td><td class="num accent">유아동 0–9세 ({kids['diff']:+.2f}%p)</td></tr>
            </tbody>
          </table>

          <div class="sub-heading">봄철 증가율 상위 공원 보유 동 TOP 5</div>
          <table class="clean-table">
            <thead>
              <tr><th>행정동</th><th class="num">1월 → 5월</th><th class="num">증가율</th></tr>
            </thead>
            <tbody>
              {top5_rows_html}
            </tbody>
          </table>
        </div>

        <div id="overview-detail" style="display:none;"></div>
      </div>

      <div class="panel chart-panel" id="map-panel">
        <div class="map-toolbar">
          <div class="toolbar-left">
            <span class="toolbar-label">자치구 필터</span>
            <select id="gu-select" class="gu-select" onchange="selectGu(this.value)">
              <option value="ALL">서울 전체 (424개 동)</option>
              {gu_options}
            </select>
            <button id="gu-reset-btn" class="back-btn" style="margin:0;display:none;" onclick="selectGu('ALL')">전체 보기</button>
          </div>
          <div class="segmented">
            <button class="seg-btn active" onclick="setColorMode('rate', this)">봄철 증가율 (%)</button>
            <button class="seg-btn" onclick="setColorMode('park', this)">공원 보유 여부</button>
          </div>
        </div>
        {map_chart.to_div(include_js=True)}
      </div>
    </div>
  </section>

  <section id="topic1" class="tab-pane">
    <div class="split-left">
      <div class="panel">
        <div class="section-kicker">주제 1 · 연도별 추이 비교</div>
        <div class="hero-stat">4 / 4개년</div>
        <p class="hero-desc">
          2023년부터 2026년까지 매년 공원 보유 행정동의 봄철 생활인구 증가율이 일관되게 높았습니다.
        </p>

        <table class="clean-table">
          <thead>
            <tr><th>기간</th><th class="num">공원</th><th class="num">미보유</th><th class="num">격차</th></tr>
          </thead>
          <tbody>
            {t1_table_rows}
          </tbody>
        </table>
      </div>

      <div class="panel chart-panel">
        {dist_chart.to_div(include_js=False)}
      </div>
    </div>

    <div class="panel chart-panel">
      {yearly_chart.to_div(include_js=False)}
    </div>
  </section>

  <section id="topic2" class="tab-pane">
    <div class="panel chart-panel">
      {age_bar_chart.to_div(include_js=False)}
    </div>

    <div class="split-right">
      <div class="panel chart-panel">
        {age_trend_chart.to_div(include_js=False)}
      </div>

      <div class="panel">
        <div class="section-kicker">주제 2 · 세대별 공원 효과 순위</div>
        <div class="hero-stat">{kids['diff']:+.2f}%p</div>
        <p class="hero-desc">
          주말 낮(10–17시) 기준 유아동 동반 가족과 청년층이 봄철 공원 유입을 주도하며, 전 세대에서 공원 보유 동의 증가율이 앞섰습니다.
        </p>

        <table class="clean-table">
          <thead>
            <tr><th>세대</th><th class="num">공원</th><th class="num">미보유</th><th class="num">격차</th></tr>
          </thead>
          <tbody>
            {t2_table_rows}
          </tbody>
        </table>
      </div>
    </div>
  </section>

</main>

<footer>
  <div class="container">
    Seoul Urban Park Living Population Analysis · 424 Administrative Dongs · 25 Autonomous Districts · Object-Oriented Analytics Pipeline
  </div>
</footer>

<script>
  const DETAIL_DATA = {detail_json};
  const RATE_SCALE = [[0.0, "#CBD5E1"], [0.44, "#F8FAFC"], [1.0, "#0F766E"]];
  const PARK_SCALE = [[0.0, "#E5E7EB"], [1.0, "#99F6E4"]];

  let currentGu = 'ALL';
  let currentColorMode = 'rate';
  let origDongTrace = null;
  let origBorderTrace = null;
  let origParkHaloTrace = null;
  let origParkBorderTrace = null;
  let origParkTrace = null;

  function switchTab(tabId, btn) {{
    document.querySelectorAll('.tab-pane, .tab-btn').forEach(el => el.classList.remove('active'));
    const pane = document.getElementById(tabId);
    pane.classList.add('active');
    btn.classList.add('active');
    if (window.Plotly) {{
      pane.querySelectorAll('.plotly-graph-div').forEach(div => Plotly.Plots.resize(div));
    }}
  }}

  function resetToSummary() {{
    document.getElementById('overview-detail').style.display = 'none';
    document.getElementById('overview-summary').style.display = 'block';
    document.querySelectorAll('.choroplethlocation.is-selected').forEach(p => p.classList.remove('is-selected'));
  }}

  function renderInspector(backHtml, bodyHtml) {{
    document.getElementById('overview-summary').style.display = 'none';
    const el = document.getElementById('overview-detail');
    el.innerHTML = backHtml + bodyHtml;
    el.style.display = 'block';
  }}

  function updateMapView() {{
    const mapPlot = document.querySelector('#map-panel .plotly-graph-div');
    if (!mapPlot || !origDongTrace) return;

    const isAll = currentGu === 'ALL';
    const selEl = document.getElementById('gu-select');
    if (selEl.value !== currentGu) selEl.value = currentGu;
    document.getElementById('gu-reset-btn').style.display = isAll ? 'none' : 'inline-flex';

    // 1. 행정동 필터링
    const indices = [];
    origDongTrace.locations.forEach((cd, i) => {{
      const d = DETAIL_DATA.dongs[cd];
      if (isAll || (d && d.gu === currentGu)) indices.push(i);
    }});

    const filtLocs = indices.map(i => origDongTrace.locations[i]);
    const filtCustom = indices.map(i => origDongTrace.customdata[i]);
    const filtRates = indices.map(i => origDongTrace.z[i]);
    const filtParkFlags = filtLocs.map(cd => (DETAIL_DATA.dongs[cd] && DETAIL_DATA.dongs[cd].has_park ? 1 : 0));
    const filtFeatures = origDongTrace.geojson.features.filter(ft => isAll || (DETAIL_DATA.dongs[ft.id] && DETAIL_DATA.dongs[ft.id].gu === currentGu));

    const dongTrace = {{
      type: 'choropleth',
      locationmode: 'geojson-id',
      uid: 'dong-' + currentGu + '-' + currentColorMode,
      geojson: {{ type: 'FeatureCollection', features: filtFeatures }},
      locations: filtLocs,
      z: currentColorMode === 'rate' ? filtRates : filtParkFlags,
      zmin: currentColorMode === 'rate' ? -12 : 0,
      zmid: currentColorMode === 'rate' ? 0 : 0.5,
      zmax: currentColorMode === 'rate' ? 15 : 1,
      colorscale: currentColorMode === 'rate' ? RATE_SCALE : PARK_SCALE,
      showscale: currentColorMode === 'rate',
      colorbar: origDongTrace.colorbar,
      marker: {{ line: {{ width: isAll ? 0.5 : 0.9, color: isAll ? '#E5E7EB' : '#FFFFFF' }} }},
      customdata: filtCustom,
      hovertemplate: origDongTrace.hovertemplate,
      name: '행정동',
      showlegend: false,
    }};

    // 2. 자치구 외곽 경계선 필터링
    const borderTrace = {{
      type: 'scattergeo',
      uid: 'border-' + currentGu,
      mode: 'lines',
      lon: isAll ? origBorderTrace.lon : (DETAIL_DATA.gu_borders[currentGu] || {{ lon: [] }}).lon,
      lat: isAll ? origBorderTrace.lat : (DETAIL_DATA.gu_borders[currentGu] || {{ lat: [] }}).lat,
      line: {{ color: '#6B7280', width: isAll ? 1.1 : 1.4, dash: 'dot' }},
      hoverinfo: 'skip',
      name: '자치구 경계',
      showlegend: true,
    }};

    // 3. 공원 보유 행정동 강조 테두리 필터링 (흰색 외곽선 + 청록색 실선)
    const pkBounds = isAll ? null : (DETAIL_DATA.park_dong_borders[currentGu] || {{ lon: [], lat: [] }});
    const parkHaloTrace = {{
      type: 'scattergeo',
      uid: 'pk-halo-' + currentGu,
      mode: 'lines',
      lon: isAll ? origParkHaloTrace.lon : pkBounds.lon,
      lat: isAll ? origParkHaloTrace.lat : pkBounds.lat,
      line: {{ color: '#FFFFFF', width: isAll ? 3.4 : 4.2 }},
      hoverinfo: 'skip',
      showlegend: false,
    }};
    const parkBorderTrace = {{
      type: 'scattergeo',
      uid: 'pk-border-' + currentGu,
      mode: 'lines',
      lon: isAll ? origParkBorderTrace.lon : pkBounds.lon,
      lat: isAll ? origParkBorderTrace.lat : pkBounds.lat,
      line: {{ color: '#0F766E', width: isAll ? 1.9 : 2.5 }},
      hoverinfo: 'skip',
      name: '공원 보유 동 경계',
      showlegend: true,
    }};

    // 4. 공원 마커 필터링 (선택된 구의 공원만 표시)
    const pIdx = [];
    DETAIL_DATA.parks.forEach((p, i) => {{
      if (isAll || p.dong_gu === currentGu || p.gu === currentGu) pIdx.push(i);
    }});
    const parkTrace = {{
      type: 'scattergeo',
      uid: 'park-' + currentGu,
      mode: 'markers',
      lat: pIdx.map(i => origParkTrace.lat[i]),
      lon: pIdx.map(i => origParkTrace.lon[i]),
      customdata: pIdx.map(i => origParkTrace.customdata[i]),
      marker: {{
        size: pIdx.map(i => origParkTrace.marker.size[i]),
        color: '#111827',
        opacity: 0.85,
        line: {{ color: '#FFFFFF', width: 0.9 }},
      }},
      hovertemplate: origParkTrace.hovertemplate,
      name: '주요 공원',
      showlegend: true,
    }};

    const layoutCopy = {{
      template: mapPlot.layout.template,
      paper_bgcolor: '#FFFFFF',
      plot_bgcolor: '#FFFFFF',
      font: mapPlot.layout.font,
      hoverlabel: mapPlot.layout.hoverlabel,
      legend: mapPlot.layout.legend,
      margin: mapPlot.layout.margin,
      height: mapPlot.layout.height,
      geo: {{
        fitbounds: 'locations',
        visible: false,
        projection: {{ type: 'mercator' }},
        bgcolor: 'rgba(0,0,0,0)',
      }},
      title: {{
        text: `<span style='color:#111827;font-size:16px;font-weight:600;letter-spacing:-0.02em'>${{isAll ? '서울시 424개 행정동 봄철 생활인구 증가율 및 주요 공원 분포' : currentGu + ' 행정동별 봄철 생활인구 증가율 (' + filtLocs.length + '개 동)'}}</span><br><span style='font-size:12.5px;color:#6B7280;font-weight:400'>${{isAll ? '짙은 청록색 테두리 = 공원 보유 동 · 상단에서 자치구를 선택하면 해당 구만 확대됩니다' : '짙은 청록색 실선 테두리가 둘러진 동이 공원 보유 행정동입니다 · 도형 클릭 시 상세 확인'}}</span>`,
        x: 0.01,
        xanchor: 'left',
      }},
    }};

    Plotly.react(mapPlot, [dongTrace, borderTrace, parkHaloTrace, parkBorderTrace, parkTrace], layoutCopy);
  }}

  function selectGu(guName) {{
    currentGu = guName;
    updateMapView();
    if (guName === 'ALL') {{
      resetToSummary();
    }} else {{
      showGuDetail(guName);
    }}
  }}

  function setColorMode(mode, btn) {{
    currentColorMode = mode;
    document.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    updateMapView();
  }}

  function showGuDetail(guName) {{
    const g = DETAIL_DATA.gus[guName];
    if (!g) return;
    const dongRows = g.dongs.map(d =>
      `<tr class='clickable-row' onclick="focusDong('${{d.cd}}')">` +
      `<td>${{d.name}}</td>` +
      `<td class='num'>${{d.has_park ? '<span class="accent">보유</span>' : '미보유'}}</td>` +
      `<td class='num ${{d.rate >= 0 ? "accent" : ""}}'>${{d.rate > 0 ? "+" : ""}}${{d.rate.toFixed(2)}}%</td></tr>`
    ).join('');

    const parksHtml = g.parks.length
      ? g.parks.map(p => `<div class="park-item"><div class="park-item-title">${{p.name}} <span style="font-weight:400;color:var(--text-muted)">(${{p.dong_nm.split(' ').slice(1).join(' ')}})</span></div><div class="park-item-meta">면적 ${{p.area_ha.toLocaleString()}} ha · ${{p.addr}}</div></div>`).join('')
      : '<div style="font-size:12px;color:var(--text-muted);">등록된 주요 도시공원이 없습니다.</div>';

    const backBtn = `<button class="back-btn" onclick="selectGu('ALL')">← 서울 전체로 돌아가기</button>`;
    renderInspector(backBtn, `
      <div class="section-kicker">서울시 자치구 · 행정동 목록</div>
      <div class="detail-header"><h2 class="detail-title">${{g.name}}</h2><span class="status-tag has-park">공원 보유 ${{g.n_park}}/${{g.n_dongs}}동</span></div>
      <table class="clean-table" style="margin-top:10px;"><tbody>
        <tr><td>구 전체 평균 증가율</td><td class="num accent">${{g.mean_rate>0?'+':''}}${{g.mean_rate.toFixed(2)}}%</td></tr>
        <tr><td>공원 보유 동 평균</td><td class="num">${{g.park_rate !== null ? (g.park_rate>0?'+':'')+g.park_rate.toFixed(2)+'%' : '-'}}</td></tr>
        <tr><td>공원 미보유 동 평균</td><td class="num">${{g.none_rate !== null ? (g.none_rate>0?'+':'')+g.none_rate.toFixed(2)+'%' : '-'}}</td></tr>
      </tbody></table>
      <div class="sub-heading">소속 행정동 전체 (${{g.n_dongs}}개 동 · 클릭 시 상세)</div>
      <div class="scroll-table-wrap">
        <table class="clean-table"><thead><tr><th>행정동</th><th class="num">공원</th><th class="num">증가율</th></tr></thead><tbody>${{dongRows}}</tbody></table>
      </div>
      <div class="sub-heading">구 내 주요 공원 (${{g.parks.length}}개소)</div>
      <div>${{parksHtml}}</div>
    `);
  }}

  function focusDong(cd) {{
    const mapPlot = document.querySelector('#map-panel .plotly-graph-div');
    if (mapPlot) {{
      const paths = mapPlot.querySelectorAll('.choroplethlayer .trace.choropleth path.choroplethlocation');
      const locs = mapPlot.data[0].locations || [];
      paths.forEach(p => p.classList.remove('is-selected'));
      const idx = locs.indexOf(cd);
      if (idx !== -1 && paths[idx]) paths[idx].classList.add('is-selected');
    }}
    showDongDetail(cd);
  }}

  function showDongDetail(cd) {{
    const d = DETAIL_DATA.dongs[cd];
    if (!d) return;
    const badge = d.has_park
      ? '<span class="status-tag has-park">공원 보유</span>'
      : '<span class="status-tag">공원 미보유</span>';

    const dayRows = ['주말·공휴일', '평일', '전체'].map(dt => {{
      const st = d.day_stats[dt];
      if (!st) return '';
      const cls = st.rate >= 0 ? 'accent' : '';
      return `<tr><td>${{dt}}</td><td class="num">${{st.jan.toLocaleString()}} → ${{st.may.toLocaleString()}}</td><td class="num ${{cls}}">${{st.rate > 0 ? '+' : ''}}${{st.rate.toFixed(2)}}%</td></tr>`;
    }}).join('');

    const yearCells = ['2023', '2024', '2025', '2026'].map(yr => {{
      const v = d.yearly[yr];
      const txt = v === undefined ? '-' : `${{v > 0 ? '+' : ''}}${{v.toFixed(1)}}%`;
      const col = v >= 0 ? 'var(--accent)' : 'var(--text-body)';
      return `<div class="year-cell"><div class="yr">${{yr}}</div><div class="val" style="color:${{col}}">${{txt}}</div></div>`;
    }}).join('');

    const ageRows = d.ages.map(a => {{
      const w = Math.min(100, Math.abs(a.rate) * 5.5);
      const negCls = a.rate < 0 ? 'neg' : '';
      return `<div class="age-bar-row"><span>${{a.group}}</span><div class="bar-track"><div class="bar-fill ${{negCls}}" style="width:${{w}}%"></div></div><span class="num" style="text-align:right;font-variant-numeric:tabular-nums;color:${{a.rate>=0?'var(--accent)':'var(--text-muted)'}}">${{a.rate>0?'+':''}}${{a.rate.toFixed(1)}}%</span></div>`;
    }}).join('');

    const parksHtml = d.parks.length
      ? d.parks.map(p => `<div class="park-item"><div class="park-item-title">${{p.name}}</div><div class="park-item-meta">면적 ${{p.area_ha.toLocaleString()}} ha · ${{p.addr}}</div>${{p.fclt ? `<div class="park-item-meta" style="margin-top:4px;color:var(--text-body)">${{p.fclt}}</div>` : ''}}</div>`).join('')
      : '<div style="font-size:12px;color:var(--text-muted);margin-top:4px;">이 행정동 경계 내 등록된 주요 도시공원이 없습니다.</div>';

    const backBtn = currentGu === 'ALL'
      ? `<div style="display:flex;gap:6px;margin-bottom:14px;"><button class="back-btn" style="margin:0;" onclick="resetToSummary()">← 서울 전체 요약</button><button class="back-btn" style="margin:0;" onclick="selectGu('${{d.gu}}')">${{d.gu}}만 확대</button></div>`
      : `<button class="back-btn" onclick="showGuDetail('${{d.gu}}')">← ${{d.gu}} 목록으로</button>`;

    renderInspector(backBtn, `
      <div class="section-kicker"><span class="gu-link" onclick="selectGu('${{d.gu}}')">${{d.gu}}</span> · 행정동 상세</div>
      <div class="detail-header"><h2 class="detail-title">${{d.name}}</h2>${{badge}}</div>
      <div class="sub-heading">1월 → 5월 낮 생활인구 변화 (4개년 평균)</div>
      <table class="clean-table">
        <thead><tr><th>구분</th><th class="num">1월 → 5월</th><th class="num">증가율</th></tr></thead>
        <tbody>${{dayRows}}</tbody>
      </table>
      <div class="sub-heading">주말 낮 연도별 증가율 추이</div>
      <div class="year-grid">${{yearCells}}</div>
      <div class="sub-heading">5대 세대별 봄철 증가율 (주말 낮)</div>
      <div>${{ageRows}}</div>
      <div class="sub-heading">소속 주요 공원 정보 (${{d.parks.length}}개소)</div>
      <div>${{parksHtml}}</div>
    `);
  }}

  function showParkDetail(p) {{
    if (!p) return;
    const backBtn = currentGu === 'ALL'
      ? `<div style="display:flex;gap:6px;margin-bottom:14px;"><button class="back-btn" style="margin:0;" onclick="resetToSummary()">← 서울 전체 요약</button><button class="back-btn" style="margin:0;" onclick="selectGu('${{p.dong_gu}}')">${{p.dong_gu}}만 확대</button></div>`
      : `<button class="back-btn" onclick="showGuDetail('${{currentGu}}')">← ${{currentGu}} 목록으로</button>`;

    renderInspector(backBtn, `
      <div class="section-kicker">${{p.gu}} · 주요 도시공원</div>
      <div class="detail-header"><h2 class="detail-title">${{p.name}}</h2><span class="status-tag has-park">${{p.area_ha.toLocaleString()}} ha</span></div>
      <table class="clean-table" style="margin-top:12px;"><tbody>
        <tr><td>위치 행정동</td><td class="num"><span class="gu-link" onclick="showDongDetail('${{p.dong_cd}}')">${{p.dong_nm}}</span></td></tr>
        <tr><td>주소</td><td class="num">${{p.addr || '-'}}</td></tr>
      </tbody></table>
      <div class="sub-heading">주요 보유 시설</div>
      <div class="park-item"><div class="park-item-meta" style="color:var(--text-body);line-height:1.55;">${{p.fclt || '등록된 시설 상세 정보가 없습니다.'}}</div></div>
    `);
  }}

  window.addEventListener('DOMContentLoaded', () => {{
    const mapPlot = document.querySelector('#map-panel .plotly-graph-div');
    if (!mapPlot || !mapPlot.data) return;

    // 초기 전체 트레이스 스냅샷 저장
    origDongTrace = {{ ...mapPlot.data[0] }};
    origBorderTrace = {{ ...mapPlot.data[1] }};
    origParkHaloTrace = {{ ...mapPlot.data[2] }};
    origParkBorderTrace = {{ ...mapPlot.data[3] }};
    origParkTrace = {{ ...mapPlot.data[4], marker: {{ ...mapPlot.data[4].marker }} }};

    const getPaths = () => {{
      const trace = mapPlot.querySelector('.choroplethlayer .trace.choropleth');
      return trace ? trace.querySelectorAll('path.choroplethlocation') : [];
    }};

    mapPlot.on('plotly_hover', (ev) => {{
      const pt = ev.points && ev.points[0];
      if (!pt) return;
      document.querySelectorAll('.choroplethlocation.is-hovered').forEach(p => p.classList.remove('is-hovered'));
      if (pt.curveNumber === 0) {{
        const paths = getPaths();
        if (paths[pt.pointIndex]) paths[pt.pointIndex].classList.add('is-hovered');
      }}
    }});

    mapPlot.on('plotly_unhover', () => {{
      document.querySelectorAll('.choroplethlocation.is-hovered').forEach(p => p.classList.remove('is-hovered'));
    }});

    mapPlot.on('plotly_click', (ev) => {{
      const pt = ev.points && ev.points[0];
      if (!pt) return;
      document.querySelectorAll('.choroplethlocation.is-selected').forEach(p => p.classList.remove('is-selected'));
      if (pt.curveNumber === 0) {{
        const paths = getPaths();
        if (paths[pt.pointIndex]) paths[pt.pointIndex].classList.add('is-selected');
        showDongDetail(pt.location);
      }} else if (pt.curveNumber === 4) {{
        const name = pt.customdata && pt.customdata[0];
        const found = DETAIL_DATA.parks.find(x => x.name === name);
        if (found) showParkDetail(found);
      }}
    }});

    const initGu = new URLSearchParams(window.location.search).get('gu');
    if (initGu && DETAIL_DATA.gus[initGu]) selectGu(initGu);
  }});
</script>
</body>
</html>
"""

    def save(self, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(self.build_html(), encoding="utf-8")
        print(f"[완료] 통합 대시보드 웹페이지 생성: {out_path} ({out_path.stat().st_size:,} bytes)")
        return out_path


def build_unified_dashboard() -> None:
    names = DongNameLookup()
    t1 = SeasonalChangeAnalyzer(PROJECT_ROOT / "data" / "processed" / "daytime_weekend_pop.csv", names)
    t2 = AgeGroupAnalyzer(PROJECT_ROOT / "data" / "processed" / "daytime_age_pop.csv", names)
    charts = {
        "map": SeoulParkMapChart(t1, names),
        "dist": RateDistributionChart(t1),
        "yearly": YearlyTrendChart(t1),
        "age_bar": AgeRateBarChart(t2),
        "age_trend": AgeYearlyTrendChart(t2),
    }
    DashboardBuilder(t1, t2, names, ParkMapSource(PARK_MAP_CSV_PATH), charts).save(PROJECT_ROOT / "docs" / "index.html")


if __name__ == "__main__":
    build_unified_dashboard()
