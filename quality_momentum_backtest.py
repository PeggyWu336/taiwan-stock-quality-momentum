# -*- coding: utf-8 -*-
"""Taiwan stock Quality x Momentum backtest."""

# ===========================================
# Taiwan stocks: Quality x Momentum main script (runs end to end)
# - Universe: market cap + liquidity + free float (percentile thresholds)
# - Quality: average z-score of several financial-statement metrics
# - Momentum: 6M / 9M / 12M
# - Portfolios: Top5/10/30/50, equal weight
# - Costs: buy commission + sell commission + transaction tax
#   (trading volume estimated from weight changes)
# - 0050: benchmark, net of costs, used in comparison charts
# Outputs:
#   results_net_ret, results_wealth, wealth_df
#   3 wealth charts + performance summary for each strategy
# ===========================================

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ========== Parameters (adjustable) ==========
FEE_BUY  = 0.001425
FEE_SELL = 0.001425
TAX_SELL = 0.003

MIN_FREE_FLOAT = 40
MCAP_PCT       = 0.3
TURNOVER_PCT   = 0.3
QUALITY_TOP_PCT = 0.3

TOP_LIST = [5, 10, 30, 50]

px.defaults.template = "plotly_white"
px.defaults.width = 980
px.defaults.height = 560
FONT_FAMILY = "Microsoft JhengHei, Noto Sans CJK TC, PingFang TC"

# Colors (adjustable)
COLOR_STRATEGY = "#2E7D6B"   # strategy color
COLOR_0050     = "#9E9E9E"   # gray

# ========== File paths (data/ folder, not included in repo) ==========
DATA_DIR = "data"
PATH_MONTHLY_PANEL = f"{DATA_DIR}/monthly_panel.csv"
PATH_0050          = f"{DATA_DIR}/0050_monthly.csv"

# ========== Load data ==========
df  = pd.read_csv(PATH_MONTHLY_PANEL)
bmk = pd.read_csv(PATH_0050)

# ========== Clean date / numeric columns (relies on ym only) ==========
df["ym"] = pd.PeriodIndex(df["ym"].astype(str), freq="M").astype(str)

need_num_cols = ["close_eom", "mktcap_eom", "avg_turnover_m", "free_float", "monthly_ret"]
for c in need_num_cols:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

df = df.sort_values(["stock_id", "ym"]).reset_index(drop=True)

# 0050: convert to year-month + compute returns
# (bmk may already have ym = YYYY-MM; handled defensively here)
bmk["ym"] = pd.PeriodIndex(bmk["ym"].astype(str), freq="M").astype(str)
bmk["close"] = pd.to_numeric(bmk["close"], errors="coerce")
bmk = bmk.sort_values("ym").reset_index(drop=True)
bmk["ret"] = bmk["close"] / bmk["close"].shift(1) - 1

# ========== Step 1: Universe ==========
def add_universe_flag(df0: pd.DataFrame) -> pd.DataFrame:
    df0 = df0.copy()

    def per_month(g):
        g = g.copy()
        base_mask = (
            g["mktcap_eom"].notna() &
            g["avg_turnover_m"].notna() &
            g["free_float"].notna() &
            (g["mktcap_eom"] > 0) &
            (g["avg_turnover_m"] > 0) &
            (g["free_float"] >= MIN_FREE_FLOAT)
        )
        g["univ_base_ok"] = base_mask

        mcap_rank = g["mktcap_eom"].rank(pct=True)
        liq_rank  = g["avg_turnover_m"].rank(pct=True)

        g["univ_mcap_ok"] = mcap_rank >= MCAP_PCT
        g["univ_liq_ok"]  = liq_rank  >= TURNOVER_PCT

        g["in_universe"] = g["univ_base_ok"] & g["univ_mcap_ok"] & g["univ_liq_ok"]
        return g

    return df0.groupby("ym", group_keys=False).apply(per_month)

df = add_universe_flag(df)
df_univ = df[df["in_universe"]].copy()

# ========== Step 2: Quality Score ==========
QUALITY_COLS_POS = ["roa_q","eps_diluted_q","curr_ratio_q","ocf_q","gross_margin_q","asset_turnover_q"]
QUALITY_COLS_NEG = ["debt_ratio_q","shares_wavg_q"]

def add_quality_score(df_univ0: pd.DataFrame) -> pd.DataFrame:
    dfq = df_univ0.copy()

    pos_cols = [c for c in QUALITY_COLS_POS if c in dfq.columns]
    neg_cols = [c for c in QUALITY_COLS_NEG if c in dfq.columns]
    all_cols = pos_cols + neg_cols

    for c in all_cols:
        dfq[c] = pd.to_numeric(dfq[c], errors="coerce")

    def per_month(g):
        g = g.copy()
        z_list = []

        for c in pos_cols:
            x = g[c]
            if x.notna().sum() < 3:
                continue
            z = (x - x.mean()) / x.std(ddof=1)
            z_list.append(z)

        for c in neg_cols:
            x = g[c]
            if x.notna().sum() < 3:
                continue
            x2 = -x
            z = (x2 - x2.mean()) / x2.std(ddof=1)
            z_list.append(z)

        if len(z_list) == 0:
            g["quality_score"] = np.nan
        else:
            zmat = np.vstack([z.values for z in z_list])
            g["quality_score"] = np.nanmean(zmat, axis=0)

        return g

    return dfq.groupby("ym", group_keys=False).apply(per_month)

df_univ_q = add_quality_score(df_univ)
df_univ_q = df_univ_q[df_univ_q["quality_score"].notna()].copy()

# ========== Step 3: Keep the top top_pct by quality ==========
def keep_top_quality(dfq: pd.DataFrame, top_pct: float) -> pd.DataFrame:
    def per_month(g):
        g = g.copy()
        g["q_pct"] = g["quality_score"].rank(pct=True, ascending=False)
        return g[g["q_pct"] <= top_pct]
    return dfq.groupby("ym", group_keys=False).apply(per_month)

