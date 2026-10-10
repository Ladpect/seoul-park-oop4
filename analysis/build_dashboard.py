"""
[통합 대시보드 빌더] 2개 연구 주제의 인터랙티브 차트 및 통계 지표를 단일 웹 플랫폼으로 통합

1. 파일 내용 (What is inside):
   - build_unified_dashboard(): 주제 1과 주제 2의 분석 엔진을 호출하고 6개 차트 컴포넌트를 일괄 조립.
   - 통계 지표 카드(KPI): 424개 행정동, 봄철 증가율 격차 +2.63%p, 4개년 일관성, 유아동 격차 +4.12%p 등 핵심 지표 템플릿.
   - 반응형 디자인: Pretendard 폰트, 다크 헤더, 탭 네비게이션, 플롯 반응형 카드 레이아웃.
   - 탭 전환 JS: 주제 1(계절 변동)과 주제 2(세대별 반응도) 간 즉시 전환 인터랙션.

2. 파일 역할 (Role & Function):
   - 두 가지 연구 주제의 시각화 결과물을 결합하여 GitHub Pages에 즉시 배포 가능한 최종 단일 페이지 웹사이트(`docs/index.html`)를 자동 생성합니다.

3. 입출력 (I/O):
   - 입력: data/processed/daytime_weekend_pop.csv, data/processed/daytime_age_pop.csv
           data/raw/HangJeongDong_ver20260701.geojson
   - 출력: docs/index.html (224KB 정적 웹 애플리케이션)
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from topic1_visualize import (
    SeasonalChangeAnalyzer, DongNameLookup,
    RateDistributionChart, DifferenceForestChart, YearlyTrendChart
)
from topic2_visualize import (
    AgeGroupAnalyzer,
    AgeRateBarChart, AgeForestChart, AgeYearlyTrendChart
)

def build_unified_dashboard():
    docs_dir = PROJECT_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    names = DongNameLookup(PROJECT_ROOT / "data" / "raw" / "HangJeongDong_ver20260701.geojson")
    
    # 주제 1 차트 생성
    t1_analyzer = SeasonalChangeAnalyzer(PROJECT_ROOT / "data" / "processed" / "daytime_weekend_pop.csv", names)
    t1_charts = [
        RateDistributionChart(t1_analyzer),
        DifferenceForestChart(t1_analyzer),
        YearlyTrendChart(t1_analyzer)
    ]
    
    # 주제 2 차트 생성
    t2_analyzer = AgeGroupAnalyzer(PROJECT_ROOT / "data" / "processed" / "daytime_age_pop.csv", names)
    t2_charts = [
        AgeRateBarChart(t2_analyzer),
        AgeForestChart(t2_analyzer),
        AgeYearlyTrendChart(t2_analyzer)
    ]
    
    # HTML 카드 블록 생성 (첫 번째 차트만 CDN JS 포함, 이후는 div만 삽입)
    t1_cards = "\n".join(
        f'<div class="chart-card"><div class="chart-body">{c.to_div(include_js=(i == 0))}</div></div>'
        for i, c in enumerate(t1_charts)
    )
    t2_cards = "\n".join(
        f'<div class="chart-card"><div class="chart-body">{c.to_div(include_js=False)}</div></div>'
        for i, c in enumerate(t2_charts)
    )

    html_content = f"""<!--
  =============================================================================
  서울시 공원과 생활인구 빅데이터 통계 분석 통합 대시보드 (GitHub Pages 배포 웹)
  - 내용: [주제 1] 공원 유무별 계절 변동(1월 vs 5월) + [주제 2] 세대별 공원 반응도 분석
  - 역할: 6개 인터랙티브 Plotly 차트, KPI 통계 지표, 반응형 탭 전환을 제공하는 단일 페이지 웹 대시보드
  - 소스 생성: analysis/build_dashboard.py
  =============================================================================
