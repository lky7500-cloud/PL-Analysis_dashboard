# 배포 가이드

## 프로젝트 구조

```
PL Analysis_dashboard/
├── app.py                  # Streamlit 대시보드 (배포 대상, 로컬 엑셀 데이터 사용)
├── requirements.txt        # app.py 실행에 필요한 의존성
├── data/                   # 원본 엑셀 데이터 (6개 테이블)
├── charts/                 # BigQuery 기반 독립 분석 스크립트 (07~09)
│   └── output/
├── README.md
└── DEPLOY.md
```

## 왜 이런 구조인가

- **`app.py`는 로컬 엑셀(`data/`)만 읽고, BigQuery를 호출하지 않는다.** Streamlit Community Cloud에는 이 PC의 GCP 인증 정보(Application Default Credentials)가 없기 때문에, 배포 앱이 BigQuery에 의존하면 클라우드에서 바로 인증 오류가 난다. 그래서 대시보드 자체는 항상 로컬 데이터로 동작하도록 분리했다.
- **`charts/07~09`는 BigQuery를 직접 조회하는 별도 스크립트로, 의도적으로 `app.py`와 분리했다.** 필요할 때 로컬 PC에서 `python charts/0X_....py`로 실행해 `fig.show()`로 확인하는 용도이며, Streamlit Cloud 배포 대상이 아니다. 따라서 `google-cloud-bigquery`, `db-dtypes` 같은 패키지는 `requirements.txt`에 넣지 않았다(넣으면 배포 앱에서 불필요하게 무거워지고, 인증 실패 위험만 늘어난다).
- **`requirements.txt`에는 `app.py`가 실제로 import하는 패키지만 최소한으로 나열한다.** 새 차트 기능을 추가할 때 `plotly.express.scatter(..., trendline="ols")`처럼 숨은 의존성(`statsmodels`)이 생기면, 로컬에서는 이미 설치돼 있어 문제가 안 보이다가 배포 후에야 `ModuleNotFoundError`로 드러난다. 그래서 새 import를 추가할 때마다 requirements.txt도 같이 갱신해야 한다.
- **`.claude/`, `.agents/`는 `.gitignore`로 제외했다.** Claude Code 세션의 로컬 도구 상태이며 프로젝트 산출물이 아니기 때문이다.

## Streamlit Cloud 배포 절차

1. GitHub 저장소(`lky7500-cloud/PL-Analysis_dashboard`, `main` 브랜치)에 push하면 Streamlit Cloud가 변경을 감지해 자동으로 재빌드·재배포한다.
2. 자동 반영까지 보통 몇 분 걸리며, 즉시 반영하고 싶으면 [share.streamlit.io](https://share.streamlit.io) → 해당 앱 → 우측 상단 메뉴(⋮) → **Reboot app**.
3. 배포 전에는 항상 로컬에서 `streamlit run app.py`로 먼저 확인한다 (특히 사이드바 필터를 바꿔가며 차트가 다시 그려지는지).

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `ModuleNotFoundError: No module named 'plotly'` (또는 다른 패키지) | `requirements.txt`에 해당 패키지가 없음 | `requirements.txt`에 추가 후 커밋·push (자동 재배포) |
| `trendline="ols"` 사용 시 로컬은 되는데 배포에서만 실패 | `statsmodels`가 `requirements.txt`에 없음 | `statsmodels`를 `requirements.txt`에 추가 |
| push했는데 배포 앱이 그대로임 | 자동 재배포가 아직 진행 중이거나 지연됨 | 몇 분 대기 후 새로고침, 급하면 Streamlit Cloud에서 Reboot app |
| 대시보드 첫 로딩이 느림 | 큰 엑셀 파일(특히 `05_매출상세.xlsx`)을 매번 새로 읽음 | `app.py`의 `load_all_excel_data()`는 이미 `@st.cache_data`로 캐싱되어 있어 같은 세션 내 재실행부터는 빠름 (완전히 새 프로세스에서만 최초 1회 느림) |
| `git status`에 원치 않는 `.claude/`, `.agents/`, `__pycache__/` 표시 | `.gitignore`에 없거나 오래된 캐시 | `.gitignore`에 항목이 있는지 확인, 이미 추적 중이면 `git rm -r --cached`로 제거 |
| BigQuery 스크립트(`charts/07~09`)가 로컬에서 인증 오류 | GCP Application Default Credentials 미설정 | `GOOGLE_APPLICATION_CREDENTIALS` 환경변수 설정 또는 `gcloud auth application-default login` 실행 |
