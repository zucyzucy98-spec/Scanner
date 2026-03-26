import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import os
import time
from datetime import datetime

# --- KONFIGURASI API ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
# Turunkan ke 500rb agar bot pasti mendapat koin saat market sepi
MIN_VOLUME_USDT = 1000000 

def send_telegram(message):
    if not TOKEN or not CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        params = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
        requests.get(url, params=params)
    except Exception as e:
        print(f"Error Telegram: {e}")

def scan_bitget():
    # TAMBAHAN PENTING: Paksa ke Market SPOT
    exchange = ccxt.bitget({
        'enableRateLimit': True, 
        'timeout': 30000,
        'options': {'defaultType': 'spot'} 
    })
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] Memulai pemindaian...")

    try:
        # 1. Ambil Ticker
        tickers = exchange.fetch_tickers()
        print(f"Berhasil menarik {len(tickers)} ticker dari Bitget.")

        # 2. Filter Koin (Hanya USDT & Volume > Min)
        filtered = []
        for symbol, t in tickers.items():
            if '/USDT' in symbol and t.get('quoteVolume') is not None:
                if t['quoteVolume'] >= MIN_VOLUME_USDT:
                    filtered.append(t)
        
        # Urutkan Volume Terbesar
        sorted_tickers = sorted(filtered, key=lambda x: x['quoteVolume'], reverse=True)
        top_symbols = [t['symbol'] for t in sorted_tickers[:50]]
        
        print(f"Koin lolos filter volume: {len(top_symbols)}")

        if not top_symbols:
            send_telegram(f"⚠️ *Peringatan:* Tidak ada koin yang lolos filter volume ${MIN_VOLUME_USDT:,}")
            return

        signals_found = 0
        total_checked = 0

        for symbol in top_symbols:
            for tf in ['1h', '4h']:
                try:
                    bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=100)
                    if len(bars) < 35: continue 
                    
                    df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    
                    # --- INDIKATOR ---
                    bb = ta.bbands(df['c'], length=20, std=2)
                    df['bb_width'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']
                    df['vol_sma'] = ta.sma(df['v'], length=20)
                    df['rsi'] = ta.rsi(df['c'], length=14)
                    macd = ta.macd(df['c'])
                    
                    # --- LOGIKA ---
                    last = -1
                    is_squeeze = df['bb_width'].iloc[last] < df['bb_width'].tail(15).mean()
                    vol_breakout = df['v'].iloc[last] > (df['vol_sma'].iloc[last] * 1.5)
                    macd_bullish = macd['MACDh_12_26_9'].iloc[last] > 0
                    not_overbought = df['rsi'].iloc[last] < 70

                    if is_squeeze and vol_breakout and macd_bullish and not_overbought:
                        curr_vol = [t['quoteVolume'] for t in sorted_tickers if t['symbol'] == symbol][0]
                        msg = (
                            f"🎯 *NEW SETUP FOUND*\n\n"
                            f"💎 *Asset:* `{symbol}`\n"
                            f"⏱️ *TF:* `{tf}` | *RSI:* `{df['rsi'].iloc[last]:.2f}`\n"
                            f"💰 *Vol 24h:* `${curr_vol/1000000:.1f}M`\n"
                            f"🔊 *Spike:* `{(df['v'].iloc[last]/df['vol_sma'].iloc[last]):.1f}x` \n\n"
                            f"🔗 [Chart](https://www.tradingview.com/chart/?symbol=BITGET:{symbol.replace('/', '')})"
                        )
                        send_telegram(msg)
                        signals_found += 1
                    
                    total_checked += 1
                    time.sleep(0.2) 

                except Exception as e:
                    print(f"Gagal memproses {symbol} {tf}: {e}")

        # --- LAPORAN AKHIR ---
        finish_now = datetime.now().strftime('%H:%M:%S')
        send_telegram(f"✅ *Scan Selesai ({finish_now})*\nTotal Chart: `{total_checked}`\nSinyal: `{signals_found}`")

    except Exception as e:
        send_telegram(f"❌ *Bot Error:* {str(e)}")

if __name__ == "__main__":
    scan_bitget()
