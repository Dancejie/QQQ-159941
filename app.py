import streamlit as st
import yfinance as yf
import baostock as bs
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

st.title("159941 vs QQQ 溢价情绪指标（在线版）")

# 添加加载状态
with st.spinner("正在下载数据..."):
    df_cn = None
    df_us = None
    
    # 尝试使用 baostock 下载中国ETF数据
    try:
        bs.login()
        
        # baostock ETF代码格式尝试：sz.159941 或 sh.159941
        # 如果ETF不支持，尝试查询股票基本信息找到正确代码
        code_formats = ["sz.159941", "sh.159941"]
        
        for code_format in code_formats:
            rs_cn = bs.query_history_k_data_plus(
                code_format,
                "date,close",
                start_date="2020-01-01",
                end_date=datetime.today().strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="3"
            )
            
            if rs_cn.error_code == '0':
                data_list = []
                while (rs_cn.error_code == '0') and rs_cn.next():
                    data_list.append(rs_cn.get_row_data())
                
                if data_list:
                    df_cn = pd.DataFrame(data_list, columns=rs_cn.fields)
                    df_cn['date'] = pd.to_datetime(df_cn['date'])
                    df_cn['close'] = df_cn['close'].astype(float)
                    df_cn.set_index('date', inplace=True)
                    df_cn = df_cn['close']
                    st.success(f"✅ 使用 baostock 成功下载 159941 数据 ({len(df_cn)} 条)")
                    break
        
        bs.logout()
        
    except Exception as e:
        try:
            bs.logout()
        except Exception:
            pass
        st.warning(f"⚠️ baostock 下载失败: {str(e)}，尝试使用 yfinance...")
    
    # 如果 baostock 失败，回退到 yfinance
    if df_cn is None or df_cn.empty:
        try:
            # yfinance 尝试不同的代码格式
            yf_formats = ["159941.SZ", "159941.SS", "159941"]
            for yf_format in yf_formats:
                try:
                    df_cn = yf.download(yf_format, start="2020-01-01", progress=False)
                    if not df_cn.empty:
                        # yfinance 返回的列可能是多级索引，需要处理
                        if isinstance(df_cn.columns, pd.MultiIndex):
                            df_cn = df_cn['Close']
                            # 如果是多级索引，取第一列（Series）
                            if isinstance(df_cn, pd.DataFrame):
                                df_cn = df_cn.iloc[:, 0]
                        else:
                            df_cn = df_cn['Close']
                        # 确保是 Series 类型
                        if isinstance(df_cn, pd.DataFrame):
                            df_cn = df_cn.iloc[:, 0]
                        st.success(f"✅ 使用 yfinance 成功下载 159941 数据 ({len(df_cn)} 条)")
                        break
                except Exception:
                    continue
            
            if df_cn is None or df_cn.empty:
                st.error("无法下载159941.SZ数据，请检查股票代码或网络连接")
                st.stop()
        except Exception as e:
            st.error(f"下载159941数据时出错: {str(e)}")
            st.stop()
    
    # 下载美国ETF数据 (QQQ)
    try:
        df_us = yf.download("QQQ", start="2020-01-01", progress=False)
        if df_us.empty:
            st.error("无法下载QQQ数据，请检查网络连接")
            st.stop()
        df_us = df_us['Close']
        st.success(f"✅ 成功下载 QQQ 数据 ({len(df_us)} 条)")
    except Exception as e:
        st.error(f"下载QQQ数据时出错: {str(e)}")
        st.stop()

# 合并数据
df = pd.concat([df_cn, df_us], axis=1).dropna()
if df.empty:
    st.error("合并后的数据为空，请检查数据源")
    st.stop()

df.columns = ["159941", "QQQ"]

# 计算溢价率：由于159941和QQQ单位不同，使用标准化后的相对表现
# 方法1：使用涨跌幅差异作为溢价率
df["159941_return"] = df["159941"].pct_change().fillna(0) * 100
df["QQQ_return"] = df["QQQ"].pct_change().fillna(0) * 100
df["premium"] = df["159941_return"] - df["QQQ_return"]

# 方法2：如果方法1不合适，使用价格比率的滚动偏离度
# 计算价格比率（虽然单位不同，但可以看相对变化）
df["price_ratio"] = df["159941"] / df["QQQ"]
df["ratio_ma"] = df["price_ratio"].rolling(window=60, min_periods=1).mean()
df["premium_alt"] = ((df["price_ratio"] / df["ratio_ma"]) - 1) * 100

# 如果方法1的溢价率范围合理，使用方法1；否则使用方法2
if df["premium"].abs().max() < 50:  # 如果涨跌幅差异在合理范围
    pass  # 使用方法1
else:
    df["premium"] = df["premium_alt"]  # 使用方法2

df["premium_high"] = df["premium"].where(df["premium"] > 8)
df["premium_low"] = df["premium"].where(df["premium"] < 1)

