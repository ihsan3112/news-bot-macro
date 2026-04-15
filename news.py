import requests
import time
from datetime import datetime

# =========================
# CONFIG
# =========================
SYMBOL = "BTCUSDT"
INTERVAL = 1800  # 30 menit
LIMIT = 100

BINANCE_URL = f"https://api.binance.com/api/v3/klines"

# =========================
# HELPER
# =========================
def get_klines(symbol, interval, limit=100):
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    res = requests.get(BINANCE_URL, params=params)
    data = res.json()
    return data


def parse_candle(c):
    return {
        "open": float(c[1]),
        "high": float(c[2]),
        "low": float(c[3]),
        "close": float(c[4]),
        "volume": float(c[5])
    }


# =========================
# ANALISA CORE
# =========================
def analyze(candles):
    closes = [c["close"] for c in candles]

    last = candles[-1]
    prev = candles[-2]

    # Struktur sederhana
    trend = "UP" if closes[-1] > closes[-5] else "DOWN"

    # Momentum
    body = abs(last["close"] - last["open"])
    momentum = "STRONG" if body > (last["high"] - last["low"]) * 0.6 else "WEAK"

    # Volume
    avg_vol = sum(c["volume"] for c in candles[-10:]) / 10
    vol_state = "HIGH" if last["volume"] > avg_vol else "LOW"

    # Support / Resistance kasar
    support = min(c["low"] for c in candles[-20:])
    resistance = max(c["high"] for c in candles[-20:])

    # Posisi harga
    if last["close"] > resistance * 0.98:
        level = "NEAR RESIST"
    elif last["close"] < support * 1.02:
        level = "NEAR SUPPORT"
    else:
        level = "MID"

    # Quality
    if momentum == "STRONG" and vol_state == "HIGH":
        quality = "OK"
    elif momentum == "WEAK":
        quality = "NOISE"
    else:
        quality = "PULLBACK"

    # Decision logic (simple tapi efektif)
    if trend == "UP" and quality == "OK" and level != "NEAR RESIST":
        decision = "LONG READY"
    elif trend == "DOWN" and quality == "OK" and level != "NEAR SUPPORT":
        decision = "SHORT READY"
    elif quality == "NOISE":
        decision = "NO TRADE"
    else:
        decision = "WAIT"

    return {
        "trend": trend,
        "momentum": momentum,
        "volume": vol_state,
        "level": level,
        "quality": quality,
        "decision": decision,
        "price": last["close"],
        "support": support,
        "resistance": resistance
    }


# =========================
# OUTPUT
# =========================
def print_analysis(result):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 40)
    print(f"[{now}] BTC")
    print("=" * 40)

    print(f"Harga        : {result['price']}")
    print(f"Trend        : {result['trend']}")
    print(f"Momentum     : {result['momentum']}")
    print(f"Volume       : {result['volume']}")
    print(f"Level        : {result['level']}")
    print(f"Support      : {round(result['support'], 2)}")
    print(f"Resistance   : {round(result['resistance'], 2)}")
    print(f"Quality      : {result['quality']}")

    print("-" * 40)
    print(f"AKSI BOT     : {result['decision']}")
    print("=" * 40)


# =========================
# MAIN LOOP
# =========================
def main():
    print("=== BTC BOT START ===")
    print(f"Interval: {INTERVAL} detik")

    while True:
        try:
            raw = get_klines(SYMBOL, "5m", LIMIT)
            candles = [parse_candle(c) for c in raw]

            result = analyze(candles)
            print_analysis(result)

        except Exception as e:
            print("ERROR:", e)

        print(f"\nTunggu {INTERVAL} detik...\n")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()