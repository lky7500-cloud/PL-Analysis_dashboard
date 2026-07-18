import glob
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(page_title="PL Analysis Dashboard", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }
    .dashboard-header {
        padding-bottom: 1rem;
        margin-bottom: 1.5rem;
        border-bottom: 2px solid var(--primary-color);
    }
    .dashboard-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
    }
    .dashboard-header p {
        margin: 0.15rem 0 0 0;
        font-size: 1rem;
        opacity: 0.65;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: 700;
        margin: 0 0 0.75rem 0;
    }
    div[data-testid="stMetric"] {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 10px;
        padding: 1rem 1rem 0.75rem 1rem;
    }
    footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


@st.cache_data
def load_all_excel_data(data_dir=DATA_DIR):
    """data 폴더 내 모든 xlsx 파일을 {파일명: DataFrame} 형태로 읽어온다."""
    dataframes = {}
    for file_path in sorted(glob.glob(os.path.join(data_dir, "*.xlsx"))):
        filename = os.path.basename(file_path)
        try:
            dataframes[filename] = pd.read_excel(file_path)
        except Exception as e:
            st.error(f"'{filename}' 파일을 읽는 중 오류가 발생했습니다: {e}")
    return dataframes


def get_existing_columns(df, required_columns):
    """required_columns 중 df에 실제로 존재하는 컬럼만 반환한다."""
    return [col for col in required_columns if col in df.columns]


dataframes = load_all_excel_data()

if not dataframes:
    st.warning("data 폴더에서 읽을 수 있는 엑셀 파일을 찾지 못했습니다.")
    st.stop()

customer = dataframes["01_거래처마스터.xlsx"]
product = dataframes["02_제품마스터.xlsx"]
account = dataframes["03_계정과목마스터.xlsx"]
budget = dataframes["04_예산.xlsx"]
sales = dataframes["05_매출상세.xlsx"]
gl = dataframes["06_GL원장.xlsx"]

gl_classified = gl.merge(account[["계정코드", "계정분류"]], on="계정코드", how="left")