df_high_q = keep_top_quality(df_univ_q, QUALITY_TOP_PCT)

# ========== Step 4: Momentum (6/9/12) + trade month ==========
df_high_q["px"] = df_high_q["close_eom"]

df_high_q["px_lag_6"]  = df_high_q.groupby("stock_id")["px"].shift(6)
df_high_q["px_lag_9"]  = df_high_q.groupby("stock_id")["px"].shift(9)
df_high_q["px_lag_12"] = df_high_q.groupby("stock_id")["px"].shift(12)

df_high_q["mom_6m"]  = df_high_q["px"] / df_high_q["px_lag_6"]  - 1
df_high_q["mom_9m"]  = df_high_q["px"] / df_high_q["px_lag_9"]  - 1
df_high_q["mom_12m"] = df_high_q["px"] / df_high_q["px_lag_12"] - 1

ym_signal = pd.PeriodIndex(df_high_q["ym"], freq="M")
df_high_q["ym_trade"] = (ym_signal + 1).astype(str)

# Return panel (monthly_ret of the trade month)
df_ret_panel = df[["stock_id","ym","monthly_ret"]].copy()
df_ret_panel["ym"] = pd.PeriodIndex(df_ret_panel["ym"].astype(str), freq="M").astype(str)

available_months = set(df_ret_panel["ym"].unique())
df_high_q = df_high_q[df_high_q["ym_trade"].isin(available_months)].copy()

# ========== TopN weights ==========
def build_topN_weights(df_signal: pd.DataFrame, signal_col: str, top_n_list, prefix: str):
    out = {}
    tmp = df_signal[["stock_id","ym_trade",signal_col]].dropna().copy()
    tmp = tmp.rename(columns={"ym_trade":"ym", signal_col:"signal"})
    tmp = tmp.sort_values(["ym","signal"], ascending=[True, False])

    for n in top_n_list:
        name = f"{prefix}_Top{n}"
        top = tmp.groupby("ym").head(n).copy()
        c = top.groupby("ym")["stock_id"].transform("count")
        top["weight"] = 1.0 / c
        out[name] = top[["ym","stock_id","weight"]].copy()

    return out

weights_6m  = build_topN_weights(df_high_q, "mom_6m",  TOP_LIST, "Q_M6")
weights_9m  = build_topN_weights(df_high_q, "mom_9m",  TOP_LIST, "Q_M9")
weights_12m = build_topN_weights(df_high_q, "mom_12m", TOP_LIST, "Q_M12")

# ========== Costs / wealth ==========
def compute_portfolio_with_cost(weights: pd.DataFrame, ret_panel: pd.DataFrame,
                                fee_buy=FEE_BUY, fee_sell=FEE_SELL, tax_sell=TAX_SELL):

    ret_panel = ret_panel.copy()
    ret_panel = ret_panel[ret_panel["monthly_ret"].notna()].copy()

    months  = sorted(weights["ym"].unique())
    tickers = sorted(weights["stock_id"].unique())

    grid = pd.MultiIndex.from_product([months, tickers], names=["ym","stock_id"]).to_frame(index=False)
    weights_full = grid.merge(weights, on=["ym","stock_id"], how="left")
    weights_full["weight"] = weights_full["weight"].fillna(0.0)

    merged = weights_full.merge(ret_panel, on=["ym","stock_id"], how="left")
    merged["weighted_ret"] = merged["weight"] * merged["monthly_ret"].fillna(0.0)
    port_ret_gross = merged.groupby("ym")["weighted_ret"].sum().sort_index()

    merged = merged.sort_values(["stock_id","ym"])
    merged["w_prev"]      = merged.groupby("stock_id")["weight"].shift(1).fillna(0.0)
    merged["buy_change"]  = np.clip(merged["weight"] - merged["w_prev"], 0, None)
    merged["sell_change"] = np.clip(merged["w_prev"] - merged["weight"], 0, None)

    buy_cost  = merged.groupby("ym")["buy_change"].sum()  * fee_buy
    sell_cost = merged.groupby("ym")["sell_change"].sum() * (fee_sell + tax_sell)

    cost_series = (buy_cost + sell_cost).reindex(port_ret_gross.index).fillna(0.0)

    net_ret = port_ret_gross - cost_series
    wealth_net = (1 + net_ret).cumprod()

    return port_ret_gross, net_ret, wealth_net

# ========== Print performance summary ==========
def performance_summary(ret: pd.Series, name: str = ""):
    r = pd.Series(ret).dropna()
    if len(r) == 0:
        print(f"【{name}】沒有資料")
        return

    months = len(r)
    total_return = (1 + r).prod() - 1
    years = months / 12.0
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else np.nan

    vol_annual  = r.std(ddof=1) * np.sqrt(12)
    mean_annual = r.mean() * 12
    sharpe = mean_annual / vol_annual if vol_annual > 0 else np.nan

    wealth = (1 + r).cumprod()
    mdd = (wealth / wealth.cummax() - 1).min()

    print(f"======== {name} ========")
    print(f"期間（月數）   : {months}")
    print(f"總報酬         : {total_return*100:>7.2f}%")
    print(f"年化報酬 (CAGR): {cagr*100:>7.2f}%")
    print(f"年化波動度     : {vol_annual*100:>7.2f}%")
    print(f"Sharpe Ratio   : {sharpe:>7.2f}")
    print(f"最大回撤 (MDD) : {mdd*100:>7.2f}%")
    print()

# ========== Run all strategies ==========
results_net_ret = {}
results_wealth  = {}

