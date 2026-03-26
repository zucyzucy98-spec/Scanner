import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import os
import time
from datetime import datetime

# --- KONFIGURASI ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
MIN_VOLUME_USDT = 500000 

def send_telegram(message):
    if not TOKEN or not CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        params = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
        requests.get(url, params=params)
    except Exception as e:
        print(f"Error Telegram: {e}")

def scan_bitget():
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
        
        # 2. Filter Koin
        filtered = [t for t in tickers.values() if '/USDT' in t['symbol'] and t.get('quoteVolume', 0) >= MIN_VOLUME_USDT]
        sorted_tickers = sorted(filtered, key=lambda x: x['quoteVolume'], reverse=True)
        top_symbols = [t['symbol'] for t in sorted_tickers[:50]]
        
        if not top_symbols:
            send_telegram("⚠️ Tidak ada koin lolos filter volume.")
            return

        signals_found = 0
        total_checked = 0

        for symbol in top_symbols:
            for tf in ['1h', '4h']:
                try:
                    # Ambil data lebih banyak (100) untuk memastikan indikator terisi
                    bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=100)
                    
                    # --- VALIDATION GATE 1: Cek kecukupan data ---
                    if not bars or len(bars) < 35:
                        print(f"⏩ Skip {symbol} {tf}: Data tidak cukup ({len(bars)} candle)")
                        continue 
                    
                    df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    
                    # --- VALIDATION GATE 2: Hitung Indikator ---
                    # Hitung BB
                    bb = ta.bbands(df['c'], length=20, std=2)
                    # Hitung RSI
                    rsi_series = ta.rsi(df['c'], length=14)
                    # Hitung MACD
                    macd_df = ta.macd(df['c'])

                    # Pastikan semua kolom indikator berhasil dibuat
                    if bb is None or rsi_series is None or macd_df is None:
                        print(f"⏩ Skip {symbol} {tf}: Gagal kalkulasi indikator")
                        continue

                    # Ambil nama kolom secara dinamis (menghindari error 'BBU_20_2.0')
                    u_band = bb.columns[2] # Biasanya BBU_20_2.0
                    l_band = bb.columns[0] # Biasanya BBL_20_2.0
                    m_band = bb.columns[1] # Biasanya BBM_20_2.0
                    macd_h  = macd_df.columns[1] # Biasanya MACDh_12_26_9

                    # --- MASUKKAN KE DATAFRAME ---
                    df['bb_width'] = (bb[u_band] - bb[l_band]) / bb[m_band]
                    df['vol_sma'] = ta.sma(df['v'], length=20)
                    df['rsi'] = rsi_series
                    df['macd_h'] = macd_df[macd_h]
                    
                    # --- LOGIKA STRATEGI ---
                    last = -1
                    is_squeeze = df['bb_width'].iloc[last] < df['bb_width'].tail(15).mean()
                    vol_breakout = df['v'].iloc[last] > (df['vol_sma'].iloc[last] * 1.5)
                    macd_bullish = df['macd_h'].iloc[last] > 0
                    not_overbought = df['rsi'].iloc[last] < 70

                    if is_squeeze and vol_breakout and macd_bullish and not_overbought:
                        curr_vol = [t['quoteVolume'] for t in sorted_tickers if t['symbol'] == symbol][0]
                        msg = (
                            f"🎯 *SETUP FOUND*\n\n"
                            f"💎 *Asset:* `{symbol}`\n"
                            f"⏱️ *TF:* `{tf}` | *RSI:* `{df['rsi'].iloc[last]:.2f}`\n"
                            f"💰 *Vol 24h:* `${curr_vol/1000000:.1f}M`\n"
                            f"🔗 [Chart](https://www.tradingview.com/chart/?symbol=BITGET:{symbol.replace('/', '')})"
                        )
                        send_telegram(msg)
                        signals_found += 1
                    
                    total_checked += 1
                    time.sleep(0.2) 

                except Exception as e:
                    print(f"⚠️ Kesalahan pada {symbol} {tf}: {str(e)}")
                    continue # Lanjut ke koin berikutnya jika satu error

        # --- LAPORAN ---
        finish_now = datetime.now().strftime('%H:%M:%S')
        send_telegram(f"✅ *Scan Selesai ({finish_now})*\nTotal Chart: `{total_checked}`\nSinyal: `{signals_found}`")

    except Exception as e:
        send_telegram(f"❌ *Global Error:* {str(e)}")

if __name__ == "__main__":
    scan_bitget()
