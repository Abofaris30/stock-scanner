import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import os
from datetime import datetime
import pytz

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

BENCHMARK = "^GSPC"
LEFT_BARS = 3
RIGHT_BARS = 3
SCAN_INTERVAL = 60 * 15

STOCKS_FILE = "stocks.txt"

TIMEFRAMES = [
    ("15m", "15m", "5d"),
    ("1H",  "1h",  "1mo"),
    ("4H",  "1h",  "1mo"),
    ("1D",  "1d",  "6mo"),
]

NY_TZ = pytz.timezone("America/New_York")

def is_market_open():
    now = datetime.now(NY_TZ)
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now <= market_close

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=data, timeout=10)
        print(f"تيليغرام: {response.status_code}")
    except Exception as e:
        print(f"خطأ في التيليغرام: {e}")

def load_stocks():
    if not os.path.exists(STOCKS_FILE):
        print(f"ملف {STOCKS_FILE} غير موجود!")
        return []
    with open(STOCKS_FILE, "r") as f:
        stocks = [line.strip().upper() for line in f if line.strip()]
    return stocks

def pivot_low(series, left, right):
    result = [np.nan] * len(series)
    for i in range(left, len(series) - right):
        window = series[i - left:i + right + 1]
        if series[i] == min(window):
            result[i] = series[i]
    return result

def pivot_high(series, left, right):
    result = [np.nan] * len(series)
    for i in range(left, len(series) - right):
        window = series[i - left:i + right + 1]
        if series[i] == max(window):
            result[i] = series[i]
    return result

def analyze(symbol, tf_name, interval, period):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        bench = yf.download(BENCHMARK, period=period, interval=interval, progress=False, auto_adjust=True)

        if df.empty or bench.empty:
            return None

        if tf_name == "4H":
            df    = df.resample("4h").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
            bench = bench.resample("4h").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()

        df, bench = df.align(bench, join='inner', axis=0)

        if len(df) < 30:
            return None

        close = df['Close'].squeeze().values
        ref   = bench['Close'].squeeze().values

        rs = close / ref * 100
        rs_series = pd.Series(rs)
        ema21 = rs_series.ewm(span=21, adjust=False).mean().values

        pl = pivot_low(rs, LEFT_BARS, RIGHT_BARS)
        ph = pivot_high(rs, LEFT_BARS, RIGHT_BARS)

        last_low = np.nan
        high_after_last_low = np.nan
        low_found = False
        buy_signal = False

        for i in range(len(rs) - 1):
            if not np.isnan(pl[i]):
                last_low = pl[i]
                high_after_last_low = np.nan
                low_found = True
            if low_found and not np.isnan(ph[i]):
                high_after_last_low = ph[i]

        i = len(rs) - 1
        if (low_found and not np.isnan(high_after_last_low)
                and rs[i - 1] < high_after_last_low and rs[i] >= high_after_last_low):
            buy_signal = True

        last_high = np.nan
        low_after_last_high = np.nan
        high_found = False
        sell_signal = False

        for i in range(len(rs) - 1):
            if not np.isnan(ph[i]):
                last_high = ph[i]
                low_after_last_high = np.nan
                high_found = True
            if high_found and not np.isnan(pl[i]):
                low_after_last_high = pl[i]

        i = len(rs) - 1
        if (high_found and not np.isnan(low_after_last_high)
                and rs[i - 1] > ema21[i - 1] and rs[i] <= ema21[i]
                and rs[i - 1] > low_after_last_high and rs[i] <= low_after_last_high):
            sell_signal = True

        return {"buy": buy_signal, "sell": sell_signal}

    except Exception as e:
        print(f"خطأ في {symbol} [{tf_name}]: {e}")
        return None

def run():
    print("السكانر شغال...")
    send_telegram("🚀 السكانر بدأ التشغيل!")

    while True:
        if not is_market_open():
            now = datetime.now(NY_TZ).strftime("%Y-%m-%d %H:%M")
            print(f"[{now}] السوق مغلق، انتظار...")
            time.sleep(60)
            continue

        stocks = load_stocks()
        if not stocks:
            time.sleep(60)
            continue

        now = datetime.now(NY_TZ).strftime("%Y-%m-%d %H:%M")
        print(f"\n[{now}] يفحص {len(stocks)} سهم...")

        for tf_name, interval, period in TIMEFRAMES:
            buy_list  = []
            sell_list = []

            for symbol in stocks:
                result = analyze(symbol, tf_name, interval, period)
                if result:
                    if result["buy"]:
                        buy_list.append(symbol)
                    if result["sell"]:
                        sell_list.append(symbol)
                time.sleep(0.5)

            if buy_list:
                msg = f"🟢 <b>BUY | {tf_name}</b> | {now}\n\n" + "\n".join(f"• {s}" for s in buy_list)
                send_telegram(msg)
                print(f"BUY [{tf_name}]: {', '.join(buy_list)}")

            if sell_list:
                msg = f"🔴 <b>SELL | {tf_name}</b> | {now}\n\n" + "\n".join(f"• {s}" for s in sell_list)
                send_telegram(msg)
                print(f"SELL [{tf_name}]: {', '.join(sell_list)}")

            if not buy_list and not sell_list:
                print(f"[{tf_name}] لا توجد اشارات")

        print(f"انتظار {SCAN_INTERVAL // 60} دقيقة...")
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    run()