def _run_weight_dict(wdict, label):
    for name, w in wdict.items():
        _, net_ret, wealth = compute_portfolio_with_cost(w, df_ret_panel)
        results_net_ret[name] = net_ret
        results_wealth[name]  = wealth
        performance_summary(net_ret, name=f"{name}（{label}）")

_run_weight_dict(weights_6m,  "品質 × 6M 動能")
_run_weight_dict(weights_9m,  "品質 × 9M 動能")
_run_weight_dict(weights_12m, "品質 × 12M 動能")

# ========== 0050 (net of costs) ==========
w_0050 = bmk[["ym"]].copy()
w_0050["stock_id"] = "0050"
w_0050["weight"]   = 1.0

ret_0050_panel = bmk[["ym","ret"]].copy()
ret_0050_panel["ym"] = pd.PeriodIndex(ret_0050_panel["ym"].astype(str), freq="M").astype(str)
ret_0050_panel["stock_id"] = "0050"
ret_0050_panel = ret_0050_panel.rename(columns={"ret":"monthly_ret"})

_, net_ret_bmk, wealth_bmk = compute_portfolio_with_cost(w_0050, ret_0050_panel)
results_net_ret["0050"] = net_ret_bmk
results_wealth["0050"]  = wealth_bmk
performance_summary(net_ret_bmk, name="0050（含成本）")

# ========== Combine wealth table ==========
wealth_df = pd.DataFrame(results_wealth)
wealth_df.index.name = "ym"
wealth_df = wealth_df.sort_index()

# ========== Wealth charts (one each for M6 / M9 / M12, with 0050) ==========
def plot_wealth(prefix: str, title: str):
    cols = [c for c in wealth_df.columns if c.startswith(prefix)] + ["0050"]
    plot_df = wealth_df[cols].dropna(how="all")

    fig = go.Figure()
    for c in plot_df.columns:
        if c == "0050":
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[c], mode="lines", name="0050（含成本）",
                                     line=dict(color=COLOR_0050)))
        else:
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[c], mode="lines", name=c,
                                     line=dict(color=COLOR_STRATEGY)))

    fig.update_layout(
        title=title,
        xaxis_title="年月",
        yaxis_title="淨值（起始 = 1）",
        template="plotly_white",
        font=dict(family=FONT_FAMILY, size=14),
        height=560
    )
    fig.show()

COLOR_MAP = {
    "Top5":  "#5E6CE1",
    "Top10": "#E05435",
    "Top30": "#25C685",
    "Top50": "#9E65E2",
    "0050":  "#F59353",
}
def plot_momentum_group(prefix, title_text):
    """
    prefix: 'Q_M6_' / 'Q_M9_' / 'Q_M12_'
    """
    cols = [c for c in wealth_df.columns if c.startswith(prefix)] + ["0050"]
    plot_df = wealth_df[cols].dropna(how="all")

    fig = go.Figure()

    for col in plot_df.columns:
        if col == "0050":
            label = "0050（含成本）"
            color = COLOR_MAP["0050"]
            width = 3
        else:
            topn = col.split("Top")[-1]
            label = f"品質×{prefix[3:6]}_Top{topn}"
            color = COLOR_MAP.get(f"Top{topn}", "#333333")
            width = 2.5 if topn == "5" else 2

        fig.add_trace(
            go.Scatter(
                x=plot_df.index,
                y=plot_df[col],
                mode="lines",
                name=label,
                line=dict(color=color, width=width)
            )
        )

    fig.update_layout(
        title=title_text,
        xaxis_title="年月",
        yaxis_title="淨值（起始 = 1）",
        template="plotly_white",
        font=dict(family=FONT_FAMILY, size=14),
        height=560,
        legend=dict(
            orientation="v",
            x=1.02,
            y=1
        )
    )
    fig.show()
plot_momentum_group(
    prefix="Q_M6_",
    title_text="品質 × 6 個月動能（Top5/10/30/50）｜扣成本淨值 vs 0050"
)

plot_momentum_group(
    prefix="Q_M9_",
    title_text="品質 × 9 個月動能（Top5/10/30/50）｜扣成本淨值 vs 0050"
)

plot_momentum_group(
    prefix="Q_M12_",
    title_text="品質 × 12 個月動能（Top5/10/30/50）｜扣成本淨值 vs 0050"
)



print("✅ 主程式完成：已生成 results_net_ret, results_wealth, wealth_df")

# Overall ranking
# =========================================================
# Overall ranking table + Composite Score + ranking bar chart
# (0050 is ranked together with the strategies)
# Depends on: results_net_ret (computed by the main script above)
# =========================================================
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ---------- Colors (adjustable) ----------
COLOR_STRATEGY = "#2E7D6B"   # strategy color
COLOR_0050     = "#7f7f7f"   # 0050 gray

def eval_perf(ret: pd.Series):
    r = pd.Series(ret).dropna()
    if len(r) == 0:
        return np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan
    wealth = (1 + r).cumprod()
    mdd = (wealth / wealth.cummax() - 1).min()
    cagr = wealth.iloc[-1] ** (12/len(r)) - 1 if len(r) > 0 else np.nan
    vol  = r.std(ddof=1) * np.sqrt(12)
    sharpe = (r.mean()*12) / vol if (vol is not None and vol > 0) else np.nan
    total_ret = wealth.iloc[-1] - 1
    return len(r), total_ret, cagr, vol, sharpe, mdd, wealth.iloc[-1]

def parse_tags(name: str):
    # Momentum label
    if name == "0050":
        mom = "BMK"
        topn = 1
    else:
        mom = "M6" if "M6" in name else "M9" if "M9" in name else "M12" if "M12" in name else "UNK"
        topn = int(name.split("Top")[-1]) if "Top" in name else np.nan
    return mom, topn

