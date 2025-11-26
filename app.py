import streamlit as st
import yfinance as yf
import baostock as bs
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

st.title("159941 vs QQQ 溢价情绪指标（在线版）")

# 添加加载状态
with st.spinner("正在获取数据..."):
    df_cn = None
    df_nav = None
    df_us = None
    
    # 使用 baostock 获取159941的收盘价和净值
    try:
        bs.login()
        
        # 1. 获取159941收盘价
        rs_price = bs.query_history_k_data_plus(
            "sz.159941",
            "date,close",
            start_date="2020-01-01",
            end_date=datetime.today().strftime("%Y-%m-%d"),
            frequency="d",
            adjustflag="3"
        )
        
        if rs_price.error_code == '0':
            price_list = []
            while (rs_price.error_code == '0') and rs_price.next():
                price_list.append(rs_price.get_row_data())
            
            if price_list:
                df_price = pd.DataFrame(price_list, columns=rs_price.fields)
                df_price['date'] = pd.to_datetime(df_price['date'])
                df_price['close'] = pd.to_numeric(df_price['close'], errors='coerce')
                df_price.set_index('date', inplace=True)
                df_cn = df_price['close'].dropna()
                st.success(f"✅ 成功获取 159941 收盘价 ({len(df_cn)} 条)")
        
        bs.logout()
        
        # 如果baostock获取失败，回退到yfinance
        if df_cn is None or df_cn.empty:
            st.warning("⚠️ baostock获取收盘价失败，尝试使用yfinance...")
            df_cn = None
        
    except Exception as e:
        try:
            bs.logout()
        except Exception:
            pass
        st.warning(f"⚠️ baostock获取数据失败: {str(e)}，尝试使用yfinance...")
    
    # 如果 baostock 失败，回退到 yfinance
    if df_cn is None or df_cn.empty:
        try:
            df_cn = yf.download("159941.SZ", start="2020-01-01", progress=False, auto_adjust=False)
            if not df_cn.empty:
                if isinstance(df_cn.columns, pd.MultiIndex):
                    df_cn = df_cn['Close'].iloc[:, 0]
                else:
                    df_cn = df_cn['Close']
                if isinstance(df_cn, pd.DataFrame):
                    df_cn = df_cn.iloc[:, 0]
                st.success(f"✅ 使用 yfinance 成功下载 159941 数据 ({len(df_cn)} 条)")
            else:
                st.error("无法下载159941.SZ数据，请检查股票代码或网络连接")
                st.stop()
        except Exception as e:
            st.error(f"下载159941数据时出错: {str(e)}")
            st.stop()
    
    # 获取159941净值（优先天天基金网，数据不足时使用akshare）
    # 无论baostock是否成功，都需要获取净值
    df_nav = None
    
    # 使用df_cn的日期范围获取净值
    start_date = df_cn.index[0].strftime("%Y-%m-%d")
    end_date = df_cn.index[-1].strftime("%Y-%m-%d")
    
    # 方法1: 优先使用天天基金网（快速）
    try:
        import requests
        from lxml import etree
        
        def get_159941_nav_from_eastmoney(start_date, end_date):
            """从天天基金网获取159941净值"""
            url = f"http://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code=159941&page=1&per=10000&sdate={start_date}&edate={end_date}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            resp = requests.get(url, headers=headers, timeout=10)
            html = etree.HTML(resp.text)
            
            # 解析净值
            dates = html.xpath('//table[@class="w782 comm lsjz"]//tr/td[1]/text()')[1:]  # 跳过表头
            navs = html.xpath('//table[@class="w782 comm lsjz"]//tr/td[2]/text()')[1:]
            
            if dates and navs:
                nav_df = pd.DataFrame({'date': dates, 'nav': navs})
                nav_df['date'] = pd.to_datetime(nav_df['date'])
                nav_df['nav'] = pd.to_numeric(nav_df['nav'], errors='coerce')
                nav_df = nav_df.dropna(subset=['nav']).reset_index(drop=True)
                nav_df.set_index('date', inplace=True)
                nav_df.rename(columns={'nav': 'nav_value'}, inplace=True)
                return nav_df
            return pd.DataFrame()
        
        df_nav = get_159941_nav_from_eastmoney(start_date, end_date)
        
        # 检查数据是否足够（如果最早日期晚于所需日期，说明数据不足）
        if not df_nav.empty:
            nav_earliest_date = df_nav.index.min()
            required_earliest_date = pd.to_datetime(start_date)
            
            # 如果净值数据最早日期比所需日期晚超过30天，说明数据不足，使用akshare
            if (nav_earliest_date - required_earliest_date).days > 30:
                st.warning(f"⚠️ 天天基金网净值数据最早只到 {nav_earliest_date.strftime('%Y-%m-%d')}，使用akshare获取完整历史数据...")
                df_nav = None
            else:
                st.success(f"✅ 从天天基金网成功获取 159941 净值 ({len(df_nav)} 条)")
    except ImportError:
        st.warning("⚠️ 缺少requests或lxml库，尝试使用akshare...")
        df_nav = None
    except Exception as e:
        st.warning(f"⚠️ 从天天基金网获取净值失败: {str(e)}，尝试使用akshare...")
        df_nav = None
    
    # 方法2: 如果天天基金网数据不足，使用akshare获取完整历史数据
    if df_nav is None or df_nav.empty:
        try:
            import akshare as ak
            st.info("📊 正在从akshare获取完整历史净值数据（可能需要几秒钟）...")
            
            # akshare需要YYYYMMDD格式
            start_date_ak = df_cn.index[0].strftime("%Y%m%d")
            end_date_ak = df_cn.index[-1].strftime("%Y%m%d")
            
            df_nav_raw = ak.fund_etf_fund_info_em(fund="159941", start_date=start_date_ak, end_date=end_date_ak)
            
            if not df_nav_raw.empty and '净值日期' in df_nav_raw.columns and '单位净值' in df_nav_raw.columns:
                df_nav_raw['净值日期'] = pd.to_datetime(df_nav_raw['净值日期'])
                df_nav_raw.set_index('净值日期', inplace=True)
                df_nav_raw['nav_value'] = pd.to_numeric(df_nav_raw['单位净值'], errors='coerce')
                df_nav = df_nav_raw[['nav_value']].dropna()
                
                if not df_nav.empty:
                    st.success(f"✅ 从akshare成功获取 159941 净值 ({len(df_nav)} 条，日期范围: {df_nav.index.min().strftime('%Y-%m-%d')} 至 {df_nav.index.max().strftime('%Y-%m-%d')})")
                else:
                    df_nav = None
            else:
                st.warning("⚠️ akshare返回的数据格式不正确")
                df_nav = None
        except ImportError:
            st.warning("⚠️ 缺少akshare库，无法获取完整历史净值数据")
            df_nav = None
        except Exception as e:
            st.warning(f"⚠️ 从akshare获取净值失败: {str(e)}")
            df_nav = None
    
    # 下载美国ETF数据 (QQQ)
    try:
        df_us = yf.download("QQQ", start="2020-01-01", progress=False, auto_adjust=False)
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

