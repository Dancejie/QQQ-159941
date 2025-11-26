import streamlit as st
import yfinance as yf
import baostock as bs
import pandas as pd
import matplotlib.pyplot as plt
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
df["premium"] = (df["159941"] / df["QQQ"] - 1) * 100
df["premium_high"] = df["premium"].where(df["premium"] > 8)
df["premium_low"] = df["premium"].where(df["premium"] < 1)

# 创建图表
fig, ax = plt.subplots(2, 1, figsize=(14, 10))

ax[0].plot(df.index, df["159941"], label="159941")
ax[0].plot(df.index, df["QQQ"], label="QQQ")
ax[0].set_title("159941 vs QQQ")
ax[0].legend()
ax[0].grid(True, alpha=0.3)

ax[1].plot(df.index, df["premium"], label="溢价率(%)", linewidth=1.5)
ax[1].scatter(df.index, df["premium_high"], color="red", s=30, label="高溢价 (>8%)", alpha=0.6)
ax[1].scatter(df.index, df["premium_low"], color="blue", s=30, label="低溢价 (<1%)", alpha=0.6)
ax[1].axhline(y=8, color='red', linestyle='--', alpha=0.5, linewidth=1)
ax[1].axhline(y=1, color='blue', linestyle='--', alpha=0.5, linewidth=1)
ax[1].set_title("溢价率趋势")
ax[1].set_ylabel("溢价率 (%)")
ax[1].legend()
ax[1].grid(True, alpha=0.3)

plt.tight_layout()
st.pyplot(fig, clear_figure=True)
