import os
import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time

# Ambil kredensial dari GitHub Secrets
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Error: Telegram Token atau Chat ID belum disetel!")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Gagal mengirim pesan: {e}")

def get_signal():
    # Inisialisasi Bitget dengan Rate Limit Enable
    exchange = ccxt.bitget({'enableRateLimit': True})
    
    print("🚀 Memulai screening di Bitget Spot...")
    
    try:
        exchange.load_markets()
        tickers = exchange.fetch_tickers()
        
        # Filter: Hanya Spot, Pair USDT, dan memiliki data Volume
        usdt_pairs = [
            t for t in tickers.values() 
            if '/USDT' in t['symbol'] 
            and 'type' in t['info'] and t['info']['type'] == 'spot'
            and t['quoteVolume'] is not None
        ]
        
        # Ambil Top 30 Koin berdasarkan Volume 24 jam
        top_volume_pairs = sorted(usdt_pairs, key=lambda x: x['quoteVolume'], reverse=True)[:30]
        symbols = [p['symbol'] for p in top_volume_pairs]
        
        print(f"🔎 Menscan {len(symbols)} koin teraktif...")

    except Exception as e:
        print(f"❌ Error API Bitget: {e}")
        return

    for symbol in symbols:
        for tf in ['1h', '4h']:
            try:
                # Ambil 100 candle terakhir (OHLCV)
                bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=100)
                if len(bars) < 50: continue
                
                df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
                
                # --- KALKULASI INDIKATOR ---
                # 1. Stochastic (5, 3, 3)
                stoch = ta.stoch(df['high'], df['low'], df['close'], k=5, d=3)
                df = pd.concat([df, stoch], axis=1)
                
                # 2. RSI (14)
                df['rsi'] = ta.rsi(df['close'], length=14)
                
                # 3. Volume Breakout (SMA 20)
                df['vol_sma'] = df['volume'].rolling(window=20).mean()

                curr = df.iloc[-1]
                prev = df.iloc[-2]

                # --- LOGIKA STRATEGI SPOT ---
                # A. Stoch Bullish Cross di area Oversold (< 30)
                stoch_k = curr['STOCHk_5_3_3']
                stoch_d = curr['STOCHd_5_3_3']
                stoch_cross = (prev['STOCHk_5_3_3'] < prev['STOCHd_5_3_3']) and (stoch_k > stoch_d)
                is_oversold = stoch_k < 30
                
                # B. Volume Breakout (Volume saat ini > 1.5x rata-rata)
                vol_ratio = curr['volume'] / curr['vol_sma']
                is_vol_breakout = vol_ratio > 1.5
                
                # C. Momentum RSI Sehat (> 45)
                rsi_val = curr['rsi']
                is_rsi_strong = rsi_val > 45

                # --- EKSEKUSI SINYAL ---
                if stoch_cross and is_oversold and is_vol_breakout and is_rsi_strong:
                    price = curr['close']
                    
                    msg = (
                        f"🔔 *BITGET SPOT SIGNAL FOUND!*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"💎 *Asset:* `{symbol}`\n"
                        f"🕒 *Timeframe:* `{tf}`\n"
                        f"💰 *Entry Price:* `{price}`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📊 *Indikator:* \n"
                        f"• RSI: `{rsi_val:.2f}` (Strong)\n"
                        f"• Stoch K/D: `{stoch_k:.1f}/{stoch_d:.1f}` (Cross Up)\n"
                        f"• Vol Ratio: `{vol_ratio:.2f}x` (Breakout!)\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🔗 [Buka Chart Bitget](https://www.bitget.com/spot/{symbol.replace('/', '_')})\n"
                        f"⚠️ _Gunakan Stop Loss & Bijak dalam Money Management._"
                    )
                    
                    print(f"✅ Sinyal ditemukan: {symbol} [{tf}]")
                    send_telegram(msg)
                
                # Delay agar tidak kena Rate Limit Bitget
                time.sleep(0.3)

            except Exception as e:
                print(f"⚠️ Skip {symbol} {tf}: {e}")
                continue

if __name__ == "__main__":
    get_signal()
