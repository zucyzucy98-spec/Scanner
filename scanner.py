import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import os
import time
from datetime import datetime

# --- KONFIGURASI API ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
MIN_VOLUME_USDT = 1000000 

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        params = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
        requests.get(url, params=params)
    except Exception as e:
        print(f"Error Telegram: {e}")

def scan_bitget():
    exchange = ccxt.bitget({'enableRateLimit': True, 'timeout': 30000})
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    send_telegram(f"🔍 *Screener Aktif ({now})*\nTimeframe: *1h & 4h* | Top 50 Koin")

    try:
        tickers = exchange.fetch_tickers()
        filtered_tickers = [
            t for t in tickers.values() 
            if '/USDT' in t['symbol'] and t['quoteVolume'] is not None and t['quoteVolume'] >= MIN_VOLUME_USDT
        ]
        sorted_tickers = sorted(filtered_tickers, key=lambda x: x['quoteVolume'], reverse=True)
        top_symbols = [t['symbol'] for t in sorted_tickers[:50]]
        
        signals_found = 0
        total_checked = 0

        for symbol in top_symbols:
            # PERUBAHAN DISINI: Mengganti TF menjadi 1h dan 4h
            for tf in ['1h', '4h']:
                try:
                    bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=100)
                    if len(bars) < 35: continue 
                    
                    df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    
                    # Indikator
                    bb = ta.bbands(df['c'], length=20, std=2)
                    df['bb_width'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']
                    df['vol_sma'] = ta.sma(df['v'], length=20)
                    df['rsi'] = ta.rsi(df['c'], length=14)
                    macd = ta.macd(df['c'])
                    
                    last = -1
                    # Logika Strategi (Tetap sama, namun lebih responsif di TF rendah)
                    is_squeeze = df['bb_width'].iloc[last] < df['bb_width'].tail(15).mean()
                    vol_breakout = df['v'].iloc[last] > (df['vol_sma'].iloc[last] * 1.5)
                    macd_bullish = macd['MACDh_12_26_9'].iloc[last] > 0
                    not_overbought = df['rsi'].iloc[last] < 70

                    if is_squeeze and vol_breakout and macd_bullish and not_overbought:
                        current_vol = [t['quoteVolume'] for t in sorted_tickers if t['symbol'] == symbol][0]
                        
                        msg = (
                            f"🎯 *INTRADAY SIGNAL (BITGET)*\n\n"
                            f"💎 *Asset:* `{symbol}`\n"
                            f"⏱️ *TF:* `{tf}` | *RSI:* `{df['rsi'].iloc[last]:.2f}`\n"
                            f"💰 *24h Vol:* `${current_vol/1000000:.2f}M`\n"
                            f"🔊 *Vol Spike:* `{(df['v'].iloc[last]/df['vol_sma'].iloc[last]):.2f}x` \n\n"
                            f"🔗 [TradingView](https://www.tradingview.com/chart/?symbol=BITGET:{symbol.replace('/', '')})"
                        )
                        send_telegram(msg)
                        signals_found += 1
                    
                    total_checked += 1
                    time.sleep(0.25)

                except Exception as e:
                    print(f"Error {symbol} {tf}: {e}")

        finish_now = datetime.now().strftime('%H:%M:%S')
        send_telegram(f"✅ *Scan Selesai ({finish_now})*\nTotal: `{total_checked}` | Sinyal: `{signals_found}`")

    except Exception as e:
        send_telegram(f"❌ *Bot Error:* {str(e)}")

if __name__ == "__main__":
    scan_bitget()
