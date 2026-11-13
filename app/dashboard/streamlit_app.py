"""
streamlit_app.py - Dashboard tang ung dung (muc 3.9.1), container "streamlit", cong 8501.

  Tab 1  Tong quan KPI         : doc Star Schema tang Gold qua Trino
  Tab 2  Du bao doanh thu      : lich su (wide_daily_sales) + du bao 30 ngay cua mo hinh dang trien khai (MinIO)
  Tab 3  Lich su huan luyen    : chi so cua tung phien ban mo hinh trong Model Registry
  Thanh ben: Tro ly AI (goi container groq-agent qua HTTP)
"""
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from common import config, registry, trino_client
from dashboard import queries as Q

CACHE_TTL = 600            # giay: ket qua truy van duoc dung lai trong 10 phut
COLORS = {"Noi dia (UK)": "#1F4E79", "Quoc te": "#E07B39"}
MARKET_LABEL = {"Noi dia (UK)": "Nội địa (UK)", "Quoc te": "Quốc tế"}


# ============================================================ Lop truy cap du lieu (co cache)
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def sql(query: str) -> pd.DataFrame:
    return trino_client.run_query(query, user="streamlit")


@st.cache_data(ttl=300, show_spinner=False)
def deployed_version():
    return registry.resolve_deployed()


@st.cache_data(ttl=300, show_spinner=False)
def versions():
    return registry.list_versions()


@st.cache_data(ttl=300, show_spinner=False)
def metrics_of(version: str):
    return registry.load_metrics(version)


@st.cache_data(ttl=300, show_spinner=False)
def csv_of(version: str, name: str):
    return registry.get_csv(registry.version_key(version, name))


@st.cache_data(ttl=60, show_spinner=False)
def agent_health():
    try:
        return requests.get(f"{config.AGENT_URL}/health", timeout=3).json()
    except Exception:  # noqa: BLE001
        return None


# ============================================================ Tien ich hien thi
def money(x) -> str:
    if x is None or pd.isna(x):
        return "–"
    return "£" + f"{x:,.0f}".replace(",", ".")


def num(x) -> str:
    if x is None or pd.isna(x):
        return "–"
    return f"{x:,.0f}".replace(",", ".")


def pct(x) -> str:
    if x is None or pd.isna(x):
        return "–"
    return f"{x * 100:.1f}%".replace(".", ",")


def vline(fig, x, text):
    """Duong doc phan ranh lich su / du bao (ve bang shape de tranh loi annotation tren truc ngay)."""
    fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper", line=dict(color="#555", dash="dash", width=1))
    fig.add_annotation(x=x, y=1, yref="paper", text=text, showarrow=False, xanchor="left", yanchor="bottom",
                       font=dict(size=11, color="#555"))


# ============================================================ Tab 1
def tab_overview():
    bounds = sql(Q.date_bounds())
    d0, d1 = pd.to_datetime(bounds.d0[0]).date(), pd.to_datetime(bounds.d1[0]).date()
    c1, c2 = st.columns([2, 1])
    picked = c1.date_input("Khoảng thời gian", value=(d0, d1), min_value=d0, max_value=d1, format="DD/MM/YYYY")
    market = c2.selectbox("Thị trường", list(Q.MARKETS))
    if not isinstance(picked, (tuple, list)) or len(picked) != 2:
        st.info("Chọn đủ ngày bắt đầu và ngày kết thúc.")
        return
    start, end = picked

    k = sql(Q.kpis(start, end, market)).iloc[0]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tổng doanh thu", money(k.revenue))
    m2.metric("Số đơn hàng", num(k.orders))
    m3.metric("Giá trị đơn trung bình (AOV)", money(k.aov))
    m4.metric("Khách hàng định danh", num(k.customers))
    if pd.isna(k.revenue):
        st.warning("Không có giao dịch trong điều kiện lọc đã chọn.")
        return

    left, right = st.columns([2, 1])
    monthly = sql(Q.monthly_by_market(start, end, market))
    monthly["market"] = monthly["market"].map(MARKET_LABEL)
    fig = px.line(monthly, x="month", y="revenue", color="market", markers=True,
                  color_discrete_map={MARKET_LABEL[k_]: v for k_, v in COLORS.items()},
                  labels={"month": "Tháng", "revenue": "Doanh thu (£)", "market": "Thị trường"})
    fig.update_layout(title="Doanh thu theo tháng", height=380, legend=dict(orientation="h", y=-0.2))
    left.plotly_chart(fig, use_container_width=True)
    if end.month == 12 and end.year == 2011 and end.day < 31:
        left.caption("Tháng 12/2011 chỉ có dữ liệu đến 09/12/2011 nên doanh thu tháng này thấp hơn thực tế.")

    share = sql(Q.market_share(start, end, market))
    share["market"] = share["market"].map(MARKET_LABEL)
    fig = px.pie(share, names="market", values="revenue", hole=0.55, color="market",
                 color_discrete_map={MARKET_LABEL[k_]: v for k_, v in COLORS.items()})
    fig.update_traces(textinfo="percent+label", sort=False)
    fig.update_layout(title="Tỷ trọng doanh thu", height=380, showlegend=False)
    right.plotly_chart(fig, use_container_width=True)

    left, right = st.columns(2)
    top = sql(Q.top_products(start, end, market))
    top["label"] = top["stock_code"] + " · " + top["description"].fillna("").str.slice(0, 32)
    fig = px.bar(top.sort_values("revenue"), x="revenue", y="label", orientation="h",
                 labels={"revenue": "Doanh thu (£)", "label": ""}, color_discrete_sequence=["#1F4E79"])
    fig.update_layout(title="Top 10 sản phẩm theo doanh thu", height=420)
    left.plotly_chart(fig, use_container_width=True)

    ctry = sql(Q.top_export_countries(start, end, market))
    if ctry.empty:
        right.info("Bộ lọc đang chọn thị trường nội địa nên không có dữ liệu xuất khẩu.")
    else:
        fig = px.bar(ctry.sort_values("revenue"), x="revenue", y="country", orientation="h",
                     labels={"revenue": "Doanh thu (£)", "country": ""}, color_discrete_sequence=["#E07B39"])
        fig.update_layout(title="Top 10 thị trường xuất khẩu", height=420)
        right.plotly_chart(fig, use_container_width=True)