# 显示数据统计
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("159941 当前价格", f"{df['159941'].iloc[-1]:.4f}", f"{df['159941'].iloc[-1] - df['159941'].iloc[-2]:.4f}")
with col2:
    st.metric("QQQ 当前价格", f"${df['QQQ'].iloc[-1]:.2f}", f"${df['QQQ'].iloc[-1] - df['QQQ'].iloc[-2]:.2f}")
with col3:
    st.metric("当前溢价率", f"{df['premium'].iloc[-1]:.2f}%", f"{df['premium'].iloc[-1] - df['premium'].iloc[-2]:.2f}%")

# 创建交互式图表
fig = make_subplots(
    rows=2, cols=1,
    subplot_titles=("159941 vs QQQ 价格对比", "溢价率趋势"),
    vertical_spacing=0.12,
    row_heights=[0.5, 0.5],
    specs=[[{"secondary_y": True}], [{}]]
)

# 第一个子图：价格对比（使用双Y轴）
fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["159941"],
        name="159941",
        mode="lines",
        line=dict(color="#1f77b4", width=2),
        hovertemplate="<b>159941</b><br>" +
                      "日期: %{x|%Y-%m-%d}<br>" +
                      "价格: %{y:.4f}<br>" +
                      "<extra></extra>"
    ),
    row=1, col=1, secondary_y=False
)

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["QQQ"],
        name="QQQ",
        mode="lines",
        line=dict(color="#ff7f0e", width=2),
        hovertemplate="<b>QQQ</b><br>" +
                      "日期: %{x|%Y-%m-%d}<br>" +
                      "价格: $%{y:.2f}<br>" +
                      "<extra></extra>"
    ),
    row=1, col=1, secondary_y=True
)

# 第二个子图：溢价率
fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["premium"],
        name="溢价率",
        mode="lines",
        line=dict(color="#2ca02c", width=2),
        hovertemplate="<b>溢价率</b><br>" +
                      "日期: %{x|%Y-%m-%d}<br>" +
                      "溢价率: %{y:.2f}%<br>" +
                      "159941: %{customdata[0]:.4f}<br>" +
                      "QQQ: $%{customdata[1]:.2f}<br>" +
                      "<extra></extra>",
        customdata=df[["159941", "QQQ"]].values
    ),
    row=2, col=1
)

# 添加高溢价点
premium_high_data = df[df["premium_high"].notna()]
if not premium_high_data.empty:
    fig.add_trace(
        go.Scatter(
            x=premium_high_data.index,
            y=premium_high_data["premium_high"],
            name="高溢价 (>8%)",
            mode="markers",
            marker=dict(color="red", size=6, symbol="circle"),
            hovertemplate="<b>高溢价点</b><br>" +
                          "日期: %{x|%Y-%m-%d}<br>" +
                          "溢价率: %{y:.2f}%<br>" +
                          "<extra></extra>",
            showlegend=True
        ),
        row=2, col=1
    )

# 添加低溢价点
premium_low_data = df[df["premium_low"].notna()]
if not premium_low_data.empty:
    fig.add_trace(
        go.Scatter(
            x=premium_low_data.index,
            y=premium_low_data["premium_low"],
            name="低溢价 (<1%)",
            mode="markers",
            marker=dict(color="blue", size=6, symbol="circle"),
            hovertemplate="<b>低溢价点</b><br>" +
                          "日期: %{x|%Y-%m-%d}<br>" +
                          "溢价率: %{y:.2f}%<br>" +
                          "<extra></extra>",
            showlegend=True
        ),
        row=2, col=1
    )

# 添加参考线
fig.add_hline(y=8, line_dash="dash", line_color="red", opacity=0.5, 
              annotation_text="8%", annotation_position="right",
              row=2, col=1)
fig.add_hline(y=1, line_dash="dash", line_color="blue", opacity=0.5,
              annotation_text="1%", annotation_position="right",
              row=2, col=1)

# 更新布局和Y轴标签
fig.update_xaxes(title_text="日期", row=2, col=1)
fig.update_xaxes(title_text="日期", row=1, col=1)

# 左Y轴：159941价格（人民币）
fig.update_yaxes(
    title_text="159941 价格 (人民币)", 
    row=1, col=1, 
    secondary_y=False,
    side="left",
    showgrid=True
)

# 右Y轴：QQQ价格（美元）
fig.update_yaxes(
    title_text="QQQ 价格 (美元)", 
    row=1, col=1, 
    secondary_y=True,
    side="right",
    showgrid=False
)

# 溢价率Y轴
fig.update_yaxes(
    title_text="溢价率 (%)", 
    row=2, col=1
)

fig.update_layout(
    height=800,
    hovermode="x unified",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        bgcolor="rgba(255,255,255,0.8)"
    ),
    template="plotly_white",
    font=dict(family="Arial, Microsoft YaHei, sans-serif", size=12),
    title=dict(
        text="159941 vs QQQ 溢价情绪指标分析",
        x=0.5,
        xanchor="center",
        font=dict(size=16)
    )
)

st.plotly_chart(fig, use_container_width=True)
