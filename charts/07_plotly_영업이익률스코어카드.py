"""
영업이익률 스코어카드
- BigQuery accounting 데이터셋(매출상세/GL원장/제품마스터/계정과목마스터)을 직접 읽어 재계산한다.
- 큰 게이지: 최신 회계기간 기준 전체 영업이익률 (-50~50%, 0 미만은 적자로 빨간 배경)
- 작은 숫자 카드: 사업부별(OLED/제약) 영업이익률

실행 전 준비:
- `gcloud auth application-default login` 등으로 Application Default Credentials가 설정되어 있어야 한다.
- pip install google-cloud-bigquery db-dtypes
"""

from google.cloud import bigquery
import plotly.graph_objects as go

PROJECT_ID = "project-2aaebe68-e80f-406b-80f"
DATASET = "accounting"


def run_query(client, sql, params=None):
    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    return client.query(sql, job_config=job_config).to_dataframe()


def main():
    client = bigquery.Client(project=PROJECT_ID)

    latest_period = run_query(
        client,
        f"""
        SELECT MAX(`회계기간`) AS `최신월`
        FROM `{PROJECT_ID}.{DATASET}.매출상세`
        """,
    )["최신월"].iloc[0]

    period_param = [bigquery.ScalarQueryParameter("period", "STRING", latest_period)]

    overall = run_query(
        client,
        f"""
        SELECT
            SUM(s.`공급가액`) AS `총매출`,
            SUM(s.`수량` * p.`표준원가`) AS `총원가`
        FROM `{PROJECT_ID}.{DATASET}.매출상세` s
        LEFT JOIN `{PROJECT_ID}.{DATASET}.제품마스터` p
            ON s.`제품코드` = p.`제품코드`
        WHERE s.`회계기간` = @period
        """,
        period_param,
    )

    overall_sga = run_query(
        client,
        f"""
        SELECT SUM(g.`금액`) AS `총판관비`
        FROM `{PROJECT_ID}.{DATASET}.GL원장` g
        LEFT JOIN `{PROJECT_ID}.{DATASET}.계정과목마스터` a
            ON g.`계정코드` = a.`계정코드`
        WHERE g.`회계기간` = @period AND a.`계정분류` = '판관비'
        """,
        period_param,
    )

    by_bu = run_query(
        client,
        f"""
        WITH sales_bu AS (
            SELECT
                p.`사업부` AS `사업부`,
                SUM(s.`공급가액`) AS `총매출`,
                SUM(s.`수량` * p.`표준원가`) AS `총원가`
            FROM `{PROJECT_ID}.{DATASET}.매출상세` s
            LEFT JOIN `{PROJECT_ID}.{DATASET}.제품마스터` p
                ON s.`제품코드` = p.`제품코드`
            WHERE s.`회계기간` = @period
            GROUP BY p.`사업부`
        ),
        sga_bu AS (
            SELECT g.`사업부` AS `사업부`, SUM(g.`금액`) AS `판관비`
            FROM `{PROJECT_ID}.{DATASET}.GL원장` g
            LEFT JOIN `{PROJECT_ID}.{DATASET}.계정과목마스터` a
                ON g.`계정코드` = a.`계정코드`
            WHERE g.`회계기간` = @period AND a.`계정분류` = '판관비'
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
        """,
        period_param,
    )

    total_revenue = overall["총매출"].iloc[0]
    total_cogs = overall["총원가"].iloc[0]
    total_sga = overall_sga["총판관비"].iloc[0]
    operating_profit = total_revenue - total_cogs - total_sga
    operating_margin = operating_profit / total_revenue * 100 if total_revenue else 0

    by_bu["영업이익"] = by_bu["총매출"] - by_bu["총원가"] - by_bu["판관비"]
    by_bu["영업이익률"] = by_bu["영업이익"] / by_bu["총매출"] * 100

    build_scorecard(latest_period, operating_margin, by_bu).show()


def build_scorecard(latest_period, operating_margin, by_bu):
    fig = go.Figure()

    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=operating_margin,
            number={"suffix": "%", "valueformat": ".1f"},
            title={"text": f"전체 영업이익률 ({latest_period})", "font": {"size": 20}},
            gauge={
                "axis": {"range": [-50, 50]},
                "bar": {"color": "#D62728" if operating_margin < 0 else "#2E7D32"},
                "steps": [
                    {"range": [-50, 0], "color": "#F4C7C3"},
                    {"range": [0, 50], "color": "#C9E4CA"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 3},
                    "thickness": 0.8,
                    "value": 0,
                },
            },
            domain={"x": [0, 0.55], "y": [0, 1]},
        )
    )

    n = len(by_bu)
    card_height = 1 / n
    for i, (_, row) in enumerate(by_bu.iterrows()):
        color = "#D62728" if row["영업이익률"] < 0 else "#2E7D32"
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=row["영업이익률"],
                number={"suffix": "%", "valueformat": ".1f", "font": {"color": color, "size": 44}},
                title={"text": f"{row['사업부']} 영업이익률", "font": {"size": 16}},
                domain={
                    "x": [0.65, 1],
                    "y": [1 - (i + 1) * card_height + 0.08, 1 - i * card_height - 0.08],
                },
            )
        )

    fig.update_layout(
        title=f"영업이익률 스코어카드 ({latest_period} 기준)",
        template="plotly_white",
        height=450,
    )
    return fig


if __name__ == "__main__":
    main()