# df_nav已经在上面从天天基金网获取了，这里检查是否成功
if df_nav is None or df_nav.empty or 'nav_value' not in df_nav.columns:
    st.error("⚠️ 未能从天天基金网获取净值数据，请检查网络连接或数据源")
    st.stop()

# 计算溢价率：159941是广发纳斯达克100ETF（纳指ETF）
# 溢价率 = (ETF实时价格 - ETF净值) ÷ ETF净值 × 100%

# 使用天天基金网获取的真实净值数据计算溢价率
df_with_nav = pd.merge(df[['159941']], df_nav, left_index=True, right_index=True, how='inner')

if not df_with_nav.empty:
    # 使用真实净值计算溢价率
    df_with_nav["premium"] = ((df_with_nav["159941"] - df_with_nav["nav_value"]) / df_with_nav["nav_value"]) * 100
    
    # 将溢价率和净值合并回主数据框
    df = df.merge(df_with_nav[['premium', 'nav_value']], left_index=True, right_index=True, how='left')
    # 前向填充和后向填充缺失的溢价率
    df["premium"] = df["premium"].ffill().bfill()
    
    st.info("📊 使用天天基金网真实净值数据计算溢价率")
else:
    st.error("⚠️ 净值数据与价格数据无法匹配，请检查数据源")
    st.stop()

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
    # 显示真实净值
    if 'nav_value' in df.columns and df['nav_value'].notna().any():
        nav_value = df['nav_value'].iloc[-1] if not pd.isna(df['nav_value'].iloc[-1]) else None
        if nav_value is not None:
            st.metric("当前净值", f"{nav_value:.4f} 元", 
                      help="来自天天基金网的真实净值数据")
        else:
            st.metric("当前净值", "N/A", help="净值数据缺失")

# 添加说明
st.info("""
**溢价率计算公式：**  
溢价率 = (ETF实时价格 - ETF净值) ÷ ETF净值 × 100%

**数据来源：**  
- 159941收盘价：baostock（失败时自动回退到yfinance）
- 159941净值：天天基金网（优先，快速）/ akshare（备选，完整历史数据）
- QQQ价格：yfinance
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

st.plotly_chart(fig, width='stretch')