# ---------- 1) Build the overall performance table ----------
rows = []
for name, r in results_net_ret.items():
    months, tot, cagr, vol, sharpe, mdd, wealth = eval_perf(r)
    mom, topn = parse_tags(name)
    rows.append({
        "策略名稱": name,
        "動能標籤": mom,
        "TopN": topn,
        "月份數": months,
        "總報酬": tot,
        "年化報酬(CAGR)": cagr,
        "年化波動度": vol,
        "Sharpe Ratio": sharpe,
        "最大回撤(MDD)": mdd,
        "最終淨值": wealth
    })

rank_all = pd.DataFrame(rows)

# (Optional) require at least 12 months of data to be ranked
rank_all = rank_all[rank_all["月份數"].fillna(0) >= 12].copy()

# ---------- 2) Composite Score (standardized across all strategies, including 0050) ----------
rank_all["MDD_pos"] = -rank_all["最大回撤(MDD)"]  # smaller drawdown is better -> flip sign

for col, zname in [("Sharpe Ratio","z_sharpe"), ("年化報酬(CAGR)","z_cagr"), ("MDD_pos","z_mdd")]:
    mu = rank_all[col].mean()
    sd = rank_all[col].std(ddof=1)
    rank_all[zname] = (rank_all[col] - mu) / sd if sd and sd > 0 else np.nan

rank_all["Composite_Score"] = 2*rank_all["z_sharpe"] + rank_all["z_cagr"] + rank_all["z_mdd"]

# Re-sort (0050 lands in its proper position)
rank_all = rank_all.sort_values("Composite_Score", ascending=False).reset_index(drop=True)

print("====== 整體排名（含 0050）Top 30 ======")
display(rank_all.head(30))

# ---------- 3) Plot: overall Top10 (0050 is added even if it is outside the Top10) ----------
N_SHOW = 10

topN = rank_all.head(N_SHOW).copy()
bmk  = rank_all[rank_all["策略名稱"]=="0050"].copy()

plot_df = topN.copy()
if len(bmk) > 0 and (plot_df["策略名稱"]=="0050").sum() == 0:
    plot_df = pd.concat([plot_df, bmk.head(1)], ignore_index=True)

# Sort by Composite score so 0050 sits in the right position
plot_df = plot_df.sort_values("Composite_Score", ascending=False).reset_index(drop=True)

plot_df["x_label"] = plot_df["策略名稱"].astype(str)
colors = [COLOR_0050 if s=="0050" else COLOR_STRATEGY for s in plot_df["策略名稱"]]

fig = go.Figure()
fig.add_trace(go.Bar(
    x=plot_df["x_label"],
    y=plot_df["Composite_Score"],
    marker_color=colors,
    text=plot_df["Composite_Score"].round(2),
    textposition="outside",
    hovertemplate=(
        "策略=%{customdata[0]}<br>"
        "動能=%{customdata[1]}<br>"
        "TopN=%{customdata[2]}<br>"
        "Composite=%{y:.2f}<br>"
        "Sharpe=%{customdata[3]:.2f}<br>"
        "CAGR=%{customdata[4]:.2%}<br>"
        "MDD=%{customdata[5]:.2%}"
        "<extra></extra>"
    ),
    customdata=np.stack([
        plot_df["策略名稱"].astype(str).values,
        plot_df["動能標籤"].astype(str).values,
        plot_df["TopN"].fillna(-1).astype(int).values,
        plot_df["Sharpe Ratio"].astype(float).values,
        plot_df["年化報酬(CAGR)"].astype(float).values,
        plot_df["最大回撤(MDD)"].astype(float).values,
    ], axis=1)
))

fig.update_layout(
    title=f"全體策略排名 Top{N_SHOW} + 0050｜Composite Score（0050 依分數插入排序）",
    xaxis_title="策略",
    yaxis_title="Composite Score（2×zSharpe + zCAGR + zMDD）",
    template="plotly_white",
    font=dict(family=FONT_FAMILY, size=14),
    bargap=0.35,
    height=560
)
fig.show()

# Group rankings
# =========================================================
# Group rankings + charts (0050 included)
# 1) Top5/10 group: table + chart
# 2) Top30/50 group: table + chart
# Depends on: rank_all (built in the overall ranking section above)
# =========================================================
import numpy as np
import plotly.graph_objects as go

COLOR_STRATEGY = "#2E7D6B"
COLOR_0050     = "#7f7f7f"

def show_group_table_and_plot(rank_all: pd.DataFrame, topn_keep, title_prefix, top_k_show=15):
    # --- Filter: TopN in the given set + 0050 ---
    sub = rank_all[(rank_all["TopN"].isin(topn_keep)) | (rank_all["策略名稱"] == "0050")].copy()

    # Composite_Score here is the one standardized across all strategies; not recomputed
    sub = sub.sort_values("Composite_Score", ascending=False).reset_index(drop=True)

    # --- Table: list all rows (use head() to show only the top ones) ---
    print(f"\n====== {title_prefix}｜排名表（含 0050）======")
    display(sub[["策略名稱","動能標籤","TopN","月份數","Sharpe Ratio","年化報酬(CAGR)","最大回撤(MDD)","Composite_Score"]])

    # --- Chart: show the top top_k_show, and add 0050 if it is not included ---
    plot_df = sub.head(top_k_show).copy()
    bmk = sub[sub["策略名稱"]=="0050"].head(1)
    if len(bmk) > 0 and (plot_df["策略名稱"]=="0050").sum() == 0:
        plot_df = pd.concat([plot_df, bmk], ignore_index=True)

    # Re-sort by score so 0050 sits in its proper position
    plot_df = plot_df.sort_values("Composite_Score", ascending=False).reset_index(drop=True)

    colors = [COLOR_0050 if s=="0050" else COLOR_STRATEGY for s in plot_df["策略名稱"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=plot_df["策略名稱"],
        y=plot_df["Composite_Score"],
        marker_color=colors,
        text=plot_df["Composite_Score"].round(2),
        textposition="outside",
        hovertemplate=(
            "策略=%{customdata[0]}<br>"
            "動能=%{customdata[1]}<br>"
            "TopN=%{customdata[2]}<br>"
            "Composite=%{y:.2f}<br>"
            "Sharpe=%{customdata[3]:.2f}<br>"
            "CAGR=%{customdata[4]:.2%}<br>"
            "MDD=%{customdata[5]:.2%}"
            "<extra></extra>"
        ),
        customdata=np.stack([
            plot_df["策略名稱"].astype(str).values,
            plot_df["動能標籤"].astype(str).values,
            plot_df["TopN"].fillna(-1).astype(int).values,
            plot_df["Sharpe Ratio"].astype(float).values,
            plot_df["年化報酬(CAGR)"].astype(float).values,
            plot_df["最大回撤(MDD)"].astype(float).values,
        ], axis=1)
    ))

    fig.update_layout(
        title=f"{title_prefix}（含 0050）｜Composite Score",
        xaxis_title="策略",
        yaxis_title="Composite Score（全體標準化）",
        template="plotly_white",
        font=dict(family=FONT_FAMILY, size=14),
        bargap=0.35,
        height=560
    )
    fig.show()

