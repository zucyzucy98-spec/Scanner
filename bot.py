import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import os
from datetime import datetime

# Konfigurasi Telegram dari GitHub Secrets
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}&parse_mode=Markdown"
    try:
        requests.get(url)
    except Exception as e:
        print(f"Gagal kirim Telegram: {e}")

def run_screener():
    # Inisialisasi Bitget
    exchange = ccxt.bitget()
    
    try:
        # 1. Ambil Market & Filter Top 50 Volume (USDT Spot Pairs)
        tickers = exchange.fetch_tickers()
        # Filter: Hanya Spot (bukan Futures), hanya USDT, dan abaikan koin 'ST' (Special Treatment) jika ada
        usdt_pairs = [
            t for t in tickers.values() 
            if '/USDT' in t['symbol'] and ':' not in t['symbol']
        ]
        
        # Urutkan berdasarkan quoteVolume (Volume dalam USDT)
        sorted_tickers = sorted(usdt_pairs, key=lambda x: x['quoteVolume'] if x['quoteVolume'] else 0, reverse=True)[:50]
        symbols = [t['symbol'] for t in sorted_tickers]

        # --- Pesan Bot Aktif ---
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        tickers_list = ", ".join([s.replace('/USDT', '') for s in symbols])
        
        status_msg = (
            f"🤖 *Bitget Screener Aktif!*\n"
            f"⏰ Waktu: `{current_time}`\n"
            f"🔍 Memindai *50 Koin Top Volume di Bitget*:\n"
            f"_{tickers_list}_"
        )
        send_telegram(status_msg)

        signals = []

        # 2. Loop Scanning
        for symbol in symbols:
            try:
                # Ambil data 1H
                bars = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
                if len(bars) < 30: continue # Skip jika data kurang
                
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                # --- Kalkulasi Indikator ---
                # Bollinger Bands Width (BBW)
                bb = ta.bbands(df['c'], length=20, std=2)
                df['bbw'] = (bb['BBU_20_2.0'] - bb['BBL_20_2.0']) / bb['BBM_20_2.0']
                
                # Stochastic 5,3,3
                stoch = ta.stoch(df['h'], df['l'], df['c'], k=5, d=3, smooth_k=3)
                k = stoch['STOCHk_5_3_3'].iloc[-1]
                d = stoch['STOCHd_5_3_3'].iloc[-1]
                k_prev = stoch['STOCHk_5_3_3'].iloc[-2]
                d_prev = stoch['STOCHd_5_3_3'].iloc[-2]
                
                # Volume Breakout (1.5x SMA 20)
                vol_ma = ta.sma(df['v'], length=20).iloc[-1]
                curr_vol = df['v'].iloc[-1]

                # --- Logika Strategi ---
                # Squeeze: BBW terendah dalam 10 jam
                is_squeeze = df['bbw'].iloc[-1] <= df['bbw'].rolling(10).min().iloc[-1]
                # Volume: 1.5x rata-rata
                is_vol_break = curr_vol > (vol_ma * 1.5)
                # Stoch: Bullish Cross (K > D)
                is_stoch_cross = k > d and k_prev <= d_prev

                if is_squeeze and is_vol_break and is_stoch_cross:
                    signals.append(
                        f"🎯 *{symbol}*\n"
                        f"• Status: `Squeeze & Breakout` (Bitget)\n"
                        f"• Stoch K: `{k:.2f}`"
                    )

            except Exception as e:
                continue # Skip jika error pada satu koin

        # 3. Kirim Hasil
        if signals:
            full_msg = "🚀 *SIGNAL DITEMUKAN (BITGET):*\n\n" + "\n\n".join(signals)
            send_telegram(full_msg)
        else:
            send_telegram("✅ Scan Bitget selesai: Tidak ada sinyal kuat saat ini.")

    except Exception as e:
        send_telegram(f"⚠️ Error Utama: {str(e)}")

if __name__ == "__main__":
    run_screener()
