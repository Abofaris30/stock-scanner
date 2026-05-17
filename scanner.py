import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import os
from datetime import datetime

# =============================
# إعدادات التيليغرام - عبّيها أنت
# =============================
TELEGRAM_TOKEN = "ضع_التوكن_هنا"
TELEGRAM_CHAT_ID = "ضع_الشات_ID_هنا"

# =============================
# إعدادات السكريبت
# =============================
BENCHMARK = "^GSPC"       # S&P 500
INTERVAL = "15m"          # الفريم الزمني
PERIOD = "5d"             # كمية البيانات
LEFT_BARS = 3             # Pivot Left
RIGHT_BARS = 3            # Pivot Right
SCAN_INTERVAL = 60 * 15  # كل 15 دقيقة بالثواني

STOCKS_FILE = "stocks.txt"  # ملف قائمة الأسهم

# =============================
# إرسال رسالة تيليغرام
# =============================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"خطأ في التيليغرام: {e}")

# =============================
# قراءة قائمة الأسهم
# =============================
def load_stocks():
    if not os.path.exists(STOCKS_FILE):
        print(f"⚠️ ملف {STOCKS_FILE} غير موجود! أنشئه وضع فيه الأسهم.")
        return []
    with open(STOCKS_FILE, "r") as f:
        stocks = [line.strip().upper() for line in f if line.strip()]
    return stocks

# =============================
# حساب Pivot Low/High
# =============================
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

# =============================
# تحليل سهم واحد
# =============================
def analyze(symbol):
    try:
        # بيانات السهم والـ Benchmark
        df = yf.download(symbol, period=PERIOD, interval=INTERVAL, progress=False, auto_adjust=True)
        bench = yf.download(BENCHMARK, period=PERIOD, interval=INTERVAL, progress=False, auto_adjust=True)

        if df.empty or bench.empty or len(df) < 30:
            return None

        # مزامنة الأوقات
        df, bench = df.align(bench, join='inner', axis=0)

        close = df['Close'].squeeze().values
        ref = bench['Close'].squeeze().values

        if len(close) < 30:
            return None

        # حساب RS
        rs = close / ref * 100

        # EMA 21
        rs_series = pd.Series(rs)
        ema21 = rs_series.ewm(span=21, adjust=False).mean().values

        # Pivot
        pl = pivot_low(rs, LEFT_BARS, RIGHT_BARS)
        ph = pivot_high(rs, LEFT_BARS, RIGHT_BARS)

        # =============================
        # BUY Logic
        # =============================
        last_low = np.nan
        high_after_last_low = np.nan
        low_found = False
        buy_signal = False

        for i in range(len(rs)):
            if not np.isnan(pl[i]):
                last_low = pl[i]
                high_after_last_low = np.nan
                low_found = True
            if low_found and not np.isnan(ph[i]):
                high_after_last_low = ph[i]
            if (low_found and not np.isnan(high_after_last_low) and i > 0
                    and rs[i - 1] < high_after_last_low and rs[i] >= high_after_last_low):
                buy_signal = True

        # =============================
        # SELL Logic
        # =============================
        last_high = np.nan
        low_after_last_high = np.nan
        high_found = False
        sell_signal = False

        for i in range(len(rs)):
            if not np.isnan(ph[i]):
                last_high = ph[i]
                low_after_last_high = np.nan
                high_found = True
            if high_found and not np.isnan(pl[i]):
                low_after_last_high = pl[i]
            if (high_found and not np.isnan(low_after_last_high) and i > 0
                    and rs[i - 1] > ema21[i - 1] and rs[i] <= ema21[i]
                    and rs[i - 1] > low_after_last_high and rs[i] <= low_after_last_high):
                sell_signal = True

        return {"buy": buy_signal, "sell": sell_signal}

    except Exception as e:
        print(f"خطأ في {symbol}: {e}")
        return None

# =============================
# الحلقة الرئيسية
# =============================
def run():
    print("🚀 السكانر شغال...")
    while True:
        stocks = load_stocks()
        if not stocks:
            time.sleep(60)
            continue

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        print(f"\n🔍 [{now}] يفحص {len(stocks)} سهم...")

        buy_list = []
        sell_list = []

        for symbol in stocks:
            result = analyze(symbol)
            if result:
                if result["buy"]:
                    buy_list.append(symbol)
                if result["sell"]:
                    sell_list.append(symbol)
            time.sleep(1)  # تجنب الحظر

        # إرسال التنبيهات
        if buy_list:
            msg = f"🟢 <b>BUY Signal</b> | {now}\n\n" + "\n".join(f"• {s}" for s in buy_list)
            send_telegram(msg)
            print(f"✅ BUY: {', '.join(buy_list)}")

        if sell_list:
            msg = f"🔴 <b>SELL Signal</b> | {now}\n\n" + "\n".join(f"• {s}" for s in sell_list)
            send_telegram(msg)
            print(f"🔻 SELL: {', '.join(sell_list)}")

        if not buy_list and not sell_list:
            print("⏳ لا توجد إشارات الآن")

        print(f"💤 انتظار {SCAN_INTERVAL // 60} دقيقة...")
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    run()