# =========================
# 1) Top5/10 + 0050
# =========================
show_group_table_and_plot(
    rank_all=rank_all,
    topn_keep=[5, 10],
    title_prefix="Top5/10 單獨排名",
    top_k_show=15
)

# =========================
# 2) Top30/50 + 0050
# =========================
show_group_table_and_plot(
    rank_all=rank_all,
    topn_keep=[30, 50],
    title_prefix="Top30/50 單獨排名",
    top_k_show=15
)

# =========================================================
# Fix: bmk was reused for the ranking table above
# -> reload the 0050 price table and store it in bmk_price
# =========================================================
bmk_price = pd.read_csv(PATH_0050).copy()

# (Optional) to keep the ranking table, save it under another name
# rank_df = bmk.copy()   # <- uncomment only if bmk currently holds the ranking table

# =========================================================
# Step 0: standardize 0050 (bmk) columns (ensure ym / close / monthly_ret exist)
# =========================================================
bmk = bmk_price.copy()


# --- 0-1) Find the date column (accepts several common column names) ---
date_candidates = ["ym", "date", "Date", "年月", "月份", "month", "Month", "month_end_date", "month_end"]
date_col = None
for c in date_candidates:
    if c in bmk.columns:
        date_col = c
        break

if date_col is None:
    raise ValueError(f"bmk 找不到日期欄位。現有欄位：{bmk.columns.tolist()}")

# --- 0-2) Convert the date column to standard ym = 'YYYY-MM' ---
if date_col != "ym":
    bmk["ym"] = bmk[date_col]
else:
    bmk["ym"] = bmk["ym"]

# Accepts '2005-01', '2005/01' and '2005-01-31'
bmk["ym"] = pd.to_datetime(bmk["ym"].astype(str), errors="coerce")
if bmk["ym"].isna().all():
    # If ym is 'YYYY-MM' without a day, to_datetime may fail; fall back to PeriodIndex
    bmk["ym"] = pd.PeriodIndex(bmk[date_col].astype(str), freq="M").to_timestamp()

bmk["ym"] = bmk["ym"].dt.to_period("M").astype(str)

# --- 0-3) Find the close price column (accepts several common column names) ---
close_candidates = ["close", "Close", "close_eom", "收盤價", "price", "Price"]
close_col = None
for c in close_candidates:
    if c in bmk.columns:
        close_col = c
        break

if close_col is None:
    raise ValueError(f"bmk 找不到收盤價欄位。現有欄位：{bmk.columns.tolist()}")

bmk["close"] = pd.to_numeric(bmk[close_col], errors="coerce")

# --- 0-4) Sort, then compute monthly_ret (reuse it if it already exists) ---
bmk = bmk.sort_values("ym").reset_index(drop=True)

if "monthly_ret" in bmk.columns:
    bmk["monthly_ret"] = pd.to_numeric(bmk["monthly_ret"], errors="coerce")
elif "ret" in bmk.columns:
    bmk["monthly_ret"] = pd.to_numeric(bmk["ret"], errors="coerce")
else:
    bmk["monthly_ret"] = bmk["close"] / bmk["close"].shift(1) - 1

# --- 0-5) Build the standard panel (used by everything below) ---
bmk_ret_panel = bmk[["ym", "monthly_ret"]].dropna().copy()
bmk_ret_panel["stock_id"] = "0050"

print("✅ bmk_ret_panel ready:", bmk_ret_panel.shape)
display(bmk_ret_panel.head())

# =========================================================
# Step A: 0050 -> ret_panel (columns must be ym / stock_id / monthly_ret)
# =========================================================
bmk = bmk_price.copy()

# 1) Find the date column (common names: ym / date / year-month)
date_col_candidates = ["ym", "date", "年月", "month"]
date_col = next((c for c in date_col_candidates if c in bmk.columns), None)
if date_col is None:
    raise ValueError(f"0050 價格表找不到日期欄位。現有欄位：{bmk.columns.tolist()}")

# 2) Find the close price column (common names: close / price)
close_col_candidates = ["close", "Close", "收盤價", "price"]
close_col = next((c for c in close_col_candidates if c in bmk.columns), None)
if close_col is None:
    raise ValueError(f"0050 價格表找不到收盤價欄位。現有欄位：{bmk.columns.tolist()}")

# 3) Convert to ym = "YYYY-MM"
bmk[date_col] = pd.to_datetime(bmk[date_col], errors="coerce")
bmk = bmk[bmk[date_col].notna()].copy()
bmk["ym"] = bmk[date_col].dt.to_period("M").astype(str)

