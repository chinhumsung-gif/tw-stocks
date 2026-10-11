#!/usr/bin/env python3
"""
每日產生網頁 docs/index.html：台股近一個月漲幅 >= 5% 的股票清單。
需與 tw_stock_screener.py 放在同一個資料夾。
"""
import datetime as dt
import html
import os
import sys
import time

import pandas as pd
import yfinance as yf

from tw_stock_screener import analyze, get_universe

MIN_GAIN = 5.0       # 最低漲幅 %
MIN_VOLUME = 500     # 20 日均量下限（張），設 0 不限制
BATCH = 150


def screen() -> pd.DataFrame:
    universe = get_universe()
    info = universe.set_index("ticker")
    tickers = universe["ticker"].tolist()
    rows = []
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        try:
            data = yf.download(batch, period="3mo", auto_adjust=True,
                               group_by="ticker", progress=False, threads=True)
        except Exception as e:
            print(f"[警告] 批次 {i} 失敗：{e}", file=sys.stderr)
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
            if gain >= MIN_GAIN and vol >= MIN_VOLUME:
                rows.append({
                    "代號": info.loc[t, "代號"], "名稱": info.loc[t, "名稱"],
                    "市場": info.loc[t, "市場"],
                    "資料日期": last_date.strftime("%Y-%m-%d"),
                    "最新收盤": round(last, 2), "一個月前收盤": round(base, 2),
                    "漲幅": round(gain, 2), "均量": int(vol),
                })
        time.sleep(1)
    df = pd.DataFrame(rows)
    return df.sort_values("漲幅", ascending=False) if not df.empty else df


def render(df: pd.DataFrame) -> str:
    tw_now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    if df.empty:
        body = "<p>今天沒有符合條件的股票。</p>"
        data_date = "-"
    else:
        data_date = df["資料日期"].max()
        tr = []
        for r in df.itertuples(index=False):
            tr.append(
                f"<tr><td>{r.代號}</td><td>{html.escape(r.名稱)}</td><td>{r.市場}</td>"
                f"<td>{r.最新收盤:.2f}</td><td>{r.一個月前收盤:.2f}</td>"
                f"<td class='up'>+{r.漲幅:.2f}%</td><td>{r.均量:,}</td></tr>"
            )
        body = (
            "<div class='wrap'><table><thead><tr><th>代號</th><th>名稱</th><th>市場</th>"
            "<th>最新收盤</th><th>一個月前</th><th>漲幅</th><th>20日均量(張)</th>"
            "</tr></thead><tbody>" + "".join(tr) + "</tbody></table></div>"
        )
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>台股近一個月漲幅 {MIN_GAIN:g}% 以上</title>
<style>
body{{font-family:system-ui,"Microsoft JhengHei",sans-serif;margin:0;padding:16px;background:#fafafa;color:#222}}
h1{{font-size:20px;margin:0 0 4px}} .meta{{color:#666;font-size:13px;margin-bottom:12px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;background:#fff;min-width:560px}}
th,td{{padding:8px 10px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap}}
th:nth-child(-n+3),td:nth-child(-n+3){{text-align:left}}
th{{background:#f0f0f0;position:sticky;top:0}} .up{{color:#d62728;font-weight:600}}
.note{{margin-top:12px;font-size:12px;color:#888}}
</style></head><body>
<h1>台股近一個月漲幅 ≥ {MIN_GAIN:g}%（共 {len(df)} 檔）</h1>
<div class="meta">資料日期：{data_date}　網頁更新：{tw_now:%Y-%m-%d %H:%M}（台灣時間）　已排除 20 日均量低於 {MIN_VOLUME} 張</div>
{body}
<div class="note">資料來源：證交所、櫃買中心公司清單與 Yahoo Finance，可能有延遲或誤差。僅供參考，不構成投資建議。</div>
</body></html>"""


if __name__ == "__main__":
    result = screen()
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(render(result))
    print(f"完成，共 {len(result)} 檔，已寫入 docs/index.html")