st.markdown(
    """
    <div class="dashboard-header">
        <h1>PL Analysis Dashboard</h1>
        <p>경영성과 및 수익성 분석</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def section_header(number, title):
    st.markdown(f'<p class="section-header">{number} {title}</p>', unsafe_allow_html=True)


periods = sorted(sales["회계기간"].unique())

st.sidebar.subheader("🔍 조회 조건")
start_period, end_period = st.sidebar.select_slider(
    "조회 기간 (부터 ~ 까지)",
    options=periods,
    value=(periods[0], periods[-1]),
)
selected_periods = [p for p in periods if start_period <= p <= end_period]
st.sidebar.caption(f"데이터 범위: {periods[0]} ~ {periods[-1]}")


def calc_total_revenue(periods_list):
    return sales.loc[sales["회계기간"].isin(periods_list), "공급가액"].sum()


def calc_cost_components(periods_list):
    sales_m = sales.loc[sales["회계기간"].isin(periods_list)].merge(
        product[["제품코드", "표준원가"]], on="제품코드", how="left"
    )
    total_cogs = (sales_m["수량"] * sales_m["표준원가"]).sum()

    total_sga = gl_classified.loc[
        gl_classified["회계기간"].isin(periods_list) & (gl_classified["계정분류"] == "판관비"),
        "금액",
    ].sum()

    return total_cogs, total_sga


def calc_operating_profit(periods_list):
    total_cogs, total_sga = calc_cost_components(periods_list)
    return calc_total_revenue(periods_list) - total_cogs - total_sga


def calc_kpis(periods_list):
    total_revenue = calc_total_revenue(periods_list)
    total_cogs, total_sga = calc_cost_components(periods_list)
    total_cost = total_cogs + total_sga
    operating_profit = total_revenue - total_cost
    operating_margin = operating_profit / total_revenue * 100 if total_revenue else None

    total_budget = budget.loc[budget["회계기간"].isin(periods_list), "예산매출"].sum()
    budget_achievement = total_revenue / total_budget * 100 if total_budget else None

    end_period = periods_list[-1]
    end_idx = periods.index(end_period)
    if end_idx > 0:
        prev_period = periods[end_idx - 1]
        current_month_revenue = calc_total_revenue([end_period])
        prev_month_revenue = calc_total_revenue([prev_period])
        mom_growth = (
            (current_month_revenue - prev_month_revenue) / prev_month_revenue * 100
            if prev_month_revenue
            else None
        )
    else:
        mom_growth = None

    return {
        "총매출": total_revenue,
        "총비용": total_cost,
        "영업이익": operating_profit,
        "영업이익률": operating_margin,
        "예산달성률": budget_achievement,
        "전월 대비 증감률": mom_growth,
    }


kpis = calc_kpis(selected_periods)


def fmt_amount(value):
    return f"{value / 1e8:,.0f}억원"


def fmt_percent(value):
    return f"{value:+.1f}%" if value is not None else "N/A"


section_header("①", "KPI 요약")
row1_col1, row1_col2, row1_col3 = st.columns(3)
row1_col1.metric("총매출", fmt_amount(kpis["총매출"]))
row1_col2.metric("총비용", fmt_amount(kpis["총비용"]))
row1_col3.metric("영업이익", fmt_amount(kpis["영업이익"]))

row2_col1, row2_col2, row2_col3 = st.columns(3)
row2_col1.metric("영업이익률", fmt_percent(kpis["영업이익률"]))
row2_col2.metric("예산달성률", fmt_percent(kpis["예산달성률"]))
row2_col3.metric("전월 대비 증감률", fmt_percent(kpis["전월 대비 증감률"]))


def build_monthly_summary(periods_list):
    sales_f = sales.loc[sales["회계기간"].isin(periods_list)]
    revenue = sales_f.groupby("회계기간")["공급가액"].sum().rename("총매출")

    sales_cost = sales_f.merge(product[["제품코드", "표준원가"]], on="제품코드", how="left")
    cogs = (sales_cost["수량"] * sales_cost["표준원가"]).groupby(sales_cost["회계기간"]).sum().rename("COGS")

    gl_f = gl_classified.loc[gl_classified["회계기간"].isin(periods_list)]
    sga = gl_f.loc[gl_f["계정분류"] == "판관비"].groupby("회계기간")["금액"].sum().rename("SGA")

    summary = pd.concat([revenue, cogs, sga], axis=1).fillna(0).reset_index()
    summary["총비용"] = summary["COGS"] + summary["SGA"]
    summary["영업이익"] = summary["총매출"] - summary["총비용"]
    return summary.sort_values("회계기간")[["회계기간", "총매출", "총비용", "영업이익"]]


def build_monthly_trend_chart(summary):
    fig = go.Figure()
    for column, color in [("총매출", "#4C78A8"), ("총비용", "#D62728"), ("영업이익", "#54A24B")]:
        fig.add_trace(
            go.Scatter(
                x=summary["회계기간"],
                y=summary[column] / 1e6,
                name=column,
                mode="lines+markers",
                line=dict(color=color),
                hovertemplate=f"{column}: " + "%{y:,.0f}백만원<extra></extra>",
            )
        )
    fig.update_layout(
        title="월별 매출/비용/영업이익 추이",
        xaxis_title="회계기간",
        yaxis_title="금액 (백만원)",
        hovermode="x unified",
        template="plotly_white",
    )
    return fig


st.divider()
section_header("②", "월별 손익 추이")
monthly_summary = build_monthly_summary(selected_periods)
st.plotly_chart(build_monthly_trend_chart(monthly_summary), use_container_width=True)


def build_business_unit_summary(periods_list):
    sales_p = sales.loc[sales["회계기간"].isin(periods_list)].merge(
        product[["제품코드", "사업부", "표준원가"]], on="제품코드", how="left"
    )
    revenue = sales_p.groupby("사업부")["공급가액"].sum().rename("총매출")
    cogs = (sales_p["수량"] * sales_p["표준원가"]).groupby(sales_p["사업부"]).sum().rename("COGS")

    gl_p = gl_classified.loc[gl_classified["회계기간"].isin(periods_list)]
    sga = gl_p.loc[gl_p["계정분류"] == "판관비"].groupby("사업부")["금액"].sum().rename("SGA")

    summary = pd.concat([revenue, cogs, sga], axis=1).fillna(0).reset_index()
    summary["총비용"] = summary["COGS"] + summary["SGA"]
    summary["영업이익"] = summary["총매출"] - summary["총비용"]
    summary["영업이익률"] = summary["영업이익"] / summary["총매출"] * 100
    return summary.sort_values("총매출", ascending=False)[
        ["사업부", "총매출", "총비용", "영업이익", "영업이익률"]
    ]


def build_business_unit_chart(summary):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for column, color in [("총매출", "#4C78A8"), ("총비용", "#D62728"), ("영업이익", "#54A24B")]:
        fig.add_trace(
            go.Bar(
                x=summary["사업부"],
                y=summary[column] / 1e6,
                name=column,
                marker_color=color,
                hovertemplate=f"{column}: " + "%{y:,.0f}백만원<extra></extra>",
            ),
            secondary_y=False,
        )
    fig.add_trace(
        go.Scatter(
            x=summary["사업부"],
            y=summary["영업이익률"],
            name="영업이익률",
            mode="lines+markers",
            line=dict(color="#F58518", width=3),
            marker=dict(size=10),
            hovertemplate="영업이익률: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(
        title="사업부별 매출/비용/영업이익 및 영업이익률",
        barmode="group",
        template="plotly_white",
    )
    fig.update_yaxes(title_text="금액 (백만원)", secondary_y=False)
    fig.update_yaxes(title_text="영업이익률 (%)", secondary_y=True)
    return fig


st.divider()
section_header("③", "사업부별 수익성")
bu_summary = build_business_unit_summary(selected_periods)
st.plotly_chart(build_business_unit_chart(bu_summary), use_container_width=True)

best_bu = bu_summary.loc[bu_summary["영업이익률"].idxmax()]
worst_bu = bu_summary.loc[bu_summary["영업이익률"].idxmin()]
st.markdown(
    f"- 가장 수익성이 높은 사업부: **{best_bu['사업부']}** (영업이익률 {best_bu['영업이익률']:.1f}%)\n"
    f"- 가장 수익성이 낮은 사업부: **{worst_bu['사업부']}** (영업이익률 {worst_bu['영업이익률']:.1f}%)"
)


def build_cost_by_account(periods_list):
    gl_p = gl_classified.loc[gl_classified["회계기간"].isin(periods_list)]
    cost = gl_p.loc[gl_p["계정분류"].isin(["원가", "판관비"])]
    return cost.groupby(["계정분류", "계정명"])["금액"].sum().reset_index()


def build_cost_treemap(summary):
    summary = summary.copy()
    summary["금액_백만원"] = summary["금액"] / 1e6
    fig = px.treemap(summary, path=["계정분류", "계정명"], values="금액_백만원", color="계정분류")
    fig.update_traces(
        texttemplate="%{label}<br>%{value:,.0f}백만원<br>%{percentRoot:.1%}",
        hovertemplate="%{label}<br>금액: %{value:,.0f}백만원<br>전체 대비: %{percentRoot:.1%}<extra></extra>",
    )
    fig.update_layout(title="비용 계정별 구성 (Treemap)")
    return fig


st.divider()
section_header("④", "비용 분석")
cost_summary = build_cost_by_account(selected_periods)
st.plotly_chart(build_cost_treemap(cost_summary), use_container_width=True)


def build_budget_vs_actual(periods_list):
    budget_bu = (
        budget.loc[budget["회계기간"].isin(periods_list)].groupby("사업부")["예산매출"].sum().rename("예산")
    )

    sales_bu = (
        sales.loc[sales["회계기간"].isin(periods_list)]
        .merge(product[["제품코드", "사업부"]], on="제품코드", how="left")
        .groupby("사업부")["공급가액"]
        .sum()
        .rename("실적")
    )

    summary = pd.concat([budget_bu, sales_bu], axis=1).fillna(0).reset_index()
    summary["달성률"] = summary["실적"] / summary["예산"] * 100
    return summary


def build_budget_gauge_chart(summary):
    axis_max = max(150, summary["달성률"].max() * 1.1)
    fig = go.Figure()
    for i, row in summary.iterrows():
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=row["달성률"],
                number={"suffix": "%", "valueformat": ".1f"},
                title={"text": row["사업부"]},
                gauge={
                    "axis": {"range": [0, axis_max]},
                    "bar": {"color": "#1f2933"},
                    "steps": [
                        {"range": [0, 90], "color": "#D62728"},
                        {"range": [90, 100], "color": "#F5C518"},
                        {"range": [100, axis_max], "color": "#54A24B"},
                    ],
                    "threshold": {
                        "line": {"color": "black", "width": 3},
                        "thickness": 0.8,
                        "value": 100,
                    },
                },
                domain={"row": 0, "column": i},
            )
        )
    fig.update_layout(
        grid={"rows": 1, "columns": len(summary), "pattern": "independent"},
        title="사업부별 예산 달성률",
    )
    return fig


st.divider()
section_header("⑤", "예산 대비 실적")
budget_summary = build_budget_vs_actual(selected_periods)
st.plotly_chart(build_budget_gauge_chart(budget_summary), use_container_width=True)


def build_customer_revenue(periods_list):
    revenue = (
        sales.loc[sales["회계기간"].isin(periods_list)]
        .groupby("거래처코드")["공급가액"]
        .sum()
        .rename("매출")
        .reset_index()
        .merge(customer[["거래처코드", "거래처명"]], on="거래처코드", how="left")
        .sort_values("매출", ascending=False)
        .reset_index(drop=True)
    )
    total_revenue = revenue["매출"].sum()
    top10 = revenue.head(10).copy()
    top10["비중"] = top10["매출"] / total_revenue * 100
    top10_concentration = top10["매출"].sum() / total_revenue * 100
    return top10, top10_concentration


def build_top_customer_chart(top10):
    ordered = top10.sort_values("매출")
    fig = go.Figure(
        go.Bar(
            x=ordered["매출"] / 1e6,
            y=ordered["거래처명"],
            orientation="h",
            marker_color="#4C78A8",
            customdata=ordered["비중"],
            hovertemplate="%{y}<br>매출: %{x:,.0f}백만원<br>전체 대비: %{customdata:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title="거래처별 매출 TOP10",
        xaxis_title="매출 (백만원)",
        yaxis_title="거래처",
        template="plotly_white",
    )
    return fig


st.divider()
section_header("⑥", "거래처 TOP10")
top10_customers, top10_concentration = build_customer_revenue(selected_periods)
st.plotly_chart(build_top_customer_chart(top10_customers), use_container_width=True)
st.markdown(f"- 상위 10개 거래처 매출 집중도: 전체 매출의 **{top10_concentration:.1f}%**")


def build_product_group_revenue(periods_list):
    sales_p = sales.loc[sales["회계기간"].isin(periods_list)].merge(
        product[["제품코드", "사업부", "제품군"]], on="제품코드", how="left"
    )
    return sales_p.groupby(["사업부", "제품군"])["공급가액"].sum().reset_index()


def build_product_group_sunburst(summary):
    summary = summary.copy()
    summary["공급가액_백만원"] = summary["공급가액"] / 1e6
    fig = px.sunburst(summary, path=["사업부", "제품군"], values="공급가액_백만원", color="사업부")
    fig.update_traces(
        texttemplate="%{label}<br>%{value:,.0f}백만원<br>%{percentRoot:.1%}",
        hovertemplate=(
            "%{label}<br>매출: %{value:,.0f}백만원<br>상위 대비: %{percentParent:.1%}"
            "<br>전체 대비: %{percentRoot:.1%}<extra></extra>"
        ),
    )
    fig.update_layout(title="제품군별 매출 비중 (Sunburst)")
    return fig


st.divider()
section_header("⑦", "제품군 분석")
product_group_summary = build_product_group_revenue(selected_periods)
st.plotly_chart(build_product_group_sunburst(product_group_summary), use_container_width=True)


def build_pl_waterfall_chart(periods_list):
    total_revenue = calc_total_revenue(periods_list) / 1e6
    total_cogs, total_sga = calc_cost_components(periods_list)
    total_cogs /= 1e6
    total_sga /= 1e6
    operating_profit = calc_operating_profit(periods_list) / 1e6

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "relative", "total"],
            x=["매출", "매출원가", "판관비", "영업이익"],
            y=[total_revenue, -total_cogs, -total_sga, 0],
            text=[
                f"{total_revenue:,.0f}백만원",
                f"-{total_cogs:,.0f}백만원",
                f"-{total_sga:,.0f}백만원",
                f"{operating_profit:,.0f}백만원",
            ],
            textposition="outside",
            connector={"line": {"color": "rgb(130,130,130)"}},
            increasing={"marker": {"color": "#54A24B"}},
            decreasing={"marker": {"color": "#D62728"}},
            totals={"marker": {"color": "#4C78A8"}},
        )
    )
    fig.update_layout(
        title="손익 Waterfall (매출 → 매출원가 → 판관비 → 영업이익)",
        yaxis_title="금액 (백만원)",
        template="plotly_white",
        showlegend=False,
    )
    return fig


st.divider()
section_header("⑧", "Waterfall")
st.plotly_chart(build_pl_waterfall_chart(selected_periods), use_container_width=True)


def generate_cfo_insight(periods_list, kpis, bu_summary, budget_summary):
    insights = []
    end_period = periods_list[-1]
    end_idx = periods.index(end_period)
    prev_period = periods[end_idx - 1] if end_idx > 0 else None

    # ① 매출 증가 여부
    mom = kpis["전월 대비 증감률"]
    if mom is None:
        insights.append("전월 데이터가 없어 매출 증감률을 계산할 수 없습니다.")
    else:
        direction = "증가" if mom >= 0 else "감소"
        insights.append(f"매출은 전월 대비 {abs(mom):.1f}% {direction}했습니다.")

    # 비용 계정별 전월 대비 증감 (②③⑦에서 활용) — 선택 기간과 무관하게 마지막 달 기준 단일 비교
    cost_change = None
    if prev_period is not None:
        prev_cost = build_cost_by_account([prev_period]).groupby("계정명")["금액"].sum()
        curr_cost = build_cost_by_account([end_period]).groupby("계정명")["금액"].sum()
        cost_change = curr_cost.subtract(prev_cost, fill_value=0).rename("증감액").sort_values(ascending=False)
    top_cost_name = cost_change.index[0] if cost_change is not None and cost_change.iloc[0] > 0 else None

    # ② 영업이익 변화
    profit_change_pct = None
    if prev_period is not None:
        prev_profit = calc_operating_profit([prev_period])
        current_month_profit = calc_operating_profit([end_period])
        if prev_profit:
            profit_change_pct = (current_month_profit - prev_profit) / prev_profit * 100

    if profit_change_pct is None:
        insights.append("전월 데이터가 없어 영업이익 변동을 비교할 수 없습니다.")
    elif profit_change_pct < 0 and top_cost_name:
        insights.append(f"그러나 {top_cost_name} 증가로 영업이익률이 감소했습니다.")
    else:
        direction = "증가" if profit_change_pct >= 0 else "감소"
        insights.append(f"영업이익은 전월 대비 {abs(profit_change_pct):.1f}% {direction}했습니다.")

    # ③ 가장 많이 증가한 비용 (②에서 이미 언급된 경우 생략)
    mentioned_in_profit_sentence = bool(profit_change_pct is not None and profit_change_pct < 0 and top_cost_name)
    if top_cost_name and not mentioned_in_profit_sentence:
        insights.append(f"이번 달 비용 중에서는 {top_cost_name}이(가) 전월 대비 가장 많이 증가했습니다.")

    # ④⑤ 사업부 수익성
    best_bu = bu_summary.loc[bu_summary["영업이익률"].idxmax()]
    insights.append(f"{best_bu['사업부']} 사업부는 가장 높은 수익성(영업이익률 {best_bu['영업이익률']:.1f}%)을 기록했습니다.")
    if len(bu_summary) > 1:
        worst_bu = bu_summary.loc[bu_summary["영업이익률"].idxmin()]
        insights.append(f"{worst_bu['사업부']} 사업부는 상대적으로 낮은 수익성(영업이익률 {worst_bu['영업이익률']:.1f}%)을 보였습니다.")

    # ⑥ 예산 미달 사업부
    under_budget = budget_summary.loc[budget_summary["달성률"] < 100, "사업부"].tolist()
    if under_budget:
        insights.append(f"{', '.join(under_budget)} 사업부는 예산 대비 실적이 부족하여 원인 분석이 필요합니다.")
    else:
        insights.append("모든 사업부가 예산을 달성했습니다.")

    # ⑦ 개선이 필요한 비용
    if cost_change is not None:
        rising = cost_change[cost_change > 0].head(2).index.tolist()
        if rising:
            insights.append(f"다음 달에는 {', '.join(rising)} 관리가 필요합니다.")

    return insights


st.divider()
section_header("⑨", "AI CFO Insight 📌")
cfo_insights = generate_cfo_insight(selected_periods, kpis, bu_summary, budget_summary)
st.markdown("\n".join(f"- {line}" for line in cfo_insights))
