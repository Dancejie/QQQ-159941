import streamlit as st
import yfinance as yf
import baostock as bs
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

st.title("159941 vs QQQ 溢价情绪指标（在线版）")

# 添加参数设置
st.sidebar.header("参数设置")
st.sidebar.markdown("""
**溢价率计算公式：**  
溢价率 = (ETF实时价格 - ETF净值) ÷ ETF净值 × 100%

**说明：**  
由于无法直接获取159941的净值数据，本应用使用价格比率的长期均值作为"理论净值"的代理来计算溢价率。
""")
window_size = st.sidebar.slider("短期基准窗口（交易日）", min_value=10, max_value=120, value=30, step=5,
                                help="用于计算溢价率基准的滚动窗口大小。默认使用250日长期均值，此参数仅在长期数据不足时使用。")

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

# 尝试获取159941的真实净值数据
df_nav = None
try:
    import akshare as ak
    # 使用akshare获取ETF净值数据
    # 获取日期范围（转换为akshare需要的格式）
    start_date = df.index[0].strftime("%Y%m%d")
    end_date = df.index[-1].strftime("%Y%m%d")
    
    # 使用fund_etf_fund_info_em获取净值数据
    df_nav = ak.fund_etf_fund_info_em(fund="159941", start_date=start_date, end_date=end_date)
    
    if not df_nav.empty and '净值日期' in df_nav.columns and '单位净值' in df_nav.columns:
        # 转换日期和净值
        df_nav['净值日期'] = pd.to_datetime(df_nav['净值日期'])
        df_nav.set_index('净值日期', inplace=True)
        df_nav['nav_value'] = pd.to_numeric(df_nav['单位净值'], errors='coerce')
        df_nav = df_nav[['nav_value']].dropna()
        
        if not df_nav.empty:
            st.success(f"✅ 成功获取159941净值数据 ({len(df_nav)} 条)")
        else:
            st.warning("⚠️ 净值数据为空，将使用估算方法")
            df_nav = None
    else:
        st.warning("⚠️ 净值数据格式不正确，将使用估算方法")
        df_nav = None
except ImportError:
    st.warning("⚠️ akshare未安装，无法获取净值数据，将使用估算方法")
except Exception as e:
    st.warning(f"⚠️ 获取净值数据失败: {str(e)}，将使用估算方法")
    df_nav = None

# 计算溢价率：159941是广发纳斯达克100ETF（纳指ETF）
# 溢价率 = (ETF实时价格 - ETF净值) ÷ ETF净值 × 100%

if df_nav is not None and not df_nav.empty:
    # 使用真实净值数据计算溢价率
    # 合并价格和净值数据
    df_with_nav = pd.merge(df[['159941']], df_nav, left_index=True, right_index=True, how='inner')
    
    if not df_with_nav.empty:
        # 使用真实净值计算溢价率
        df_with_nav["premium"] = ((df_with_nav["159941"] - df_with_nav["nav_value"]) / df_with_nav["nav_value"]) * 100
        
        # 将溢价率和净值合并回主数据框
        df = df.merge(df_with_nav[['premium', 'nav_value']], left_index=True, right_index=True, how='left')
        # 前向填充和后向填充缺失的溢价率
        df["premium"] = df["premium"].ffill().bfill()
        
        st.info("📊 使用真实净值数据计算溢价率")
    else:
        st.warning("⚠️ 净值数据与价格数据无法匹配，将使用估算方法")
        df_nav = None

# 如果无法获取净值数据，使用价格比率的长期均值作为"理论净值"的代理
# 检查是否已经成功使用真实净值计算了溢价率
use_real_nav = ('premium' in df.columns and df['premium'].notna().any() and 
                'nav_value' in df.columns and df['nav_value'].notna().any())

