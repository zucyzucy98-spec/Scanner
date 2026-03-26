import ccxt
import pandas as pd
import requests
import os
from datetime import datetime

TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}&parse_mode=Markdown"
    requests.get(url)

def calculate_indicators(df):
    # 1. Bollinger Bands (20, 2)
    sma = df['c'].rolling(window=20).mean()
    std = df['c'].rolling(window=20).std()
    df['bb_upper'] = sma + (std * 2)
    df['bb_lower'] = sma - (std * 2)
    df['bbw'] = (df['bb_upper'] - df['bb_lower']) / sma
    
    # 2. Stochastic (5, 3, 3)
    low_5 = df['l'].rolling(window=5).min()
    high_5 = df['h'].rolling(window=5).max()
    # %K raw
    df['stoch_k_raw'] = 100 * ((df['c'] - low_5) / (high_5 - low_5))
    # %K smooth (3) dan %D (3)
    df['stoch_k'] = df['stoch_k_raw'].rolling(window=3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
    
    # 3. Volume SMA 20
    df['vol_ma'] = df['v'].rolling(window=20).mean()
    return df

def run_screener():
    exchange = ccxt.bitget() # Atau ccxt.binance()
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = [t for t in tickers.values() if '/USDT' in t['symbol'] and ':' not in t['symbol']]
        sorted_tickers = sorted(usdt_pairs, key=lambda x: x['quoteVolume'] if x['quoteVolume'] else 0, reverse=True)[:50]
        symbols = [t['symbol'] for t in sorted_tickers]

        # Notif Aktif
        send_telegram(f"🤖 *Bot Aktif:* Memindai {len(symbols)} koin di Bitget...")

        signals = []
        for symbol in symbols:
            try:
                bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                df = calculate_indicators(df)

                # Ambil nilai terakhir
                last = df.iloc[-1]
                prev = df.iloc[-2]
                
                # LOGIKA SCAN
                # A. Squeeze: BBW terendah dalam 10 jam terakhir
                is_squeeze = last['bbw'] <= df['bbw'].tail(10).min()
                # B. Volume: 1.5x rata-rata
                is_vol_break = last['v'] > (last['vol_ma'] * 1.5)
                # C. Stoch Cross: K > D dan sebelumnya K <= D
                is_stoch_cross = last['stoch_k'] > last['stoch_d'] and prev['stoch_k'] <= prev['stoch_d']

                if is_squeeze and is_vol_break and is_stoch_cross:
                    signals.append(f"🎯 *{symbol}*\nSqueeze + Vol Breakout!\nStoch K: `{last['stoch_k']:.2f}`")

            except: continue

        if signals:
            send_telegram("🚀 *SIGNAL DITEMUKAN:*\n\n" + "\n\n".join(signals))
        else:
            send_telegram("✅ Selesai: Belum ada sinyal.")

    except Exception as e:
        send_telegram(f"⚠️ Error: {str(e)}")

if __name__ == "__main__":
    run_screener()
