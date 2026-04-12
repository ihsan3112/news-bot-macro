import time
import requests
import os
from datetime import datetime, timezone

# ================= CONFIG =================
NEWS_API_KEY = os.getenv("d731f728bb10403799a7a14bea6ac0f6")
TELEGRAM_BOT_TOKEN = os.getenv("8184173057:AAFxfvVPUpwovWHP3LPnZMlblqQy-E96sGA")
TELEGRAM_CHAT_ID = os.getenv("7806614019")

CHECK_INTERVAL = 1800  # 30 menit

# ================= CORE TOPIC =================

TOPIC_GROUPS = {
    "TRUMP": ["trump", "white house", "vance"],
    "FED": ["fed", "powell", "fomc", "cpi", "pce", "inflation"],
    "WAR": ["iran", "israel", "war", "missile", "attack", "conflict", "hormuz"],
    "CRYPTO": ["bitcoin", "btc", "crypto", "etf", "liquidation"],
    "WHALE": ["whale", "large transfer", "exchange inflow", "exchange outflow"]
}

# ================= TELEGRAM =================

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg
        })
    except:
        pass

# ================= HELPERS =================

def minutes_ago(published_at):
    now = datetime.now(timezone.utc)
    news_time = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int((now - news_time).total_seconds() / 60)

def detect_topic(title):
    t = title.lower()

    for group, words in TOPIC_GROUPS.items():
        for w in words:
            if w in t:
                return group
    return None

def detect_sentiment(title):
    t = title.lower()

    if any(x in t for x in ["attack", "war", "missile", "tension", "conflict"]):
        return "RISK-OFF ⚠️"

    if any(x in t for x in ["ceasefire", "peace", "deal", "agreement"]):
        return "RISK-ON 🟢"

    if any(x in t for x in ["liquidation", "dump", "crash"]):
        return "BEARISH 🔴"

    if any(x in t for x in ["pump", "surge", "rally"]):
        return "BULLISH 🟢"

    return "NETRAL"

def trader_action(topic, sentiment):
    if topic == "WAR":
        return "⚠️ WAIT / VOLATILE / JANGAN ENTRY"

    if topic == "TRUMP":
        return "⚠️ MARKET SENSITIF - TUNGGU REAKSI"

    if topic == "FED":
        return "⚠️ HIGH IMPACT - JANGAN ENTRY CEPAT"

    if topic == "WHALE":
        return "👀 PANTAU - BISA DISTRIBUSI / AKUMULASI"

    if sentiment == "BULLISH 🟢":
        return "🔥 BISA CARI MOMENTUM"

    if sentiment == "BEARISH 🔴":
        return "⚠️ HATI-HATI / POTENSI DUMP"

    return "👀 PANTAU SAJA"

# ================= FETCH =================

def fetch_news():
    query = "trump OR fed OR iran OR bitcoin OR whale"

    url = (
        f"https://newsapi.org/v2/everything?"
        f"q={