if not use_real_nav:
    # 价格比率 = 159941价格 / QQQ价格
    # 注意：159941是人民币计价，QQQ是美元计价，但都跟踪纳斯达克100指数
    df["price_ratio"] = df["159941"] / df["QQQ"]

    # 使用长期滚动均值作为"理论净值"的代理
    # 优先使用早期历史数据（2020-2023）建立基准，因为那时溢价率可能较低
    # 如果数据不足，则使用全部历史数据

    # 尝试获取早期数据建立基准
    try:
        # 下载早期数据（2020-2023年）
        df_cn_early = yf.download("159941.SZ", start="2020-01-01", end="2024-01-01", progress=False)
        df_us_early = yf.download("QQQ", start="2020-01-01", end="2024-01-01", progress=False)
        
        if not df_cn_early.empty and not df_us_early.empty:
            if isinstance(df_cn_early.columns, pd.MultiIndex):
                close_cn_early = df_cn_early['Close'].iloc[:, 0]
            else:
                close_cn_early = df_cn_early['Close']
            close_us_early = df_us_early['Close']
            
            df_early = pd.concat([close_cn_early, close_us_early], axis=1).dropna()
            if not df_early.empty:
                df_early.columns = ["159941", "QQQ"]
                df_early["price_ratio"] = df_early["159941"] / df_early["QQQ"]
                # 使用早期数据的中位数作为基准（更稳健）
                baseline_value = df_early["price_ratio"].median()
                st.sidebar.info("✓ 使用早期数据（2020-2023）建立基准")
            else:
                baseline_value = df["price_ratio"].median()
        else:
            baseline_value = df["price_ratio"].median()
    except Exception:
        # 如果获取早期数据失败，使用当前数据的中位数
        baseline_value = df["price_ratio"].median()

    # 使用滚动窗口计算基准
    long_window = min(250, len(df) // 2)
    if long_window < 60:
        long_window = len(df)

    df["ratio_baseline"] = df["price_ratio"].rolling(window=long_window, min_periods=max(60, long_window//4)).mean()

    # 如果长期窗口数据不足，使用可调整的短期窗口
    if df["ratio_baseline"].isna().sum() > len(df) * 0.2:
        # 使用用户设置的窗口大小
        df["ratio_baseline"] = df["price_ratio"].rolling(window=window_size, min_periods=max(10, window_size//2)).mean()

    # 填充初始缺失值：使用早期数据的中位数
    if df["ratio_baseline"].isna().any():
        df["ratio_baseline"] = df["ratio_baseline"].bfill()  # 从后往前填充
        if df["ratio_baseline"].isna().any():
            df["ratio_baseline"] = df["ratio_baseline"].fillna(baseline_value)

    # 溢价率 = (当前价格比率 / 基准比率 - 1) * 100
    # 这相当于：(当前价格 - 理论净值) / 理论净值 * 100%
    df["premium"] = ((df["price_ratio"] / df["ratio_baseline"]) - 1) * 100

    # 如果溢价率计算异常，使用更短期的基准
    if df["premium"].abs().max() > 500:  # 如果溢价率异常大
        # 使用用户设置的窗口大小
        df["ratio_baseline"] = df["price_ratio"].rolling(window=window_size, min_periods=max(10, window_size//2)).mean()
        df["ratio_baseline"] = df["ratio_baseline"].bfill().fillna(df["price_ratio"].mean())
        df["premium"] = ((df["price_ratio"] / df["ratio_baseline"]) - 1) * 100

# 确保premium列存在
if 'premium' not in df.columns or df['premium'].isna().all():
    st.error("溢价率计算失败，请检查数据源")
    st.stop()

# 填充缺失的溢价率值（如果有）
if df["premium"].isna().any():
    df["premium"] = df["premium"].ffill().bfill()

df["premium_high"] = df["premium"].where(df["premium"] > 8)
df["premium_low"] = df["premium"].where(df["premium"] < 1)

# 显示数据统计
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("159941 当前价格", f"{df['159941'].iloc[-1]:.4f} 元", f"{df['159941'].iloc[-1] - df['159941'].iloc[-2]:.4f}")
with col2:
    st.metric("QQQ 当前价格", f"${df['QQQ'].iloc[-1]:.2f}", f"${df['QQQ'].iloc[-1] - df['QQQ'].iloc[-2]:.2f}")
with col3:
    st.metric("当前溢价率", f"{df['premium'].iloc[-1]:.2f}%", f"{df['premium'].iloc[-1] - df['premium'].iloc[-2]:.2f}%")
with col4:
    # 显示净值（真实净值或估算净值）
    if 'nav_value' in df.columns and df['nav_value'].notna().any():
        # 使用真实净值
        nav_value = df['nav_value'].iloc[-1] if not pd.isna(df['nav_value'].iloc[-1]) else None
        if nav_value is not None:
            st.metric("当前净值", f"{nav_value:.4f} 元", 
                      help="来自akshare的真实净值数据")
        else:
            estimated_nav = df['159941'].iloc[-1] / (1 + df['premium'].iloc[-1] / 100)
            st.metric("估算净值", f"{estimated_nav:.4f} 元", 
                      help="基于价格比率长期均值估算的理论净值")
    else:
        # 显示估算净值
        estimated_nav = df['159941'].iloc[-1] / (1 + df['premium'].iloc[-1] / 100)
        st.metric("估算净值", f"{estimated_nav:.4f} 元", 
                  help="基于价格比率长期均值估算的理论净值")

# 添加说明
if 'nav_value' in df.columns and df['nav_value'].notna().any():
    st.success("✅ 使用真实净值数据计算溢价率")
    st.info("""
    **溢价率说明：**  
    - 溢价率 = (ETF实时价格 - ETF净值) ÷ ETF净值 × 100%  
    - 本应用使用akshare获取的159941真实净值数据计算溢价率
    - 数据来源：akshare金融数据接口
    """)
else:
    st.warning("⚠️ 使用估算方法计算溢价率")
    st.info("""
    **溢价率说明：**  
    - 溢价率 = (ETF实时价格 - ETF净值) ÷ ETF净值 × 100%  
    - 由于无法获取159941的净值数据，本应用使用价格比率的长期均值（250日）作为"理论净值"的代理来计算溢价率  
    - 实际溢价率请以基金公司公布的净值为准
    """)

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
# 准备hover数据
hover_data = df[["159941", "QQQ"]].values
if 'nav_value' in df.columns:
    # 如果有净值数据，在hover中显示净值
    hover_data = df[["159941", "QQQ", "nav_value"]].values
    hover_template = "<b>溢价率</b><br>" + \
                     "日期: %{x|%Y-%m-%d}<br>" + \
                     "溢价率: %{y:.2f}%<br>" + \
                     "159941价格: %{customdata[0]:.4f} 元<br>" + \
                     "净值: %{customdata[2]:.4f} 元<br>" + \
                     "QQQ: $%{customdata[1]:.2f}<br>" + \
                     "<extra></extra>"
else:
    hover_template = "<b>溢价率</b><br>" + \
                     "日期: %{x|%Y-%m-%d}<br>" + \
                     "溢价率: %{y:.2f}%<br>" + \
                     "159941: %{customdata[0]:.4f} 元<br>" + \
                     "QQQ: $%{customdata[1]:.2f}<br>" + \
                     "<extra></extra>"

fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["premium"],
        name="溢价率",
        mode="lines",
        line=dict(color="#2ca02c", width=2),
        hovertemplate=hover_template,
        customdata=hover_data
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
