# # from django.core.management.base import BaseCommand
# # from django.conf import settings
# # from tradeapp.models import APICredential
# # from tradeapp.constants import FINAL_DICTIONARY_OBJECT
# # from tradeapp.angel_utils import get_redis_client
# # from SmartApi.smartWebSocketV2 import SmartWebSocketV2
# # import json
# # import logging
# # import time
# # from datetime import datetime
# # import pytz

# # IST = pytz.timezone("Asia/Kolkata")
# # CANDLE_STREAM_KEY = getattr(settings, "BREAKOUT_CANDLE_STREAM", "candle_1m")
# # LIVE_OHLC_KEY = getattr(settings, "BREAKOUT_LIVE_OHLC_KEY", "live_ohlc_data")

# # logger = logging.getLogger('data_engine')

# # class Command(BaseCommand):
# #     help = 'Runs Central Data Engine: Aggregates Ticks -> 1 Min Candles -> Redis Stream'

# #     def handle(self, *args, **options):
# #         r = get_redis_client()
        
# #         # 1. Wait for Credentials loop
# #         while True:
# #             creds = APICredential.objects.first()
# #             if creds and creds.access_token and creds.feed_token:
# #                 break
# #             self.stdout.write(self.style.WARNING('Waiting for valid Access Token & Feed Token...'))
# #             time.sleep(5)

# #         token_map = {str(v): k for k, v in FINAL_DICTIONARY_OBJECT.items()}
# #         candle_buffer = {}

# #         # 2. Initialize WebSocket (Now safe because we checked tokens)
# #         try:
# #             sws = SmartWebSocketV2(creds.access_token, creds.api_key, creds.client_code, creds.feed_token)
# #         except Exception as e:
# #             logger.error(f"Failed to init WebSocket: {e}")
# #             return

# #         def get_current_minute_str():
# #             return datetime.now(IST).strftime('%Y-%m-%d %H:%M:00%z')

# #         def flush_candle(token, data):
# #             symbol = token_map.get(token, token)
# #             payload = {
# #                 "symbol": symbol,
# #                 "token": token,
# #                 "open": data['open'],
# #                 "high": data['high'],
# #                 "low": data['low'],
# #                 "close": data['close'],
# #                 "volume": data['volume'],
# #                 "ts": data['ts']
# #             }
# #             r.xadd(CANDLE_STREAM_KEY, {'data': json.dumps(payload)})
            
# #             current_snapshot = r.get(LIVE_OHLC_KEY)
# #             snapshot_dict = json.loads(current_snapshot) if current_snapshot else {}
            
# #             snapshot_dict[symbol] = {"ltp": data['close'], "high": data['high'], "low": data['low']}
# #             r.set(LIVE_OHLC_KEY, json.dumps(snapshot_dict))

# #         def on_data(wsapp, message):
# #             try:
# #                 token = message.get('token')
# #                 if token not in token_map:
# #                     return

# #                 ltp = float(message.get('last_traded_price'))
# #                 daily_vol = message.get('vol_traded', 0) 
                
# #                 if not ltp:
# #                     return

# #                 current_min = get_current_minute_str()
                
# #                 if token not in candle_buffer:
# #                     candle_buffer[token] = {
# #                         'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp,
# #                         'volume': daily_vol, 'ts': current_min, 'start_vol': daily_vol
# #                     }
                
# #                 candle = candle_buffer[token]

# #                 if candle['ts'] != current_min:
# #                     prev_candle_data = candle.copy()
# #                     prev_candle_data['volume'] = daily_vol - candle['start_vol']
# #                     flush_candle(token, prev_candle_data)
                    
# #                     candle_buffer[token] = {
# #                         'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp,
# #                         'volume': daily_vol, 'ts': current_min, 'start_vol': daily_vol
# #                     }
# #                 else:
# #                     candle['high'] = max(candle['high'], ltp)
# #                     candle['low'] = min(candle['low'], ltp)
# #                     candle['close'] = ltp

# #             except Exception as e:
# #                 pass

# #         def on_open(wsapp):
# #             logger.info("WebSocket Connected")
# #             tokens = list(token_map.keys())
# #             sws.subscribe("correlation_id", 1, [{"exchangeType": 1, "tokens": tokens}])
# #             logger.info(f"Subscribed to {len(tokens)} tokens from Universe.")