-->
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="서울시 공원 유무에 따른 계절(1월 vs 5월) 생활인구 변동 및 세대별 공원 반응도 빅데이터 통계 분석 대시보드">
  <title>서울시 공원과 생활인구 통계 분석 대시보드</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
  <style>
    :root {{
      --primary: #2a9d8f;
      --secondary: #e76f51;
      --dark: #1f2937;
      --gray-bg: #f8fafc;
      --card-bg: #ffffff;
      --border: #e2e8f0;
      --font-family: Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      background-color: var(--gray-bg);
      font-family: var(--font-family);
      color: var(--dark);
      line-height: 1.6;
    }}
    header {{
      background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
      color: #ffffff;
      padding: 48px 32px 36px;
      border-bottom: 1px solid #334155;
    }}
    .header-container {{
      max-width: 1200px;
      margin: 0 auto;
    }}
    .badge {{
      display: inline-block;
      background: rgba(42, 157, 143, 0.2);
      color: #48cae4;
      border: 1px solid rgba(72, 202, 228, 0.3);
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 12px;
    }}
    h1 {{
      font-size: 30px;
      font-weight: 700;
      margin: 0 0 10px;
      letter-spacing: -0.5px;
    }}
    header p {{
      font-size: 15px;
      color: #94a3b8;
      margin: 0;
      max-width: 800px;
    }}
    
    /* 탭 네비게이션 */
    .nav-tabs {{
      background: #ffffff;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }}
    .nav-container {{
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      gap: 12px;
      padding: 0 32px;
    }}
    .tab-btn {{
      padding: 18px 24px;
      font-size: 16px;
      font-weight: 600;
      color: #64748b;
      background: transparent;
      border: none;
      border-bottom: 3px solid transparent;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s ease;
      font-family: inherit;
    }}
    .tab-btn:hover {{
      color: var(--primary);
    }}
    .tab-btn.active {{
      color: var(--primary);
      border-bottom-color: var(--primary);
    }}
    
    /* 메인 컨테이너 */
    main {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px;
    }}
    
    /* KPI 통계 카드 */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}
    .kpi-card {{
      background: var(--card-bg);
      border-radius: 14px;
      padding: 20px 24px;
      border: 1px solid var(--border);
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}
    .kpi-title {{
      font-size: 13px;
      font-weight: 600;
      color: #64748b;
      margin-bottom: 6px;
    }}
    .kpi-value {{
      font-size: 26px;
      font-weight: 700;
      color: #0f172a;
    }}
    .kpi-sub {{
      font-size: 13px;
      color: #94a3b8;
      margin-top: 4px;
    }}
    .highlight-green {{ color: #10b981; }}
    .highlight-teal {{ color: #0d9488; }}
    
    /* 차트 카드 */
    .chart-card {{
      background: var(--card-bg);
      border-radius: 16px;
      border: 1px solid var(--border);
      box-shadow: 0 2px 8px rgba(0,0,0,0.04);
      margin-bottom: 28px;
      overflow: hidden;
      transition: box-shadow 0.2s ease;
    }}
    .chart-card:hover {{
      box-shadow: 0 4px 16px rgba(0,0,0,0.07);
    }}
    .chart-body {{
      padding: 12px;
    }}
    
    .tab-pane {{
      display: none;
    }}
    .tab-pane.active {{
      display: block;
      animation: fadeIn 0.3s ease;
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    
    footer {{
      text-align: center;
      padding: 40px 20px;
      color: #94a3b8;
      font-size: 14px;
      border-top: 1px solid var(--border);
      background: #ffffff;
      margin-top: 40px;
    }}
  </style>
</head>
<body>

<header>
  <div class="header-container">
    <div class="badge">객체지향프로그래밍 팀 프로젝트</div>
    <h1>서울시 공원과 생활인구 빅데이터 통계 분석 대시보드</h1>
    <p>서울시 주요 공원 현황과 4개년(2023~2026) 행정동별 생활인구 데이터를 결합하여, 공원 보유 여부가 계절별·세대별 인구 변동에 미치는 영향을 다각도로 검증합니다.</p>
  </div>
</header>

<nav class="nav-tabs">
  <div class="nav-container">
    <button class="tab-btn active" onclick="switchTab('topic1')">
      📊 주제 1: 공원 유무별 생활인구 변동
    </button>
    <button class="tab-btn" onclick="switchTab('topic2')">
      👥 주제 2: 세대별 공원 반응도 분석
    </button>
  </div>
</nav>

<main>
  <!-- 탭 1 컨텐츠 -->
  <div id="topic1" class="tab-pane active">
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-title">분석 대상 행정동</div>
        <div class="kpi-value">424개 동</div>
        <div class="kpi-sub">공원 보유 102개 동 · 미보유 322개 동</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">주말 낮 봄철 증가율 격차</div>
        <div class="kpi-value highlight-teal">+2.63%p</div>
        <div class="kpi-sub">공원 +0.18% vs 미보유 -2.45% (p = 0.003)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">연도별 재현성</div>
        <div class="kpi-value highlight-green">4 / 4개년 일관</div>
        <div class="kpi-sub">2023~2026년 매년 공원 동 우세 확인</div>
      </div>
    </div>
    {t1_cards}
  </div>

  <!-- 탭 2 컨텐츠 -->
  <div id="topic2" class="tab-pane">
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-title">유아동(0~9세) 봄철 유입 격차</div>
        <div class="kpi-value highlight-teal">+4.12%p</div>
        <div class="kpi-sub">전 세대 중 최대 증가폭 (p = 0.0107)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">청년층(20~39세) 나들이 효과</div>
        <div class="kpi-value highlight-green">+2.82%p</div>
        <div class="kpi-sub">공원 +1.85% vs 미보유 -0.97% (p = 0.0148)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">고령층(60세+) 산책 활동</div>
        <div class="kpi-value" style="color: #457b9d;">+2.16%p</div>
        <div class="kpi-sub">4개년 모두 통계적 초유의 (p = 0.0018)</div>
      </div>
    </div>
    {t2_cards}
  </div>
</main>

<footer>
  <p>OOP Project Dashboard · 서울시 주요 공원 현황 & 행정동단위 생활인구 데이터셋 · 우측 상단 카메라 아이콘 클릭 시 SVG 벡터 이미지 다운로드 가능</p>
</footer>

<script>
  function switchTab(tabId) {{
    document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    
    document.getElementById(tabId).classList.add('active');
    event.currentTarget.classList.add('active');
    
    // 차트 크기 재조정 트리거 (Plotly 탭 전환 대응)
    window.dispatchEvent(new Event('resize'));
  }}
</script>
</body>
</html>
"""
    output_path = docs_dir / "index.html"
    output_path.write_text(html_content, encoding="utf-8")
    print(f"[완료] 통합 대시보드 웹페이지 생성: {output_path}")

if __name__ == "__main__":
    build_unified_dashboard()
