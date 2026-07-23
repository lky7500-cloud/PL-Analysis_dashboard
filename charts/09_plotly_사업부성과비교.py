"""
사업부별 성과 비교 (OLED vs 제약)
- BigQuery accounting 데이터셋(매출상세/GL원장/제품마스터/계정과목마스터/예산)을 직접 읽어
  사업부별 영업이익률과 예산달성률을 전체 기간 기준으로 재계산한다.
- 왼쪽 패널: 사업부별 영업이익률 평균, 오른쪽 패널: 사업부별 예산달성률 평균 (subplot)
- 제약(상대적 우수 사업부)은 강조색, OLED는 회색 계열로 구분
- 막대 위에 정확한 값을 텍스트로 표시

실행 전 준비:
- Application Default Credentials 설정 (예: GOOGLE_APPLICATION_CREDENTIALS 환경변수)
- pip install google-cloud-bigquery db-dtypes
"""

from google.cloud import bigquery
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PROJECT_ID = "project-2aaebe68-e80f-406b-80f"
DATASET = "accounting"

HIGHLIGHT_COLOR = "#2E7D32"  # 제약 (강조)
BASE_COLOR = "#B0B0B0"  # OLED (회색)


def load_margin_by_bu(client):
    sql = f"""
        WITH sales_bu AS (
            SELECT
                p.`사업부` AS `사업부`,
                SUM(s.`공급가액`) AS `총매출`,
                SUM(s.`수량` * p.`표준원가`) AS `총원가`
            FROM `{PROJECT_ID}.{DATASET}.매출상세` s
            LEFT JOIN `{PROJECT_ID}.{DATASET}.제품마스터` p
                ON s.`제품코드` = p.`제품코드`
            GROUP BY p.`사업부`
        ),
        sga_bu AS (
            SELECT g.`사업부` AS `사업부`, SUM(g.`금액`) AS `판관비`
            FROM `{PROJECT_ID}.{DATASET}.GL원장` g
            LEFT JOIN `{PROJECT_ID}.{DATASET}.계정과목마스터` a
                ON g.`계정코드` = a.`계정코드`
            WHERE a.`계정분류` = '판관비'
            GROUP BY g.`사업부`
        )
        SELECT
            sales_bu.`사업부` AS `사업부`,
            sales_bu.`총매출` AS `총매출`,
            sales_bu.`총원가` AS `총원가`,
            COALESCE(sga_bu.`판관비`, 0) AS `판관비`
        FROM sales_bu
        LEFT JOIN sga_bu ON sales_bu.`사업부` = sga_bu.`사업부`
        ORDER BY sales_bu.`사업부`
    """
    df = client.query(sql).to_dataframe()
    df["영업이익"] = df["총매출"] - df["총원가"] - df["판관비"]
    df["영업이익률"] = df["영업이익"] / df["총매출"] * 100
    return df[["사업부", "영업이익률"]]


def load_budget_achievement_by_bu(client):
    sql = f"""
        WITH budget_bu AS (
            SELECT `사업부` AS `사업부`, SUM(`예산매출`) AS `예산`
            FROM `{PROJECT_ID}.{DATASET}.예산`
            GROUP BY `사업부`
        ),
        sales_bu AS (
            SELECT p.`사업부` AS `사업부`, SUM(s.`공급가액`) AS `실적`
            FROM `{PROJECT_ID}.{DATASET}.매출상세` s
            LEFT JOIN `{PROJECT_ID}.{DATASET}.제품마스터` p
                ON s.`제품코드` = p.`제품코드`
            GROUP BY p.`사업부`
        )
        SELECT budget_bu.`사업부` AS `사업부`, budget_bu.`예산` AS `예산`, sales_bu.`실적` AS `실적`
        FROM budget_bu
        LEFT JOIN sales_bu ON budget_bu.`사업부` = sales_bu.`사업부`
        ORDER BY budget_bu.`사업부`
    """
    df = client.query(sql).to_dataframe()
    df["예산달성률"] = df["실적"] / df["예산"] * 100
    return df[["사업부", "예산달성률"]]


def bar_colors(bu_series):
    return [HIGHLIGHT_COLOR if bu == "제약" else BASE_COLOR for bu in bu_series]


def build_comparison_chart(margin_df, budget_df):
    fig = make_subplots(rows=1, cols=2, subplot_titles=("사업부별 영업이익률", "사업부별 예산달성률"))

    fig.add_trace(
        go.Bar(
            x=margin_df["사업부"],
            y=margin_df["영업이익률"],
            marker_color=bar_colors(margin_df["사업부"]),
            text=[f"{v:.1f}%" for v in margin_df["영업이익률"]],
            textposition="outside",
            name="영업이익률",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            x=budget_df["사업부"],
            y=budget_df["예산달성률"],
            marker_color=bar_colors(budget_df["사업부"]),
            text=[f"{v:.1f}%" for v in budget_df["예산달성률"]],
            textposition="outside",
            name="예산달성률",
        ),
        row=1,
        col=2,
    )

    fig.update_yaxes(title_text="영업이익률 (%)", row=1, col=1)
    fig.update_yaxes(title_text="예산달성률 (%)", row=1, col=2)
    fig.update_layout(
        title="사업부별 성과 비교 (제약 강조, OLED 대조)",
        template="plotly_white",
        showlegend=False,
    )
    return fig


def main():
    client = bigquery.Client(project=PROJECT_ID)
    margin_df = load_margin_by_bu(client)
    budget_df = load_budget_achievement_by_bu(client)
    build_comparison_chart(margin_df, budget_df).show()


if __name__ == "__main__":
    main()