# #         def on_error(wsapp, error):
# #             logger.error(f"WebSocket Error: {error}")

# #         sws.on_data = on_data
# #         sws.on_open = on_open
# #         sws.on_error = on_error

# #         self.stdout.write(self.style.SUCCESS(f'Starting Data Engine for {len(token_map)} stocks...'))
# #         sws.connect()

# from django.core.management.base import BaseCommand
# from django.conf import settings
# from tradeapp.models import APICredential
# from tradeapp.constants import FINAL_DICTIONARY_OBJECT
# from tradeapp.angel_utils import get_redis_client
# from SmartApi.smartWebSocketV2 import SmartWebSocketV2
# import json
# import logging
# import time
# from datetime import datetime
# import pytz

# IST = pytz.timezone("Asia/Kolkata")
# CANDLE_STREAM_KEY = getattr(settings, "BREAKOUT_CANDLE_STREAM", "candle_1m")
# LIVE_OHLC_KEY = getattr(settings, "BREAKOUT_LIVE_OHLC_KEY", "live_ohlc_data")

# logger = logging.getLogger('data_engine')

# class Command(BaseCommand):
#     help = 'Runs Central Data Engine: Aggregates Ticks -> 1 Min Candles -> Redis Stream'

#     def handle(self, *args, **options):
#         # 1. Setup Redis
#         r = get_redis_client()
        
#         # 2. Infinite Resilience Loop (Prevents Heroku Crashes)
#         while True:
#             try:
#                 self.run_socket_session(r)
#             except Exception as e:
#                 logger.error(f"Data Engine Crash: {e}")
            
#             # If we get here, the socket closed or crashed. Wait before retrying.
#             self.stdout.write(self.style.WARNING('Engine stopped. Restarting in 5 seconds...'))
#             time.sleep(5)

#     def run_socket_session(self, r):
#         # 1. Fetch Credentials
#         creds = APICredential.objects.first()
#         if not creds or not creds.access_token or not creds.feed_token:
#             self.stdout.write(self.style.WARNING('Waiting for valid tokens...'))
#             return # Returns to main loop to sleep 5s

#         # 2. Setup Token Map
#         token_map = {str(v): k for k, v in FINAL_DICTIONARY_OBJECT.items()}
#         candle_buffer = {}

#         # 3. Initialize WebSocket
#         try:
#             sws = SmartWebSocketV2(creds.access_token, creds.api_key, creds.client_code, creds.feed_token)
#         except Exception as e:
#             logger.error(f"Init Error: {e}")
#             return

#         def flush_candle(token, data):
#             symbol = token_map.get(token, token)
#             payload = {
#                 "symbol": symbol, "token": token, "open": data['open'],
#                 "high": data['high'], "low": data['low'], "close": data['close'],
#                 "volume": data['volume'], "ts": data['ts']
#             }
#             # Push to Stream
#             r.xadd(CANDLE_STREAM_KEY, {'data': json.dumps(payload)})
            
#             # Update Live Snapshot
#             current_snapshot = r.get(LIVE_OHLC_KEY)
#             snapshot_dict = json.loads(current_snapshot) if current_snapshot else {}
#             snapshot_dict[symbol] = {"ltp": data['close'], "high": data['high'], "low": data['low']}
#             r.set(LIVE_OHLC_KEY, json.dumps(snapshot_dict))

#         def on_data(wsapp, message):
#             try:
#                 token = message.get('token')
#                 if token not in token_map: return

#                 ltp = float(message.get('last_traded_price'))
#                 daily_vol = message.get('vol_traded', 0) 
                
#                 if not ltp: return

#                 current_min = datetime.now(IST).strftime('%Y-%m-%d %H:%M:00%z')
                
#                 if token not in candle_buffer:
#                     candle_buffer[token] = {
#                         'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp,
#                         'volume': daily_vol, 'ts': current_min, 'start_vol': daily_vol
#                     }
                
#                 candle = candle_buffer[token]

#                 if candle['ts'] != current_min:
#                     prev_candle = candle.copy()
#                     prev_candle['volume'] = daily_vol - candle['start_vol']
#                     flush_candle(token, prev_candle)
                    
