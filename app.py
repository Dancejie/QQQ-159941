import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

st.title("159941 vs QQQ 溢价情绪指标（在线版）")

# 添加加载状态
with st.spinner("正在下载数据..."):
    try:
        # 尝试下载中国ETF数据（yfinance对中国股票支持有限，可能需要使用其他格式）
        # 如果159941.SZ无法下载，可以尝试159941.SS（上海）或其他格式
        df_cn = yf.download("159941.SZ", start="2020-01-01", progress=False)
        if df_cn.empty:
            st.error("无法下载159941.SZ数据，请检查股票代码或网络连接")
            st.stop()
        df_cn = df_cn['Close']
        
        df_us = yf.download("QQQ", start="2020-01-01", progress=False)
        if df_us.empty:
            st.error("无法下载QQQ数据，请检查网络连接")
            st.stop()
        df_us = df_us['Close']
    except Exception as e:
        st.error(f"下载数据时出错: {str(e)}")
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
