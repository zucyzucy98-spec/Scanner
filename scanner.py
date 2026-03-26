import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import os
import time
from datetime import datetime

# --- KONFIGURASI API (Ambil dari GitHub Secrets) ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        params = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": False}
        requests.get(url, params=params)
    except Exception as e:
        print(f"Error kirim Telegram: {e}")

def scan_bitget():
    # Inisialisasi Bitget
    exchange = ccxt.bitget({'enableRateLimit': True})
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] Memulai pemindaian Top 30 Volume di Bitget...")
    
    try:
        # 1. Ambil semua ticker untuk mencari Top Volume
        tickers = exchange.fetch_tickers()
        sorted_tickers = sorted(
            [t for t in tickers.values() if '/USDT' in t['symbol'] and t['quoteVolume'] is not None],
            key=lambda x: x['quoteVolume'], 
            reverse=True
        )
        
        top_symbols = [t['symbol'] for t in sorted_tickers[:30]]
        signals_found = 0

        for symbol in top_symbols:
            for tf in ['4h', '1d']:
                try:
                    # Ambil data OHLCV
                    bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=100)
                    df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    
                    # --- INDIKATOR ---
                    # Bollinger Bands & Squeeze logic
                    bb = ta.bbands(df['c'], length=20, std=2)
                    df['bb_width'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']
                    
                    # Volume SMA & RSI
                    df['vol_sma'] = ta.sma(df['v'], length=20)
                    df['rsi'] = ta.rsi(df['c'], length=14)
                    
                    # MACD
                    macd = ta.macd(df['c'])
                    
                    # --- LOGIKA FILTER ---
                    last = -1
                    # Squeeze: BB Width saat ini lebih rendah dari rata-rata 15 candle sebelumnya
                    is_squeeze = df['bb_width'].iloc[last] < df['bb_width'].tail(15).mean()
                    # Volume: 1.5x lipat rata-rata
                    vol_breakout = df['v'].iloc[last] > (df['vol_sma'].iloc[last] * 1.5)
                    # Momentum: Histogram MACD Positif (Warna Hijau)
                    macd_bullish = macd['MACDh_12_26_9'].iloc[last] > 0
                    # Safety: RSI tidak boleh di atas 70 (Overbought)
                    not_overbought = df['rsi'].iloc[last] < 70

                    if is_squeeze and vol_breakout and macd_bullish and not_overbought:
                        msg = (
                            f"🎯 *SIGNAL TERDETEKSI (BITGET)*\n\n"
                            f"💎 *Asset:* `{symbol}`\n"
                            f"⏱️ *Timeframe:* `{tf}`\n"
                            f"📊 *RSI:* `{df['rsi'].iloc[last]:.2f}`\n"
                            f"📈 *BB Width:* `{df['bb_width'].iloc[last]:.4f}` (Squeeze)\n"
                            f"🔊 *Vol Ratio:* `{(df['v'].iloc[last]/df['vol_sma'].iloc[last]):.2f}x` dari rata-rata\n\n"
                            f"🔗 [Buka Chart di TradingView](https://www.tradingview.com/chart/?symbol=BITGET:{symbol.replace('/', '')})"
                        )
                        send_telegram(msg)
                        signals_found += 1
                    
                    time.sleep(0.1) # Hindari rate limit

                except Exception as e:
                    print(f"Skip {symbol} {tf}: {e}")

        # Laporan Akhir (Logging)
        if signals_found == 0:
            send_telegram(f"✅ *Scan Selesai ({now})*\nStatus: Tidak ada setup yang memenuhi kriteria saat ini.")
        else:
            send_telegram(f"✅ *Scan Selesai ({now})*\nStatus: Menemukan {signals_found} potensi koin.")

    except Exception as e:
        send_telegram(f"❌ *Error pada Bot:* {str(e)}")

if __name__ == "__main__":
    scan_bitget()