# 4) Convert close to numeric + compute monthly returns
bmk["close"] = pd.to_numeric(bmk[close_col], errors="coerce")
bmk = bmk.sort_values("ym")
bmk["monthly_ret"] = bmk["close"] / bmk["close"].shift(1) - 1

# 5) Output the standard panel
ret_0050_panel = bmk[["ym", "monthly_ret"]].copy()
ret_0050_panel["stock_id"] = "0050"
ret_0050_panel = ret_0050_panel.dropna().reset_index(drop=True)

print("✅ ret_0050_panel OK:", ret_0050_panel.shape)
display(ret_0050_panel.head())

# =========================================================
# Step B: add 0050 to the backtest results (net of costs)
# -> results_net_ret / results_wealth
# =========================================================
w_0050 = ret_0050_panel[["ym"]].copy()
w_0050["stock_id"] = "0050"
w_0050["weight"] = 1.0

gross_bmk, net_ret_bmk, wealth_bmk = compute_portfolio_with_cost(w_0050, ret_0050_panel)

results_net_ret["0050"] = net_ret_bmk
results_wealth["0050"]  = wealth_bmk

performance_summary(net_ret_bmk, name="0050（含成本）")

import itertools
import numpy as np
import pandas as pd

# =========================================================
# 1) Parameter grid (edit here)
# =========================================================
GRID_PARAMS = {
    "MIN_FREE_FLOAT":   [30, 40, 50],
    "MCAP_PCT":         [0.15,0.20, 0.30],
    "TURNOVER_PCT":     [0.20, 0.30,0.50],
    "QUALITY_TOP_PCT":  [0.15,0.20, 0.30],
}
MOMENTUM_WINDOWS = [6, 9, 12]
TOP_LIST = [5, 10]
COMP_WEIGHTS = {"Sharpe": 2.0, "CAGR": 1.0, "MDD": 1.0}

# =========================================================
# 2) Helpers: performance + Composite
# =========================================================
def eval_perf(ret: pd.Series):
    r = ret.dropna()
    if len(r) == 0:
        return None
    wealth = (1 + r).cumprod()
    mdd = (wealth / wealth.cummax() - 1).min()
    cagr = wealth.iloc[-1] ** (12/len(r)) - 1 if len(r) > 0 else np.nan
    vol  = r.std(ddof=1) * np.sqrt(12)
    sharpe = (r.mean()*12) / vol if vol > 0 else np.nan
    return {
        "月份數": len(r),
        "總報酬": wealth.iloc[-1] - 1,
        "年化報酬(CAGR)": cagr,
        "年化波動度": vol,
        "Sharpe Ratio": sharpe,
        "最大回撤(MDD)": mdd,
        "最終淨值": wealth.iloc[-1]
    }

def add_composite(df_rank: pd.DataFrame):
    df_rank = df_rank.copy()
    df_rank["MDD_pos"] = -df_rank["最大回撤(MDD)"]

    for col, zname in [("Sharpe Ratio","z_sharpe"), ("年化報酬(CAGR)","z_cagr"), ("MDD_pos","z_mdd")]:
        mu = df_rank[col].mean()
        sd = df_rank[col].std(ddof=1)
        df_rank[zname] = (df_rank[col] - mu) / sd if sd and sd > 0 else 0.0

    df_rank["Composite_Score"] = (
        COMP_WEIGHTS["Sharpe"] * df_rank["z_sharpe"] +
        COMP_WEIGHTS["CAGR"]   * df_rank["z_cagr"] +
        COMP_WEIGHTS["MDD"]    * df_rank["z_mdd"]
    )
    return df_rank

# =========================================================
# 3) One parameter set: run all strategies for it (name -> net_ret)
# =========================================================
def run_one_setting(ff, mcap, to, qtop):
    global MIN_FREE_FLOAT, MCAP_PCT, TURNOVER_PCT, QUALITY_TOP_PCT
    MIN_FREE_FLOAT, MCAP_PCT, TURNOVER_PCT, QUALITY_TOP_PCT = ff, mcap, to, qtop

    _df = add_universe_flag(df)
    df_univ = _df[_df["in_universe"]].copy()

    df_univ_q = add_quality_score(df_univ)
    df_univ_q = df_univ_q[df_univ_q["quality_score"].notna()].copy()

    df_high_q = keep_top_quality(df_univ_q, QUALITY_TOP_PCT)
    df_high_q = df_high_q.sort_values(["stock_id","ym"]).copy()

    df_high_q["px"] = df_high_q["close_eom"]
    for w in MOMENTUM_WINDOWS:
        df_high_q[f"px_lag_{w}"] = df_high_q.groupby("stock_id")["px"].shift(w)
        df_high_q[f"mom_{w}m"] = df_high_q["px"] / df_high_q[f"px_lag_{w}"] - 1

    ym_signal_period = pd.PeriodIndex(df_high_q["ym"], freq="M")
    df_high_q["ym_trade"] = (ym_signal_period + 1).astype(str)

    available_months = set(df_ret_panel["ym"].unique())
    df_high_q = df_high_q[df_high_q["ym_trade"].isin(available_months)].copy()

    out = {}
    for w in MOMENTUM_WINDOWS:
        prefix = f"Q_M{w}"
        weights = build_topN_weights(df_high_q, f"mom_{w}m", TOP_LIST, prefix=prefix)
        for strat_name, wdf in weights.items():
            _, net_ret, _ = compute_portfolio_with_cost(wdf, df_ret_panel)
            out[strat_name] = net_ret
    return out

# =========================================================
# 4) Run the full grid and build one ranking table
#    across parameter sets x strategies
# =========================================================
grid_list = list(itertools.product(
    GRID_PARAMS["MIN_FREE_FLOAT"],
    GRID_PARAMS["MCAP_PCT"],
    GRID_PARAMS["TURNOVER_PCT"],
    GRID_PARAMS["QUALITY_TOP_PCT"],
))