# ============================================================ Tab 2
def tab_forecast():
    hist = sql(Q.daily_history())
    hist["sale_date"] = pd.to_datetime(hist["sale_date"])
    version, source = deployed_version()
    fc = csv_of(version, "forecast.csv") if version else None
    met = metrics_of(version) if version else None

    if version is None:
        st.warning("Model Registry chưa có mô hình đạt nghiệm thu. Hãy chạy model_retrain_dag trên Airflow.")
    else:
        msg = f"Mô hình đang phục vụ: **{version}**"
        if met:
            msg += f" · huấn luyện lúc {met.get('trained_at', '–')[:19].replace('T', ' ')} UTC"
            msg += f" · WAPE kiểm định {pct(met['tuned_prophet']['wape'])}"
        if source == "fallback":
            msg += " · (chưa có latest.json, dùng phiên bản mới nhất đạt nghiệm thu)"
        st.caption(msg)

    view = st.radio("Phạm vi hiển thị", ["6 tháng gần nhất", "Toàn bộ lịch sử"], horizontal=True)
    last_day = hist["sale_date"].max()
    h = hist if view == "Toàn bộ lịch sử" else hist[hist["sale_date"] > last_day - timedelta(days=182)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=h.sale_date, y=h.total_revenue, name="Doanh thu thực tế",
                             line=dict(color="#9AA5B1", width=1)))
    fig.add_trace(go.Scatter(x=h.sale_date, y=h.rolling_mean_7d, name="Trung bình trượt 7 ngày",
                             line=dict(color="#1F4E79", width=2)))
    fig.add_trace(go.Scatter(x=h.sale_date, y=h.rolling_mean_30d, name="Trung bình trượt 30 ngày",
                             line=dict(color="#2E8B57", width=2)))
    if fc is not None and not fc.empty:
        fc["ds"] = pd.to_datetime(fc["ds"])
        lo, hi = fc["yhat_lower"].clip(lower=0), fc["yhat_upper"].clip(lower=0)
        fig.add_trace(go.Scatter(x=pd.concat([fc.ds, fc.ds[::-1]]), y=pd.concat([hi, lo[::-1]]),
                                 fill="toself", fillcolor="rgba(224,123,57,0.18)", line=dict(width=0),
                                 name="Khoảng tin cậy 80%", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fc.ds, y=fc.yhat.clip(lower=0), name="Dự báo Prophet",
                                 line=dict(color="#E07B39", width=2, dash="dash")))
    vline(fig, last_day, " Bắt đầu dự báo")
    fig.update_layout(height=470, yaxis_title="Doanh thu (£)", hovermode="x unified",
                      legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig, use_container_width=True)

    if fc is None or fc.empty:
        st.info("Chưa có file forecast.csv của mô hình đang phục vụ.")
        return
    yhat = fc["yhat"].clip(lower=0)
    peak = fc.loc[yhat.idxmax()]
    m1, m2, m3 = st.columns(3)
    m1.metric(f"Tổng doanh thu dự báo {len(fc)} ngày", money(yhat.sum()))
    m2.metric("Trung bình mỗi ngày", money(yhat.mean()))
    m3.metric(f"Ngày đỉnh dự kiến ({money(max(peak.yhat, 0))})", peak.ds.strftime("%d/%m/%Y"))
    with st.expander("Bảng dự báo chi tiết theo ngày"):
        table = pd.DataFrame({
            "Ngày": fc.ds.dt.strftime("%d/%m/%Y"),
            "Dự báo (£)": yhat.round(0),
            "Cận dưới 80% (£)": fc.yhat_lower.clip(lower=0).round(0),
            "Cận trên 80% (£)": fc.yhat_upper.clip(lower=0).round(0),
        })
        st.dataframe(table, hide_index=True, use_container_width=True)
    st.caption("Giá trị dự báo âm được cắt về 0 vì doanh thu không thể âm.")


