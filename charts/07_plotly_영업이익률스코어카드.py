"""
영업이익률 스코어카드
- BigQuery accounting 데이터셋(매출상세/GL원장/제품마스터/계정과목마스터)을 직접 읽어 재계산한다.
- BigQuery 인증/연결에 실패하면 ../data/ 로컬 엑셀 스냅샷으로 자동 전환해 동작한다
  (인증 정보가 없는 환경에서도 스크립트가 깨지지 않도록 하기 위함).
- 큰 게이지: 최신 회계기간 기준 전체 영업이익률 (-50~50%, 0 미만은 적자로 빨간 배경)
- 작은 숫자 카드: 사업부별(OLED/제약) 영업이익률

실행 전 준비:
- `gcloud auth application-default login` 등으로 Application Default Credentials가 설정되어 있으면 BigQuery 라이브 데이터를 사용한다.
- 인증이 없으면 자동으로 로컬 스냅샷(../data/)을 사용한다.
- pip install google-cloud-bigquery db-dtypes
"""

from google.cloud import bigquery
import pandas as pd
import plotly.graph_objects as go

from _local_snapshot import load_local_tables

PROJECT_ID = "project-2aaebe68-e80f-406b-80f"
DATASET = "accounting"


def run_query(client, sql, params=None):
    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    return client.query(sql, job_config=job_config).to_dataframe()


def _load_from_bigquery():
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

    return latest_period, operating_margin, by_bu


def _load_from_local():
    sales, product, gl_classified, _ = load_local_tables()
    latest_period = sorted(sales["회계기간"].unique())[-1]

    sales_p = sales.loc[sales["회계기간"] == latest_period].merge(
        product[["제품코드", "표준원가"]], on="제품코드", how="left"
    )
    total_revenue = sales_p["공급가액"].sum()
    total_cogs = (sales_p["수량"] * sales_p["표준원가"]).sum()

    gl_p = gl_classified.loc[gl_classified["회계기간"] == latest_period]
    total_sga = gl_p.loc[gl_p["계정분류"] == "판관비", "금액"].sum()

    operating_profit = total_revenue - total_cogs - total_sga
    operating_margin = operating_profit / total_revenue * 100 if total_revenue else 0

    sales_bu = sales.loc[sales["회계기간"] == latest_period].merge(
        product[["제품코드", "사업부", "표준원가"]], on="제품코드", how="left"
    )
    revenue_bu = sales_bu.groupby("사업부")["공급가액"].sum().rename("총매출")
    cogs_bu = (sales_bu["수량"] * sales_bu["표준원가"]).groupby(sales_bu["사업부"]).sum().rename("총원가")
    sga_bu = gl_p.loc[gl_p["계정분류"] == "판관비"].groupby("사업부")["금액"].sum().rename("판관비")

    by_bu = pd.concat([revenue_bu, cogs_bu, sga_bu], axis=1).fillna(0).reset_index()
    by_bu["영업이익"] = by_bu["총매출"] - by_bu["총원가"] - by_bu["판관비"]
    by_bu["영업이익률"] = by_bu["영업이익"] / by_bu["총매출"] * 100

    return latest_period, operating_margin, by_bu


def main():
    try:
        latest_period, operating_margin, by_bu = _load_from_bigquery()
        source = "BigQuery 라이브"
    except Exception as e:
        print(f"[안내] BigQuery 연결 실패({e}) -> 로컬 스냅샷(../data/)으로 전환합니다.")
        latest_period, operating_margin, by_bu = _load_from_local()
        source = "로컬 스냅샷"

    build_scorecard(latest_period, operating_margin, by_bu, source).show()


def build_scorecard(latest_period, operating_margin, by_bu, source="BigQuery 라이브"):
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
        title=f"영업이익률 스코어카드 ({latest_period} 기준 · {source})",
        template="plotly_white",
        height=450,
    )
    return fig


if __name__ == "__main__":
    main()