#                     candle_buffer[token] = {
#                         'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp,
#                         'volume': daily_vol, 'ts': current_min, 'start_vol': daily_vol
#                     }
#                 else:
#                     candle['high'] = max(candle['high'], ltp)
#                     candle['low'] = min(candle['low'], ltp)
#                     candle['close'] = ltp
#             except Exception:
#                 pass

#         def on_open(wsapp):
#             logger.info("WebSocket Connected")
#             tokens = list(token_map.keys())
#             # Subscribe to NSE Equity
#             sws.subscribe("correlation_id", 1, [{"exchangeType": 1, "tokens": tokens}])
#             self.stdout.write(self.style.SUCCESS(f'Subscribed to {len(tokens)} stocks.'))

#         def on_error(wsapp, error):
#             logger.error(f"WebSocket Error: {error}")

#         # Assign callbacks
#         sws.on_data = on_data
#         sws.on_open = on_open
#         sws.on_error = on_error

#         # Start Connection (Blocks until connection closes)
#         sws.connect()
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

logger = logging.getLogger('data_engine')

class Command(BaseCommand):
    help = 'Runs Central Data Engine: Aggregates Ticks -> 1 Min Candles -> Redis Stream'

    def handle(self, *args, **options):
        r = get_redis_client()
        while True:
            try:
                self.run_socket_session(r)
            except Exception as e:
                logger.error(f"Data Engine Crash: {e}")
            self.stdout.write(self.style.WARNING('Engine stopped. Restarting in 5 seconds...'))
            time.sleep(5)

    def run_socket_session(self, r):
        creds = APICredential.objects.first()
        if not creds or not creds.access_token or not creds.feed_token:
            self.stdout.write(self.style.WARNING('Waiting for valid tokens...'))
            return

        token_map = {str(v): k for k, v in FINAL_DICTIONARY_OBJECT.items()}
        candle_buffer = {}

        try:
            sws = SmartWebSocketV2(creds.access_token, creds.api_key, creds.client_code, creds.feed_token)
        except Exception as e:
            logger.error(f"Init Error: {e}")
            return

        def flush_candle(token, data):
            symbol = token_map.get(token, token)
            payload = {
                "symbol": symbol, "token": token, "open": data['open'],
                "high": data['high'], "low": data['low'], "close": data['close'],
                "volume": data['volume'], "ts": data['ts']
            }
            r.xadd(CANDLE_STREAM_KEY, {'data': json.dumps(payload)})
            
            current_snapshot = r.get(LIVE_OHLC_KEY)
            snapshot_dict = json.loads(current_snapshot) if current_snapshot else {}
            snapshot_dict[symbol] = {"ltp": data['close'], "high": data['high'], "low": data['low']}
            r.set(LIVE_OHLC_KEY, json.dumps(snapshot_dict))

        def on_data(wsapp, message):
            try:
                token = message.get('token')
                if token not in token_map: return

                # In Mode 2, these fields are available
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

                if candle['ts'] != current_min:
                    prev_candle = candle.copy()
                    # Calculate volume for this minute (Current Cumulative - Start Cumulative)
                    prev_candle['volume'] = daily_vol - candle['start_vol']
                    flush_candle(token, prev_candle)
                    
                    candle_buffer[token] = {
                        'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp,
                        'volume': daily_vol, 'ts': current_min, 'start_vol': daily_vol
                    }
                else:
                    candle['high'] = max(candle['high'], ltp)
                    candle['low'] = min(candle['low'], ltp)
                    candle['close'] = ltp
            except Exception:
                pass

        def on_open(wsapp):
            logger.info("WebSocket Connected")
            tokens = list(token_map.keys())
            # FIX: Subscribe with Mode 2 (Quote) to get OHLC + Volume
            # Mode 1 (LTP) does not provide enough data for candles
            sws.subscribe("correlation_id", 2, [{"exchangeType": 1, "tokens": tokens}])
            self.stdout.write(self.style.SUCCESS(f'Subscribed to {len(tokens)} stocks (Mode 2: Quote).'))

        def on_error(wsapp, error):
            logger.error(f"WebSocket Error: {error}")

        sws.on_data = on_data
        sws.on_open = on_open
        sws.on_error = on_error
        sws.connect()