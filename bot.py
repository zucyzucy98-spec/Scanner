import os
import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time

# 1. Konfigurasi API & Telegram (Diambil dari GitHub Secrets)
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("❌ Error: Telegram Token atau Chat ID belum diset di GitHub Secrets!")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"❌ Gagal kirim Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Error koneksi Telegram: {e}")

def get_signal():
    # Menggunakan Bitget dengan optimasi Rate Limit
    exchange = ccxt.bitget({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'} # Memastikan default ke pasar Spot
    })
    
    print("🚀 Memulai screening di Bitget Spot...")
    
    try:
        exchange.load_markets()
        tickers = exchange.fetch_tickers()
        
        # Filter Market: Mencari pair USDT yang aktif (Bukan koin mati/volume 0)
        usdt_pairs = []
        for symbol, t in tickers.items():
            # Filter hanya pair USDT, pastikan bukan Futures/Contract
            if '/USDT' in symbol and ':' not in symbol:
                vol = t.get('quoteVolume')
                if vol and vol > 0:
                    usdt_pairs.append(t)
        
        # Ambil Top 50 koin berdasarkan volume 24 jam untuk memperluas pencarian
        top_volume_pairs = sorted(usdt_pairs, key=lambda x: x['quoteVolume'], reverse=True)[:50]
        symbols = [p['symbol'] for p in top_volume_pairs]
        
        if not symbols:
            print("❌ Tidak ada koin USDT yang ditemukan di Bitget.")
            return

        print(f"🔎 Menscan {len(symbols)} koin teraktif di Bitget...")

    except Exception as e:
        print(f"❌ Error saat mengambil data market: {e}")
        return

    # Loop setiap koin untuk TF 1h dan 4h
    for symbol in symbols:
        for tf in ['1h', '4h']:
            try:
                # Ambil data Candle (OHLCV)
                bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=100)
                if len(bars) < 50:
                    continue
                
                df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
                
                # --- KALKULASI INDIKATOR (PANDAS_TA) ---
                # 1. Stochastic (5, 3, 3)
                stoch = ta.stoch(df['high'], df['low'], df['close'], k=5, d=3)
                df = pd.concat([df, stoch], axis=1)
                
                # 2. RSI (14)
                df['rsi'] = ta.rsi(df['close'], length=14)
                
                # 3. Volume SMA (20) untuk deteksi Breakout
                df['vol_sma'] = df['volume'].rolling(window=20).mean()

                # Ambil data Candle terakhir (Current) dan sebelumnya (Previous)
                curr = df.iloc[-1]
                prev = df.iloc[-2]

                # --- LOGIKA STRATEGI ---
                # A. Stochastic Cross Up di area Oversold (< 30)
                stoch_k = curr['STOCHk_5_3_3']
                stoch_d = curr['STOCHd_5_3_3']
                stoch_cross = (prev['STOCHk_5_3_3'] < prev['STOCHd_5_3_3']) and (stoch_k > stoch_d)
                is_oversold = stoch_k < 30
                
                # B. Volume Breakout (Volume > 1.5x rata-rata 20 candle terakhir)
                vol_ratio = curr['volume'] / curr['vol_sma']
                is_vol_breakout = vol_ratio > 1.5
                
                # C. RSI Momentum Sehat (> 45)
                rsi_val = curr['rsi']
                is_rsi_strong = rsi_val > 45

                # JIKA SEMUA KONDISI TERPENUHI
                if stoch_cross and is_oversold and is_vol_breakout and is_rsi_strong:
                    price = curr['close']
                    
                    msg = (
                        f"🔔 *BITGET SPOT SIGNAL DETECTED*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"💎 *Asset:* `{symbol}`\n"
                        f"🕒 *Timeframe:* `{tf}`\n"
                        f"💰 *Entry Price:* `{price}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📊 *Detail Indikator:*\n"
                        f"• RSI: `{rsi_val:.2f}` (Strong Momentum)\n"
                        f"• Stoch K/D: `{stoch_k:.1f}/{stoch_d:.1f}` (Bullish Cross)\n"
                        f"• Vol Ratio: `{vol_ratio:.2f}x` (Volume Spike!)\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔗 [Buka Chart di Bitget](https://www.bitget.com/spot/{symbol.replace('/', '_')})\n"
                        f"⚠️ _Gunakan Stop Loss & Bijak dalam MM._"
                    )
                    
                    print(f"✅ SIGNAL FOUND: {symbol} [{tf}]")
                    send_telegram(msg)
                
                # Delay 0.3 detik agar tidak kena blokir API (Rate Limit)
                time.sleep(0.3)

            except Exception as e:
                # print(f"⚠️ Error pada {symbol} {tf}: {e}") # Opsional: Aktifkan jika ingin debug
                continue

if __name__ == "__main__":
    get_signal()
    print("✅ Screening Selesai.")
