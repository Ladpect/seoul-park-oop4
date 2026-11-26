# 📊 데이터셋 안내 (Data Catalog)

본 디렉토리는 서울시 공원 유무에 따른 생활인구 계절 변동 및 세대별 반응도 분석에 사용되는 데이터셋을 관리합니다.

---

## 1. 📁 `data/raw/` (원천 데이터)

| 파일 / 폴더 | 파일 내용 (What is inside) | 역할 및 기능 (Role & Function) |
| :--- | :--- | :--- |
| **`park_dong_map.csv`** | 서울시 127개 주요 공원 정보 (일련번호, 공원명, 자치구, 8자리 행정동 코드, 면적, 좌표, 주요시설, 주소) | 서울시 424개 행정동 중 공원 보유 행정동(107개, `has_park=True`)과 미보유(317개) 식별 및 지도 마커 표시 기준 테이블. [매핑 검토 결과](park_mapping_audit.md) |
| **`HangJeongDong_ver20260701.geojson`** | 대한민국 행정동 지리 경계 다각형 좌표 및 행정동 코드(8자리)·명칭 맵핑 GeoJSON ([vuski/admdongkor](https://github.com/vuski/admdongkor)) | 서울 전용 경량 GeoJSON(`seoul_dongs.geojson`) 추출의 원천 지리 데이터 |
| **`LPD/`** *(로컬 보관)* | 서울시 생활인구 월별 원천 CSV 파일 (2022.07~2026.07 총 49개 보관, 분석에는 4개년 1·5월 8개 파일 사용) | 전처리 파이프라인(`preprocessing/newdata.py`, `extract_age_data.py`)의 원천 입력 빅데이터 (대용량으로 Git 추적 제외) |

---

## 2. 📁 `data/processed/` (정제 완료 데이터셋)

| 파일명 | 파일 내용 (What is inside) | 역할 및 기능 (Role & Function) |
| :--- | :--- | :--- |
| **`seoul_dongs.geojson`** | 서울시 424개 행정동 경량 경계 폴리곤 및 개편 동 코드 통합 매핑 (420KB) | 서울 지도 시각화(`SeoulParkMapChart`) 및 빠른 행정동 이름 조회(`DongNameLookup`) |
| **`daytime_weekend_pop.csv`** | 424개 행정동 × 4개년 × 2개 계절(1월·5월) × 주말/평일 낮 시간대(10~17시) 평균 생활인구 및 공원 유무 집계 (6,784행) | **[주제 1]** 혹한기(1월) 대비 나들이철(5월)의 생활인구 계절 변동률 및 공원 유무별 격차 비교 입력 데이터 |
| **`daytime_age_pop.csv`** | 424개 행정동 × 4개년 × 2개 계절 × 5개 세대 그룹(유아동, 청소년, 청년, 중장년, 노년)별 낮 생활인구 집계 (40,704행) | **[주제 2]** 주말·공휴일 낮 기준 세대별 봄철 공원 반응도 분석 및 통계 검정의 입력 데이터 |