rows = []

# ---- 0050: added once (not repeated for each grid point)
bmk_ret = None
if "results_net_ret" in globals() and "0050" in results_net_ret:
    bmk_ret = results_net_ret["0050"]
elif "net_ret_bmk" in globals():
    bmk_ret = net_ret_bmk

if bmk_ret is not None:
    perf = eval_perf(bmk_ret)
    row = {
        "策略名稱": "0050",
        "動能標籤": "BMK",
        "TopN": 1,
        "MIN_FREE_FLOAT": np.nan,
        "MCAP_PCT": np.nan,
        "TURNOVER_PCT": np.nan,
        "QUALITY_TOP_PCT": np.nan,
    }
    row.update(perf)
    rows.append(row)

# ---- All strategies in the grid
for (ff, mcap, to, qtop) in grid_list:
    res = run_one_setting(ff, mcap, to, qtop)

    for name, r in res.items():
        perf = eval_perf(r)
        if perf is None:
            continue

        topn = int(name.split("Top")[-1]) if "Top" in name else 1
        mom = "M6" if "M6" in name else "M9" if "M9" in name else "M12" if "M12" in name else "UNK"

        rows.append({
            "策略名稱": name,
            "動能標籤": mom,
            "TopN": topn,
            "MIN_FREE_FLOAT": ff,
            "MCAP_PCT": mcap,
            "TURNOVER_PCT": to,
            "QUALITY_TOP_PCT": qtop,
            **perf
        })

rank_grid = pd.DataFrame(rows)

# Composite + ranking
rank_grid = add_composite(rank_grid)
rank_grid = rank_grid.sort_values("Composite_Score", ascending=False).reset_index(drop=True)

print("✅ 不同參數 × 不同策略｜總排行表（含0050）")
display(rank_grid.head(50))

# Charts
import plotly.graph_objects as go
import numpy as np
import pandas as pd

FONT_FAMILY = "Microsoft JhengHei, Noto Sans CJK TC, PingFang TC"
COLOR_MAP = {
    "M6":   "#1f77b4",   # blue
    "M9":   "#ff7f0e",   # orange
    "M12":  "#2ca02c",   # green
    "0050": "#7f7f7f"    # gray
}

def _color_row(r):
    if r["策略名稱"] == "0050":
        return COLOR_MAP["0050"]
    return COLOR_MAP.get(r["動能標籤"], "#2E7D6B")

def plot_overall_top10_with_0050(rank_df: pd.DataFrame, top_k=10, title="全體策略排名 Top10 + 0050｜Composite Score"):
    df = rank_df.copy()

    topk = df[df["策略名稱"]!="0050"].head(top_k)
    bmk  = df[df["策略名稱"]=="0050"].head(1)
    plot_df = pd.concat([topk, bmk], ignore_index=True)

    # Re-sort by Composite so 0050 lands in the right position
    plot_df = plot_df.sort_values("Composite_Score", ascending=False).reset_index(drop=True)

    # x-axis labels (avoid duplicate names overlapping)
    plot_df["x_label"] = plot_df.apply(
        lambda r: "0050" if r["策略名稱"]=="0050"
        else f"{r['策略名稱']} | FF{r.get('MIN_FREE_FLOAT','')}_MC{r.get('MCAP_PCT','')}_TO{r.get('TURNOVER_PCT','')}_Q{r.get('QUALITY_TOP_PCT','')}",
        axis=1
    )

    colors = plot_df.apply(_color_row, axis=1).tolist()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=plot_df["x_label"],
        y=plot_df["Composite_Score"],
        marker_color=colors,
        text=plot_df["Composite_Score"].round(2),
        textposition="outside",
        hovertemplate=(
            "策略=%{customdata[0]}<br>"
            "動能=%{customdata[1]} | TopN=%{customdata[2]}<br>"
            "Composite=%{y:.2f}<br>"
            "Sharpe=%{customdata[3]:.2f}<br>"
            "CAGR=%{customdata[4]:.2%}<br>"
            "MDD=%{customdata[5]:.2%}"
            "<extra></extra>"
        ),
        customdata=np.stack([
            plot_df["策略名稱"].astype(str).values,
            plot_df["動能標籤"].astype(str).values,
            plot_df["TopN"].astype(int).values,
            plot_df["Sharpe Ratio"].astype(float).values,
            plot_df["年化報酬(CAGR)"].astype(float).values,
            plot_df["最大回撤(MDD)"].astype(float).values,
        ], axis=1)
    ))
    max_score = plot_df["Composite_Score"].max()
    fig.update_layout(
        title=title,
        xaxis_title="策略（含參數標籤）",
        yaxis_title="Composite Score",
        yaxis=dict(range=[0, max_score * 1.15]),
        template="plotly_white",
        font=dict(family=FONT_FAMILY, size=13),
        bargap=0.35,
        height=560
    )
    fig.show()

plot_overall_top10_with_0050(rank_grid, top_k=10)

# Sub-periods
# Define the periods
# Sub-period check: does the strategy win in only one period?
# A robust strategy should beat the market across several periods.
# ==========================================================
# Sub-period performance analysis
# ==========================================================

def subperiod_performance(net_ret: pd.Series, periods: dict):
    """
    net_ret : monthly net returns (index = ym)
    periods : {"2005-2010": ("2005-01","2010-12"), ...}
    Returns: sub-period performance table
    """
    rows = []

    for name, (start, end) in periods.items():
        r = net_ret.loc[start:end].dropna()
        if len(r) < 24:  # at least 2 years
            continue

        months = len(r)
        total_return = (1 + r).prod() - 1
        years = months / 12
        cagr = (1 + total_return) ** (1 / years) - 1

        vol = r.std(ddof=1) * np.sqrt(12)
        sharpe = (r.mean() * 12) / vol if vol > 0 else np.nan

        wealth = (1 + r).cumprod()
        mdd = (wealth / wealth.cummax() - 1).min()

        rows.append({
            "子期間": name,
            "月份數": months,
            "CAGR": cagr,
            "Sharpe": sharpe,
            "MDD": mdd
        })

    return pd.DataFrame(rows)


