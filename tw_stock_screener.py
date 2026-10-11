#!/usr/bin/env python3
"""
台股每日篩選：以執行當日為基準，近一個月漲幅 >= 門檻（預設 5%）

安裝：  pip install yfinance pandas requests
執行：  python tw_stock_screener.py
選項：  python tw_stock_screener.py --min-gain 5 --min-volume 1000 --outdir ./output
輸出：  output/tw_up_YYYYMMDD.csv（Excel 可直接開啟）
"""
import argparse
import datetime as dt
import os
import sys
import time

import pandas as pd
import requests
import yfinance as yf

# 證交所 / 櫃買中心公開資料（上市、上櫃公司清單）
SOURCES = [
    ("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", ".TW", "上市"),
    ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", ".TWO", "上櫃"),
]


def get_universe() -> pd.DataFrame:
    """取得上市 + 上櫃的普通股清單（4 位數代號）。"""
    rows = []
    for url, suffix, market in SOURCES:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            for d in r.json():
                code = str(d.get("公司代號", "")).strip()
                name = str(d.get("公司簡稱", "")).strip()
                if code.isdigit() and len(code) == 4:
                    rows.append(
                        {"代號": code, "名稱": name, "市場": market,
                         "ticker": code + suffix}
                    )
        except Exception as e:
            print(f"[警告] 無法取得{market}清單：{e}", file=sys.stderr)
    df = pd.DataFrame(rows).drop_duplicates("ticker")
    if df.empty:
        sys.exit("取不到股票清單，請檢查網路連線。")
    return df


def analyze(df: pd.DataFrame):
    """回傳 (最新日期, 最新收盤, 基準日收盤, 漲幅%, 20日均量(張))。"""
    df = df.dropna(subset=["Close"])
    if len(df) < 20:
        return None
    last_date = df.index[-1]
    target = last_date - pd.DateOffset(months=1)
    base_df = df[df.index <= target]
    if base_df.empty:
        return None
    base = float(base_df["Close"].iloc[-1])
    last = float(df["Close"].iloc[-1])
    if base <= 0:
        return None
    vol = float(df["Volume"].tail(20).mean()) / 1000  # 股 -> 張
    return last_date, last, base, (last / base - 1) * 100, vol


def run(min_gain: float, min_volume: float, outdir: str, batch_size: int = 150):
    universe = get_universe()
    print(f"股票數量：{len(universe)}，開始下載價格資料…")

    results = []
    tickers = universe["ticker"].tolist()
    info = universe.set_index("ticker")

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.download(
                batch, period="3mo", auto_adjust=True, group_by="ticker",
                progress=False, threads=True,
            )
        except Exception as e:
            print(f"[警告] 批次 {i} 下載失敗：{e}", file=sys.stderr)
            continue

        for t in batch:
            try:
                sub = data[t] if isinstance(data.columns, pd.MultiIndex) else data
                res = analyze(sub)
            except Exception:
                continue
            if res is None:
                continue
            last_date, last, base, gain, vol = res
            if gain >= min_gain and vol >= min_volume:
                results.append({
                    "代號": info.loc[t, "代號"],
                    "名稱": info.loc[t, "名稱"],
                    "市場": info.loc[t, "市場"],
                    "最新日期": last_date.strftime("%Y-%m-%d"),
                    "最新收盤": round(last, 2),
                    "一個月前收盤": round(base, 2),
                    "一個月漲幅%": round(gain, 2),
                    "20日均量(張)": int(vol),
                })
        print(f"進度：{min(i + batch_size, len(tickers))}/{len(tickers)}")
        time.sleep(1)  # 避免請求過快

    out = pd.DataFrame(results)
    if out.empty:
        print("今天沒有符合條件的股票。")
        return
    out = out.sort_values("一個月漲幅%", ascending=False)

    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"tw_up_{dt.date.today():%Y%m%d}.csv")
    out.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n共 {len(out)} 檔符合條件，已存到：{path}\n")
    print(out.head(20).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="台股近一個月漲幅篩選")
    ap.add_argument("--min-gain", type=float, default=5.0, help="最低漲幅 %%（預設 5）")
    ap.add_argument("--min-volume", type=float, default=500,
                    help="20日均量下限（張，預設 500，排除冷門股；設 0 不限制）")
    ap.add_argument("--outdir", default="output", help="輸出資料夾")
    args = ap.parse_args()
    run(args.min_gain, args.min_volume, args.outdir)
