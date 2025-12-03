from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import APICredential
from core.constants import FINAL_DICTIONARY_OBJECT
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import redis
import json
import logging
from datetime import datetime
import pytz

# Constants
IST = pytz.timezone("Asia/Kolkata")
CANDLE_STREAM_KEY = getattr(settings, "BREAKOUT_CANDLE_STREAM", "candle_1m")
LIVE_OHLC_KEY = getattr(settings, "BREAKOUT_LIVE_OHLC_KEY", "live_ohlc_data")

logger = logging.getLogger('data_engine')

class Command(BaseCommand):
    help = 'Runs Central Data Engine: Aggregates Ticks -> 1 Min Candles -> Redis Stream'

    def handle(self, *args, **options):
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        creds = APICredential.objects.first()
        
        if not creds:
            self.stdout.write(self.style.ERROR('No Credentials Found'))
            return

        # 1. Map Tokens to Symbols using the Universe Dictionary
        # Reverse map: Token -> Symbol (needed for incoming WebSocket data)
        # Note: FINAL_DICTIONARY_OBJECT values are strings in constants.py, ensure consistency
        token_map = {str(v): k for k, v in FINAL_DICTIONARY_OBJECT.items()}
        
        candle_buffer = {}

        sws = SmartWebSocketV2(creds.access_token, creds.api_key, creds.client_code, creds.feed_token)

        def get_current_minute_str():
            return datetime.now(IST).strftime('%Y-%m-%d %H:%M:00%z')

        def flush_candle(token, data):
            symbol = token_map.get(token, token)
            payload = {
                "symbol": symbol,
                "token": token,
                "open": data['open'],
                "high": data['high'],
                "low": data['low'],
                "close": data['close'],
                "volume": data['volume'],
                "ts": data['ts']
            }
            # Publish to Stream
            r.xadd(CANDLE_STREAM_KEY, {'data': json.dumps(payload)})
            
            # Update Live OHLC snapshot
            current_snapshot = r.get(LIVE_OHLC_KEY)
            snapshot_dict = json.loads(current_snapshot) if current_snapshot else {}
            
            snapshot_dict[symbol] = {"ltp": data['close'], "high": data['high'], "low": data['low']}
            r.set(LIVE_OHLC_KEY, json.dumps(snapshot_dict))
            
            # Optional: Log only occasionally to reduce noise
            # logger.info(f"Generated Candle: {symbol}")

        def on_data(wsapp, message):
            try:
                token = message.get('token')
                
                # Filter: Process ONLY if token is in our Universe
                if token not in token_map:
                    return

                # Parse LTP (Handle potential paise conversion if API changes, standard is usually Rupees now)
                ltp = float(message.get('last_traded_price'))
                daily_vol = message.get('vol_traded', 0) 
                
                if not ltp:
                    return

                current_min = get_current_minute_str()
                
                if token not in candle_buffer:
                    candle_buffer[token] = {
                        'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp,
                        'volume': daily_vol, 'ts': current_min, 'start_vol': daily_vol
                    }
                
                candle = candle_buffer[token]

                if candle['ts'] != current_min:
                    # Finalize previous candle
                    prev_candle_data = candle.copy()
                    prev_candle_data['volume'] = daily_vol - candle['start_vol']
                    flush_candle(token, prev_candle_data)
                    
                    # Start new candle
                    candle_buffer[token] = {
                        'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp,
                        'volume': daily_vol, 'ts': current_min, 'start_vol': daily_vol
                    }
                else:
                    candle['high'] = max(candle['high'], ltp)
                    candle['low'] = min(candle['low'], ltp)
                    candle['close'] = ltp

            except Exception as e:
                # Suppress minor parsing errors to keep engine running
                pass

        def on_open(wsapp):
            logger.info("WebSocket Connected")
            
            # Subscribe ONLY to the specific Universe
            tokens = list(token_map.keys())
            
            # Angel WebSocket limit per request is often 50-100. Split if necessary.
            # But library might handle batching. Sending as one list for now.
            sws.subscribe("correlation_id", 1, [{"exchangeType": 1, "tokens": tokens}])
            logger.info(f"Subscribed to {len(tokens)} tokens from Universe.")

        def on_error(wsapp, error):
            logger.error(f"WebSocket Error: {error}")

        sws.on_data = on_data
        sws.on_open = on_open
        sws.on_error = on_error

        self.stdout.write(self.style.SUCCESS(f'Starting Data Engine for {len(token_map)} stocks...'))
        sws.connect()