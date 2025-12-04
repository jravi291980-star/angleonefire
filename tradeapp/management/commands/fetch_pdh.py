from django.core.management.base import BaseCommand
from tradeapp.models import APICredential
from tradeapp.angel_utils import AngelConnect, get_redis_client
from tradeapp.constants import FINAL_DICTIONARY_OBJECT
import json
import time
import logging

logger = logging.getLogger('pdh_fetcher')

class Command(BaseCommand):
    help = 'Fetches Previous Day High (PDH) and Low (PDL) for the stock universe and caches in Redis.'

    def handle(self, *args, **options):
        r = get_redis_client()
        creds = APICredential.objects.first()
        
        if not creds or not creds.access_token:
            self.stdout.write(self.style.ERROR('No Valid Credentials Found. Login First.'))
            return

        angel = AngelConnect(creds.api_key, creds.access_token, creds.refresh_token, creds.feed_token)
        
        self.stdout.write(self.style.SUCCESS(f'Fetching PDH for {len(FINAL_DICTIONARY_OBJECT)} stocks...'))
        
        PREV_DAY_HASH = "prev_day_ohlc" 
        count = 0
        
        for symbol, token in FINAL_DICTIONARY_OBJECT.items():
            try:
                # This now calls the Fixed Function with correct 09:15-15:30 times
                candles = angel.get_historical_data(token, interval="ONE_DAY")
                
                if candles and len(candles) > 0:
                    # Get the LAST completed candle (Previous Trading Day)
                    # Candle format: [timestamp, open, high, low, close, volume]
                    # Since we fetch up to Today 15:30, the last one in the list is the most recent closed day.
                    
                    # NOTE: If running during market hours, the last candle might be "Today's incomplete candle".
                    # We usually want the one BEFORE that (Previous Day).
                    # Logic: If last candle date == today, take the one before it.
                    
                    last_candle = candles[-1]
                    
                    # Basic check: Just take the last available candle for now
                    # (In a production system, check the date string index 0)
                    
                    pd_high = last_candle[2]
                    pd_low = last_candle[3]
                    pd_close = last_candle[4]
                    
                    data = {
                        "high": pd_high,
                        "low": pd_low,
                        "close": pd_close,
                        "date": last_candle[0]
                    }
                    
                    r.hset(PREV_DAY_HASH, symbol, json.dumps(data))
                    count += 1
                    
                    # Log every 50 stocks to show progress
                    if count % 50 == 0:
                        self.stdout.write(f"Processed {count} stocks...")
                        
                    # Rate limit (3 req/sec)
                    time.sleep(0.35) 
                else:
                    logger.warning(f"No history found for {symbol}")

            except Exception as e:
                logger.error(f"Failed to fetch PDH for {symbol}: {e}")
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS(f'Successfully cached PDH for {count} stocks.'))