# ============================================================ Tab 3
def tab_history():
    vs = versions()
    if not vs:
        st.warning("Model Registry chưa có phiên bản nào.")
        return
    deployed, _ = deployed_version()
    rows = []
    for v in vs:
        m = metrics_of(v)
        if not m:
            continue
        acc = m.get("acceptance", {})
        rows.append({
            "Phiên bản": v,
            "Huấn luyện lúc (UTC)": m.get("trained_at", "")[:19].replace("T", " "),
            "Chế độ": m.get("mode", ""),
            "WAPE Tuned": m["tuned_prophet"]["wape"],
            "WAPE Baseline": m["baseline_prophet"]["wape"],
            "WAPE Seasonal naive": m["seasonal_naive"]["wape"],
            "MAE (£)": m["tuned_prophet"]["mae"],
            "RMSE (£)": m["tuned_prophet"]["rmse"],
            "Ngưỡng WAPE": acc.get("max_wape", config.DEFAULT_MAX_WAPE),
            "Đạt nghiệm thu": bool(acc.get("passed")),
            "Đang phục vụ": v == deployed,
        })
    if not rows:
        st.warning("Không đọc được metrics.json của phiên bản nào.")
        return
    df = pd.DataFrame(rows)
    df["Cảnh báo"] = df.apply(lambda r: "Vượt ngưỡng" if r["WAPE Tuned"] > r["Ngưỡng WAPE"]
                              else ("Chưa đạt" if not r["Đạt nghiệm thu"] else ""), axis=1)
    failed = (df["Cảnh báo"] != "").sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Số lần huấn luyện", len(df))
    c2.metric("Đạt nghiệm thu", int(df["Đạt nghiệm thu"].sum()))
    c3.metric("Cần xem lại", int(failed))
    if failed:
        st.warning(f"{failed} phiên bản không đạt tiêu chí nghiệm thu, không được đưa vào phục vụ.")

    show = df.copy()
    for c in ["WAPE Tuned", "WAPE Baseline", "WAPE Seasonal naive", "Ngưỡng WAPE"]:
        show[c] = show[c].map(pct)
    for c in ["MAE (£)", "RMSE (£)"]:
        show[c] = show[c].map(num)
    show["Đạt nghiệm thu"] = show["Đạt nghiệm thu"].map({True: "Đạt", False: "Không đạt"})
    show["Đang phục vụ"] = show["Đang phục vụ"].map({True: "●", False: ""})
    st.dataframe(show, hide_index=True, use_container_width=True)

    long = df.melt(id_vars="Phiên bản", value_vars=["WAPE Tuned", "WAPE Baseline", "WAPE Seasonal naive"],
                   var_name="Mô hình", value_name="WAPE")
    fig = px.bar(long, x="Phiên bản", y="WAPE", color="Mô hình", barmode="group",
                 color_discrete_sequence=["#E07B39", "#9AA5B1", "#1F4E79"])
    fig.add_hline(y=df["Ngưỡng WAPE"].iloc[0], line_dash="dash", line_color="#C0392B",
                  annotation_text="Ngưỡng nghiệm thu", annotation_position="top left")
    fig.update_layout(title="WAPE trên tập kiểm tra theo phiên bản (thấp hơn là tốt hơn)", height=380,
                      yaxis_tickformat=".0%", xaxis_type="category")
    st.plotly_chart(fig, use_container_width=True)

    pick = st.selectbox("Xem chi tiết phiên bản", df["Phiên bản"])
    m = metrics_of(pick)
    a, b = st.columns([1, 2])
    with a:
        st.markdown("**Siêu tham số tốt nhất (Grid Search)**")
        st.json(m.get("best_params", {}))
        imp = m.get("improvement_vs_baseline", {})
        if imp:
            st.markdown(f"WAPE giảm **{imp.get('wape_pct', 0):.1f}%** so với Prophet mặc định".replace(".", ",", 1))
        d = m.get("data", {})
        st.caption(f"Train {d.get('train_rows', '–')} ngày · Test {d.get('test_rows', '–')} ngày · {d.get('split', '')}")
    with b:
        tp = csv_of(pick, "test_predictions.csv")
        if tp is None:
            st.info("Phiên bản này không có test_predictions.csv.")
        else:
            tp["ds"] = pd.to_datetime(tp["ds"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=tp.ds, y=tp.y, name="Thực tế", line=dict(color="#9AA5B1", width=1)))
            fig.add_trace(go.Scatter(x=tp.ds, y=tp.baseline_yhat, name="Prophet mặc định",
                                     line=dict(color="#1F4E79", width=1, dash="dot")))
            fig.add_trace(go.Scatter(x=tp.ds, y=tp.tuned_yhat, name="Prophet đã tinh chỉnh",
                                     line=dict(color="#E07B39", width=2)))
            fig.update_layout(title="Dự báo trên tập kiểm tra", height=360, yaxis_title="Doanh thu (£)",
                              legend=dict(orientation="h", y=-0.2), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)


