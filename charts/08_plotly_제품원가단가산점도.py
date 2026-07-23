"""
제품 표준원가 vs 평균 판매단가 산점도
- BigQuery accounting 데이터셋(제품마스터/매출상세)을 직접 읽어 제품별 평균 판매단가를 재계산한다.
- 목적: 판매단가가 표준원가에 비례해(cost-plus) 일관되게 책정되고 있는지 확인.
- x축: 표준원가, y축: 제품별 평균 판매단가
- plotly.express scatter + trendline="ols"로 추세선 자동 표시, 오른쪽 위에 피어슨 상관계수(r) 표시

실행 전 준비:
- Application Default Credentials 설정 (예: GOOGLE_APPLICATION_CREDENTIALS 환경변수)
- pip install google-cloud-bigquery db-dtypes statsmodels
"""

from google.cloud import bigquery
import plotly.express as px

PROJECT_ID = "project-2aaebe68-e80f-406b-80f"
DATASET = "accounting"


def load_product_price_data(client):
    sql = f"""
        SELECT
            p.`제품코드` AS `제품코드`,
            p.`제품명` AS `제품명`,
            p.`표준원가` AS `표준원가`,
            AVG(s.`단가`) AS `평균단가`
        FROM `{PROJECT_ID}.{DATASET}.제품마스터` p
        LEFT JOIN `{PROJECT_ID}.{DATASET}.매출상세` s
            ON p.`제품코드` = s.`제품코드`
        GROUP BY p.`제품코드`, p.`제품명`, p.`표준원가`
    """
    return client.query(sql).to_dataframe()


def build_scatter(df):
    corr = df["표준원가"].corr(df["평균단가"])

    fig = px.scatter(
        df,
        x="표준원가",
        y="평균단가",
        trendline="ols",
        hover_data={"제품코드": True},
        labels={"표준원가": "표준원가 (원)", "평균단가": "평균 판매단가 (원)"},
        title="제품별 표준원가 vs 평균 판매단가",
    )
    fig.update_traces(marker=dict(size=8, color="#4C78A8", opacity=0.7), selector=dict(mode="markers"))
    fig.update_traces(line=dict(color="#D62728", width=2), selector=dict(mode="lines"))

    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.98,
        y=0.98,
        text=f"r = {corr:.2f}",
        showarrow=False,
        font=dict(size=16, color="#333333"),
        bgcolor="rgba(255,255,255,0.7)",
    )

    fig.update_layout(template="plotly_white")
    return fig


def main():
    client = bigquery.Client(project=PROJECT_ID)
    df = load_product_price_data(client)
    build_scatter(df).show()


if __name__ == "__main__":
    main()
