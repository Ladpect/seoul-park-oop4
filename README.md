# 🌲 서울시 공원 유무에 따른 생활인구 계절 변동 및 세대별 반응도 빅데이터 분석

> **객체지향프로그래밍(OOP) 팀 프로젝트**  
> 서울시 주요 공원 현황과 4개년(2023~2026) 행정동별 생활인구 빅데이터를 결합하여, 공원 보유 여부가 계절별·세대별 인구 변동에 미치는 영향을 다각도로 검증하는 객체지향 통계 분석 및 대시보드 웹 플랫폼입니다.

---

## 🔗 대시보드 바로가기

* **배포 URL:** [GitHub Pages 대시보드 바로가기](https://ladpect.github.io/seoul-park-oop4/) *(저장소 Settings > Pages에서 `docs` 폴더를 배포 소스로 지정)*
* **로컬 실행:** `docs/index.html` 파일을 웹 브라우저에서 열면 즉시 대시보드를 체험할 수 있습니다.

---

## 🎯 연구 주제 및 핵심 분석 결과

### 📊 [주제 1] 공원 유무에 따른 사계절(1월 vs 5월) 생활인구 변동 비교
* **가설:** 혹한기(1월) 대비 나들이철(5월) 주말 낮 시간대(10~17시) 생활인구의 증가폭은 공원을 보유한 행정동이 비보유 행정동보다 유의미하게 클 것이다.
* **통계적 검정 결과 (4개년 424개 행정동):**
  * **공원 보유 행정동 (102개):** 평균 **+0.18%**
  * **공원 미보유 행정동 (322개):** 평균 **-2.45%**
  * **계절 증가율 격차:** **+2.63%p** ($t = 2.97$, $p = 0.0036$, Mann-Whitney U $p = 0.0060$)
  * **연도별 재현성:** 2023년(+1.62%p), 2024년(+2.50%p), 2025년(+3.29%p), 2026년(+3.09%p) **4개년 매년 공원 동의 증가율이 일관되게 우세 ($p < 0.05$)**.

### 👥 [주제 2] 세대/연령대별 공원 반응도 분석
* **가설:** 봄철 공원 보유 행정동으로의 인구 유입 증가는 특정 연령층(영유아 가족, 청년층, 고령층)이 주도할 것이다.
* **통계적 검정 결과 (4개년 세대별 분석):**
  1. **유아동 (0~9세):** 공원 보유 동(+3.56%) vs 미보유 동(-0.56%) → **격차 +4.12%p ($p = 0.0107$)**  
     * 전 세대 중 가장 극적인 격차를 기록하며, **봄철 공원의 1순위 유인 계층은 영유아·어린이 동반 가족**임을 입증.
  2. **청년층 (20~39세):** 공원 보유 동(+1.85%) vs 미보유 동(-0.97%) → **격차 +2.82%p ($p = 0.0148$)**  
     * 주말 피크닉 및 야외 데이트 인구의 공원 선호 확인.
  3. **고령층 (60세 이상):** 공원 보유 동(-3.33%) vs 미보유 동(-5.50%) → **격차 +2.16%p ($p = 0.0018$)**  
     * 4개년 모든 해에서 $p < 0.04$로 가장 일관된 산책 및 건강 활동 보존 효과 확인.

---

## 🏛️ 객체지향(OOP) 소프트웨어 설계

본 프로젝트는 데이터 수집부터 통계 검정, 인터랙티브 시각화까지 OOP 원칙(추상화, 상속, 다형성, 캡슐화, 조합)에 기반하여 설계되었습니다.

### 📐 클래스 구조도 (UML Class Diagram)

```
                       ┌───────────────────────┐
                       │     <<abstract>>      │
                       │       CsvSource       │
                       ├───────────────────────┤
                       │ - fpath: Path         │
                       ├───────────────────────┤
                       │ + encoding (property) │
                       │ + normalize_dong_cd() │
                       │ + load() {abstract}   │
                       └───────────▲───────────┘
                                   │ 상속 (Inheritance)
          ┌────────────────────────┼────────────────────────┐
┌─────────┴────────────┐ ┌─────────┴────────────┐ ┌─────────┴────────────┐
│   LivingPopSource    │ │  AgeLivingPopSource  │ │    ParkMapSource     │
│ (4열 인구 데이터 로드│ │(32열 성별/연령 집계) │ │(공원 맵핑 및 면적보정│
└──────────────────────┘ └──────────────────────┘ └────────────▲─────────┘
                                                               │ 주입
                                                   ┌───────────┴─────────┐
                                                   │     ParkMapper      │
                                                   ├─────────────────────┤
                                                   │ + restrict_to()     │
                                                   │ + has_park()        │
                                                   └─────────────────────┘

                       ┌───────────────────────┐
                       │     <<abstract>>      │
                       │         Chart         │
                       ├───────────────────────┤
                       │ - analyzer            │
                       ├───────────────────────┤
                       │ + build() {abstract}  │
                       │ + save(out_dir)       │
                       │ + to_div(include_js)  │
                       └───────────▲───────────┘
                                   │ 상속 (Polymorphism)
          ┌────────────────────────┴────────────────────────┐
┌─────────┴───────────────────────────┐ ┌───────────────────┴─────────────────┐
│              주제 1 차트             │ │                  주제 2 차트               │
├─────────────────────────────────────┤ ├─────────────────────────────────────┤
│ • RateDistributionChart (분포 박스) │ │ • AgeRateBarChart (세대별 비교 막대)│
│ • DifferenceForestChart (신뢰구간)  │ │ • AgeForestChart (세대별 포레스트)  │
│ • YearlyTrendChart (4개년 추이선)   │ │ • AgeYearlyTrendChart (세대별 추이) │
└─────────────────────────────────────┘ └─────────────────────────────────────┘
```

### 💡 핵심 OOP 설계 패턴 적용
* **추상화(Abstraction):** `CsvSource`와 `Chart`를 추상 기본 클래스로 정의하여 공통 속성(인코딩 감지, 파일 저장, SVG 추출)을 규격화.
* **상속(Inheritance):** `AgeLivingPopSource`가 `CsvSource`를 상속받고, 6개의 시각화 클래스가 `Chart`를 상속받아 다형적 동작 구현.
* **캡슐화(Encapsulation):** 공휴일 판별 및 설 연휴 제외 로직은 `HolidayCalendar`, 행정동 불일치 공원 필터링은 `ParkMapper` 내부로 캡슐화.
* **조합(Composition):** `DaytimePopPreprocessor`와 `AgePopPreprocessor`가 Config, Calendar, Mapper 객체들을 주입받아 전처리 파이프라인 수행.

---

## 📂 프로젝트 구조 및 파일별 상세 설명

프로젝트는 데이터 수명주기(원천 데이터 수집 ➔ OOP 전처리 파이프라인 ➔ 통계 분석 및 Plotly 시각화 ➔ GitHub Pages 웹 대시보드 배포)에 맞추어 체계적으로 모듈화되어 있습니다.

```
OOP/
├── data/                                 # 데이터 디렉토리
│   ├── README.md                         # 데이터셋(원천/정제) 상세 명세서
│   ├── raw/                              # 원천 데이터 (공원 맵핑, GeoJSON, 월별 생활인구)
│   └── processed/                        # 전처리 및 정제 완료 통계 분석용 데이터셋
├── preprocessing/                        # 객체지향(OOP) 데이터 정제 및 집계 파이프라인
│   ├── newdata.py                        # [주제 1] 주말 낮 생활인구 집계 모듈
│   └── extract_age_data.py               # [주제 2] 5대 세대별 생활인구 집계 모듈
├── analysis/                             # 통계 검정 및 인터랙티브 Plotly 시각화 모듈
│   ├── topic1_visualize.py               # [주제 1] 공원 유무별 계절 변동 검정 및 차트
│   ├── topic2_visualize.py               # [주제 2] 세대별 공원 반응도 검정 및 차트
│   └── build_dashboard.py                # 통합 웹 대시보드 빌더
├── docs/                                 # GitHub Pages 배포 디렉토리
│   ├── index.html                        # 2개 탭 통합 대시보드 메인 웹 애플리케이션
│   ├── topic1/                           # 주제 1 개별 차트 HTML 및 통계표 CSV
│   └── topic2/                           # 주제 2 개별 차트 HTML 및 통계표 CSV
├── .gitignore                            # 대용량 원천 데이터(LPD/) 및 로컬 문서 제외
└── README.md                             # 프로젝트 종합 안내 기술 문서
```

### 1. `data/` (데이터셋 디렉토리)
| 파일 / 폴더명 | 포함 내용 (What is inside) | 역할 및 기능 (Role & Function) |
| :--- | :--- | :--- |
| `data/README.md` | 데이터 디렉토리 내 원천/정제 데이터셋의 상세 스키마 및 출처 정리 | `data/` 디렉토리 방문 시 데이터셋 명세를 즉시 확인할 수 있도록 안내 |
| `data/raw/park_dong_map.csv` | 서울시 102개 주요 공원의 번호, 공원명, 자치구, 8자리 행정동코드, 면적($m^2$), 좌표, 시설물, 주소 정보 | 서울시 424개 행정동 중 공원 보유 동(102개)과 미보유 동(322개)을 식별하고 독립변수(`has_park`)를 정의하는 기준 데이터셋 |
| `data/raw/HangJeongDong_ver20260701.geojson` | 대한민국 행정동 지리 경계 다각형 좌표 및 행정동 코드·이름 매핑 GeoJSON ([출처: admdongkor](https://github.com/vuski/admdongkor)) | 8자리 행정동 코드를 사람이 직관적으로 이해할 수 있는 동 이름(예: '종로구 청운효자동', '마포구 상암동')으로 변환하여 차트 툴팁에 표시 |
| `data/raw/LPD/` *(git 제외)* | 4개년(2023~2026) 1월·5월 서울시 생활인구 월별 원천 CSV 파일 8개 (총 수천만 건의 시간대별 행정동 인구 원시 데이터) | 전처리 파이프라인의 입력 원천 데이터 (대용량으로 인해 `.gitignore`로 관리되며 로컬에 보관) |
| `data/processed/daytime_weekend_pop.csv` | 424개 행정동 × 4개년 × 2개 계절(1월·5월) × 주말/평일 낮 시간대(10~17시) 평균 생활인구 집계 (6,784행) | **[주제 1]** 혹한기 대비 봄철 생활인구 증가율 계산, 독립표본 t-검정, Mann-Whitney U 검정 수행의 입력 데이터 |
| `data/processed/daytime_age_pop.csv` | 424개 행정동 × 4개년 × 2개 계절 × 5개 세대(유아동, 청소년, 청년, 중장년, 노년)별 주말 낮 생활인구 집계 (40,704행) | **[주제 2]** 5대 세대 그룹별 봄철 생활인구 증가율 및 공원 반응도 격차 통계 검정의 입력 데이터 |

### 2. `preprocessing/` (데이터 정제 및 전처리 파이프라인)
| 파일명 | 포함 내용 (What is inside) | 역할 및 기능 (Role & Function) |
| :--- | :--- | :--- |
| `preprocessing/newdata.py` | `CsvSource`(추상 클래스), `LivingPopSource`, `ParkMapSource`, `HolidayCalendar`, `ParkMapper`, `DaytimePopPreprocessor` 클래스 | 대이동 왜곡을 일으키는 설 연휴(2023/2025)를 제외하고, 주말/공휴일 낮 시간대 평균 인구를 집계하여 `data/processed/daytime_weekend_pop.csv` 생성 |
| `preprocessing/extract_age_data.py` | `newdata.py`의 기반 클래스를 상속받은 `AgeLivingPopSource`, `AgePopPreprocessor` 클래스 및 5대 세대 정의 | 원천 생활인구 32개 열을 파싱하여 5개 생애주기 세대(영유아, 청소년, 청년, 중장년, 고령층)별 인구로 분할 집계하여 `data/processed/daytime_age_pop.csv` 생성 |

### 3. `analysis/` (통계 분석 및 시각화 모듈)
| 파일명 | 포함 내용 (What is inside) | 역할 및 기능 (Role & Function) |
| :--- | :--- | :--- |
| `analysis/topic1_visualize.py` | `SeasonalChangeAnalyzer`, `DongNameLookup`, `Theme`, `Chart`(추상 클래스), `RateDistributionChart`, `DifferenceForestChart`, `YearlyTrendChart` 클래스 | **[주제 1]** 계절 증가율 계산, 독립표본 t-검정 및 U-검정 수행, 박스플롯·포레스트플롯·4개년 추이선 인터랙티브 Plotly 차트 생성 및 `docs/topic1/`에 저장 |
| `analysis/topic2_visualize.py` | `AgeGroupAnalyzer`, `AgeRateBarChart`, `AgeForestChart`, `AgeYearlyTrendChart` 클래스 | **[주제 2]** 세대별 증가율 및 격차 통계 검정 수행, 5개 세대 비교 막대그래프·신뢰구간·연도별 추이선 인터랙티브 Plotly 차트 생성 및 `docs/topic2/`에 저장 |
| `analysis/build_dashboard.py` | 주제 1과 주제 2의 차트 컴포넌트 호출, KPI 요약 카드 정의, 반응형 레이아웃 구성, 탭 전환 스크립트 빌드 함수 | 6개 인터랙티브 차트와 주요 통계 지표를 결합한 GitHub Pages 배포용 단일 웹 플랫폼(`docs/index.html`) 자동 생성 |

### 4. `docs/` (GitHub Pages 배포 웹 디렉토리)
| 파일 / 폴더명 | 포함 내용 (What is inside) | 역할 및 기능 (Role & Function) |
| :--- | :--- | :--- |
| `docs/index.html` | Pretendard 웹폰트, KPI 카드 6개, Plotly 인터랙티브 그래프 6개, 반응형 탭 메뉴가 내장된 단일 HTML 웹 대시보드 (225KB) | 사용자가 브라우저에서 2개 연구 주제를 탭으로 넘나들며 확대/축소, 툴팁 확인, SVG 다운로드를 할 수 있는 최종 웹 플랫폼 |
| `docs/topic1/` | 주제 1 개별 차트 HTML 3개(`distribution`, `forest`, `yearly`), 통계 요약표(`stats_summary.csv`), `index.html` | 주제 1 단독 페이지 및 통계 검정 결과 수치 파일 제공 |
| `docs/topic2/` | 주제 2 개별 차트 HTML 3개(`age_bar`, `age_forest`, `age_trend`), 통계 요약표(`stats_summary.csv`), `index.html` | 주제 2 단독 페이지 및 세대별 통계 검정 결과 수치 파일 제공 |

### 5. 기타 설정 파일
| 파일명 | 포함 내용 (What is inside) | 역할 및 기능 (Role & Function) |
| :--- | :--- | :--- |
| `.gitignore` | `data/raw/LPD/`, `*.docx`, `__pycache__/` 등 제외 규칙 | 대용량 원천 빅데이터와 개인 보고서 초안이 Git 원격 저장소에 커밋되지 않도록 차단 |
| `README.md` | 프로젝트 개요, 연구 가설 및 결과, OOP 아키텍처 다이어그램, 파일별 상세 설명, 데이터 출처, 실행 가이드 | 프로젝트의 전반적인 기술 내역과 통계적 결론을 안내하는 공식 문서 |

---

## 📊 사용 데이터셋 및 출처 (Data Sources)

1. **메인 데이터셋 (서울시 주요 공원 현황):** 서울 열린데이터 광장 ([data.seoul.go.kr](https://data.seoul.go.kr/))
2. **추가 데이터셋 1 (서울시 행정동별 생활인구 수):** 서울 열린데이터 광장 (2023~2026 4개년 월별 집계)
3. **추가 데이터셋 2 (대한민국 행정동 경계 GeoJSON):** [vuski/admdongkor](https://github.com/vuski/admdongkor) (통계청 행정구역 경계 기반 오픈소스 GeoJSON)

---

## 🛠️ 실행 방법 (How to Run)

### 1. 환경 설정
Python 3.10 이상 권장
```bash
pip install pandas numpy scipy plotly
```

### 2. 데이터 전처리 실행
```bash
# 주제 1 데이터 가공 (data/processed/daytime_weekend_pop.csv 생성)
python preprocessing/newdata.py

# 주제 2 연령별 데이터 가공 (data/processed/daytime_age_pop.csv 생성)
python preprocessing/extract_age_data.py
```

### 3. 시각화 및 통합 대시보드 빌드
```bash
# 주제 1 분석 & 차트 생성
python analysis/topic1_visualize.py

# 주제 2 분석 & 차트 생성
python analysis/topic2_visualize.py

# 통합 웹 대시보드 빌드 (docs/index.html 생성)
python analysis/build_dashboard.py
```

---

## 👥 팀원 정보 및 역할 분담

* **팀장:** 정윤원 (2025403023 / Ladpect)
* **팀원:** 어승경 (minmul07), 김민재 (CanelE452), 박태준 (parktj0807), 송은빈 (lullasia)