# ============================================================ Thanh ben: Tro ly AI
def sidebar_agent():
    st.sidebar.header("Trợ lý AI")
    health = agent_health()
    if health is None:
        st.sidebar.error("Không kết nối được container groq-agent.")
    elif not health.get("groq_key_configured"):
        st.sidebar.warning("groq-agent chưa có GROQ_API_KEY.")
    else:
        st.sidebar.caption(f"Mô hình: {health.get('model')}")

    with st.sidebar.form("ask", clear_on_submit=True):
        q = st.text_area("Hỏi về dữ liệu bán hàng", height=90,
                         placeholder="Ví dụ: Top 5 sản phẩm bán chạy?")
        sent = st.form_submit_button("Gửi câu hỏi", use_container_width=True)
    if sent and q.strip():
        with st.sidebar:
            with st.spinner("Đang sinh SQL và truy vấn..."):
                try:
                    res = requests.post(f"{config.AGENT_URL}/ask", json={"question": q}, timeout=180).json()
                except Exception as exc:  # noqa: BLE001
                    res = {"question": q, "ok": False, "error": f"Không gọi được groq-agent: {exc}"}
        st.session_state.setdefault("chat", []).insert(0, res)

    for res in st.session_state.get("chat", []):
        st.sidebar.markdown(f"**Hỏi:** {res['question']}")
        if res.get("answer"):
            st.sidebar.markdown(res["answer"])
        if res.get("error"):
            st.sidebar.error(res["error"])
        if res.get("sql"):
            with st.sidebar.expander("Xem SQL và dữ liệu"):
                st.code(res["sql"], language="sql")
                if res.get("rows"):
                    st.dataframe(pd.DataFrame(res["rows"], columns=res["columns"]), hide_index=True)
                st.caption(f"{res.get('row_count', 0)} dòng · {res.get('attempts', 0)} lần sinh SQL · "
                           f"{res.get('elapsed_s', '–')} giây")
        st.sidebar.divider()


# ============================================================ Trang chinh
def main():
    st.set_page_config(page_title="Online Retail Lakehouse", page_icon="📊", layout="wide")
    # Thanh ben rong hon de doc duoc cau SQL va bang ket qua cua Tro ly AI
    st.markdown("<style>section[data-testid='stSidebar']{width:430px !important;}</style>",
                unsafe_allow_html=True)
    st.title("Dashboard doanh thu Online Retail II")
    if st.button("Làm mới dữ liệu"):
        st.cache_data.clear()
    sidebar_agent()
    t1, t2, t3 = st.tabs(["Tổng quan KPI", "Dự báo doanh thu", "Lịch sử huấn luyện"])
    with t1:
        try:
            tab_overview()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Không truy vấn được tầng Gold qua Trino: {exc}")
    with t2:
        try:
            tab_forecast()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Không tải được dữ liệu dự báo: {exc}")
    with t3:
        try:
            tab_history()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Không đọc được Model Registry: {exc}")


if __name__ == "__main__":
    main()
