from django.core.management.base import BaseCommand
from django.conf import settings
from tradeapp.models import APICredential
from tradeapp.constants import FINAL_DICTIONARY_OBJECT
from tradeapp.angel_utils import get_redis_client
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import json
import logging
import time
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")
CANDLE_STREAM_KEY = getattr(settings, "BREAKOUT_CANDLE_STREAM", "candle_1m")
LIVE_OHLC_KEY = getattr(settings, "BREAKOUT_LIVE_OHLC_KEY", "live_ohlc_data")

# Configure Logging to output to Heroku Console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('data_engine')

class Command(BaseCommand):
    help = 'Runs Central Data Engine with Detail Logging'

    def handle(self, *args, **options):
        r = get_redis_client()
        logger.info("--- DATA ENGINE INITIALIZED ---")
        
        while True:
            try:
                self.run_socket_session(r)
            except Exception as e:
                logger.error(f"CRITICAL ENGINE CRASH: {e}")
            
            logger.warning('Engine stopped. Restarting in 5 seconds...')
            time.sleep(5)

    def run_socket_session(self, r):
        creds = APICredential.objects.first()
        if not creds or not creds.access_token or not creds.feed_token:
            logger.warning('Waiting for valid tokens... (Login via Dashboard)')
            return

        token_map = {str(v): k for k, v in FINAL_DICTIONARY_OBJECT.items()}
        candle_buffer = {}

        try:
            # Log masked token for debugging
            logger.info(f"Initializing WebSocket with FeedToken: {creds.feed_token[:10]}...")
            sws = SmartWebSocketV2(creds.access_token, creds.api_key, creds.client_code, creds.feed_token)
        except Exception as e:
            logger.error(f"WebSocket Init Failed: {e}")
            return

        def flush_candle(token, data):
            symbol = token_map.get(token, token)
            payload = {
                "symbol": symbol, "token": token, "open": data['open'],
                "high": data['high'], "low": data['low'], "close": data['close'],
                "volume": data['volume'], "ts": data['ts']
            }
            # Push to Stream
            r.xadd(CANDLE_STREAM_KEY, {'data': json.dumps(payload)})
            
            # Update Snapshot
            current_snapshot = r.get(LIVE_OHLC_KEY)
            snapshot_dict = json.loads(current_snapshot) if current_snapshot else {}
            snapshot_dict[symbol] = {"ltp": data['close'], "high": data['high'], "low": data['low']}
            r.set(LIVE_OHLC_KEY, json.dumps(snapshot_dict))
            
            # LOGGING: Show activity (Critical for debugging)
            logger.info(f"🕯️ CANDLE: {symbol} | Time: {data['ts']} | Close: {data['close']}")

        def on_data(wsapp, message):
            try:
                token = message.get('token')
                if token not in token_map: return

                ltp = float(message.get('last_traded_price', 0))
                daily_vol = float(message.get('vol_traded', 0)) 
                
                if ltp == 0: return

                current_min = datetime.now(IST).strftime('%Y-%m-%d %H:%M:00%z')
                
                if token not in candle_buffer:
                    candle_buffer[token] = {
                        'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp,
                        'volume': daily_vol, 'ts': current_min, 'start_vol': daily_vol
                    }
                
                candle = candle_buffer[token]

                # Minute Change Detection
                if candle['ts'] != current_min:
                    prev_candle = candle.copy()
                    prev_candle['volume'] = daily_vol - candle['start_vol']
                    flush_candle(token, prev_candle)
                    
                    # Reset for new minute
                    candle_buffer[token] = {
                        'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp,
                        'volume': daily_vol, 'ts': current_min, 'start_vol': daily_vol
                    }
                else:
                    # Update High/Low/Close
                    candle['high'] = max(candle['high'], ltp)
                    candle['low'] = min(candle['low'], ltp)
                    candle['close'] = ltp
                    
            except Exception as e:
                logger.error(f"Tick Process Error: {e}")

        def on_open(wsapp):
            logger.info("✅ WebSocket Connected Successfully")
            tokens = list(token_map.keys())
            sws.subscribe("correlation_id", 2, [{"exchangeType": 1, "tokens": tokens}])
            logger.info(f"📡 Subscribed to {len(tokens)} stocks in MODE 2 (Quote).")

        def on_error(wsapp, error):
            logger.error(f"❌ WebSocket Error: {error}")

        sws.on_data = on_data
        sws.on_open = on_open
        sws.on_error = on_error
        sws.connect()