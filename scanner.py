import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time

# --- KONFIGURASI ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
LIMIT_COINS = 50 
# Bagian yang diubah: Menambahkan 1h dan 4h
TIMEFRAMES = ['1h', '4h'] 

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error kirim Telegram: {e}")

def get_top_volume_bitget(exchange):
    print("Mengambil Top 50 Volume di Bitget...")
    tickers = exchange.fetch_tickers()
    usdt_pairs = [
        {'symbol': t['symbol'], 'volume': t['quoteVolume']} 
        for t in tickers.values() 
        if '/USDT' in t['symbol'] and t['quoteVolume'] is not None
    ]
    # Sortir dari volume tertinggi
    sorted_pairs = sorted(usdt_pairs, key=lambda x: x['volume'], reverse=True)
    return [p['symbol'] for p in sorted_pairs[:LIMIT_COINS]]

def fetch_signals(exchange, symbol, tf):
    try:
        # Mengambil data candle (OHLCV)
        bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=100)
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        
        # 1. RSI (14)
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        # 2. Stochastic (5, 3, 3)
        stoch = ta.stoch(df['high'], df['low'], df['close'], k=5, d=3, smooth_k=3)
        df = pd.concat([df, stoch], axis=1)
        
        # 3. Volume Breakout (Volume > 1.5x Rata-rata)
        df['vol_ma'] = ta.sma(df['volume'], length=20)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # LOGIKA STRATEGI
        stoch_k, stoch_d = last['STOCHk_5_3_3'], last['STOCHd_5_3_3']
        prev_k, prev_d = prev['STOCHk_5_3_3'], prev['STOCHd_5_3_3']
        
        # Golden Cross Stochastic
        is_stoch_cross = (prev_k < prev_d) and (stoch_k > stoch_d)
        
        # Volume Breakout (Filter diperketat untuk TF rendah)
        vol_multiplier = 2.0 if tf == '1h' else 1.5
        is_vol_breakout = last['volume'] > (last['vol_ma'] * vol_multiplier)
        
        # RSI Filter
        is_rsi_ok = last['rsi'] > 50

        if is_stoch_cross and is_vol_breakout and is_rsi_ok:
            return {
                "signal": True,
                "price": last['close'],
                "rsi": round(last['rsi'], 2),
                "stoch_k": round(stoch_k, 2)
            }
    except Exception as e:
        print(f"Skip {symbol} {tf}: {e}")
    
    return {"signal": False}

def main():
    bitget = ccxt.bitget()
    top_symbols = get_top_volume_bitget(bitget)
    
    print(f"Memulai Scan {len(top_symbols)} koin pada {TIMEFRAMES}...")
    
    for symbol in top_symbols:
        for tf in TIMEFRAMES:
            # Tambahkan delay kecil untuk menghindari Rate Limit Bitget
            time.sleep(0.2) 
            
            result = fetch_signals(bitget, symbol, tf)
            if result['signal']:
                # Label emoji berbeda untuk membedakan TF di Telegram
                tf_emoji = "⚡" if tf == '1h' else "⏳"
                
                pesan = (
                    f"{tf_emoji} *BITGET SIGNAL FOUND!*\n\n"
                    f"💎 *Asset:* {symbol}\n"
                    f"⏰ *Timeframe:* {tf}\n"
                    f"💰 *Price:* {result['price']}\n"
                    f"📈 *RSI:* {result['rsi']}\n"
                    f"📊 *Stoch K:* {result['stoch_k']}\n\n"
                    f"✅ *Volume & Momentum OK*"
                )
                print(f"Sinyal ditemukan: {symbol} {tf}")
                send_telegram(pesan)

if __name__ == "__main__":
    main()