SUBPERIODS = {
    "2005–2009": ("2005-01", "2009-12"),
    "2010–2014": ("2010-01", "2014-12"),
    "2015–2019": ("2015-01", "2019-12"),
    "2020–2025": ("2020-01", "2025-10")
}
w_base = weights_9m["Q_M9_Top5"]
_, net_ret_base, _ = compute_portfolio_with_cost(w_base, df_ret_panel)

sub_base = subperiod_performance(net_ret_base, SUBPERIODS)
display(sub_base)

# Parameters used in the sub-period analysis
STRATEGY_PARAMS = {
    "Momentum": "9M",
    "TopN": 5,
    "MIN_FREE_FLOAT": MIN_FREE_FLOAT,
    "MCAP_PCT": MCAP_PCT,
    "TURNOVER_PCT": TURNOVER_PCT,
    "QUALITY_TOP_PCT": QUALITY_TOP_PCT,
    "Fee": f"{FEE_BUY}/{FEE_SELL}/{TAX_SELL}"
}

STRATEGY_PARAMS

# Latest period (last trade month): Top5 holdings with momentum / quality
# =========================================================
# Output: latest Top5 holdings of the best strategy, Q_M9_Top5
# Source: df_high_q (with ym, ym_trade, mom_9m and quality_score)
# =========================================================

# 1) Find the latest trade month
latest_trade_ym = sorted(df_high_q["ym_trade"].unique())[-1]
print("最新交易月(ym_trade) =", latest_trade_ym)

# 2) Get the Top5 entered in that month (sorted by mom_9m)
top5_latest = (
    df_high_q[df_high_q["ym_trade"] == latest_trade_ym]
    .dropna(subset=["mom_9m", "quality_score"])
    .sort_values("mom_9m", ascending=False)
    .head(5)
    .copy()
)

# 3) Add equal weights (still equal weight if there are fewer than 5 stocks)
top5_latest["weight"] = 1.0 / len(top5_latest)

# 4) Columns to show (adjustable)
cols_show = [c for c in [
    "ym", "ym_trade", "stock_id",
    "mom_9m", "quality_score",
    "mktcap_eom", "avg_turnover_m", "free_float",
    "weight"
] if c in top5_latest.columns]

display(top5_latest[cols_show])

# Full period: Top5 holdings for every trade month
# =========================================================
# Output: Q_M9_Top5 holdings for every period
# Source: weights_9m["Q_M9_Top5"] (the strategy's actual weights)
# =========================================================

w_m9_top5 = weights_9m["Q_M9_Top5"].copy()

# Collapse each month's Top5 stocks into one list column
holdings_all = (
    w_m9_top5.sort_values(["ym", "weight"], ascending=[True, False])
    .groupby("ym")["stock_id"]
    .apply(list)
    .reset_index()
    .rename(columns={"ym": "交易月(ym_trade)", "stock_id": "Top5持股"})
)

display(holdings_all.head(10))
print("總交易月數 =", len(holdings_all))

top5_latest[cols_show].to_csv("Q_M9_Top5_latest_holdings.csv", index=False, encoding="utf-8-sig")
holdings_all.to_csv("Q_M9_Top5_all_holdings_by_month.csv", index=False, encoding="utf-8-sig")

print("✅ 已輸出：Q_M9_Top5_latest_holdings.csv")
print("✅ 已輸出：Q_M9_Top5_all_holdings_by_month.csv")

import pandas as pd

def first_trade_month_by_subperiod(holdings_all: pd.DataFrame,
                                  subperiods: dict,
                                  trade_col: str = "交易月(ym_trade)") -> pd.DataFrame:
    """
    Find the first tradable month in each sub-period.
    - holdings_all: monthly holdings table (one row per month); must contain trade_col
      e.g. the holdings_all table built above
    - subperiods: {"2005–2009": ("2005-01","2009-12"), ...}
    - trade_col: name of the trade-month column (default: the one used in holdings_all)

    Returns: sub-period, start, end, first tradable month,
             and number of tradable months in the sub-period
    """
    if trade_col not in holdings_all.columns:
        raise ValueError(f"holdings_all 找不到 {trade_col} 欄位，現在欄位：{holdings_all.columns.tolist()}")

    df = holdings_all.copy()
    df[trade_col] = pd.PeriodIndex(df[trade_col].astype(str), freq="M").astype(str)

    rows = []
    for name, (start, end) in subperiods.items():
        start = pd.Period(start, "M").strftime("%Y-%m")
        end   = pd.Period(end,   "M").strftime("%Y-%m")

        mask = (df[trade_col] >= start) & (df[trade_col] <= end)
        months_in = sorted(df.loc[mask, trade_col].unique())

        rows.append({
            "子期間": name,
            "起始": start,
            "結束": end,
            "第一個可交易月": months_in[0] if len(months_in) > 0 else None,
            "可交易月數": len(months_in)
        })

    return pd.DataFrame(rows)


# ====== Usage ======
SUBPERIODS = {
    "2005–2009": ("2005-01", "2009-12"),
    "2010–2014": ("2010-01", "2014-12"),
    "2015–2019": ("2015-01", "2019-12"),
    "2020–2025": ("2020-01", "2025-10"),
}

# holdings_all was built above (it has the trade-month column)
first_trade_table = first_trade_month_by_subperiod(holdings_all, SUBPERIODS)
display(first_trade_table)
