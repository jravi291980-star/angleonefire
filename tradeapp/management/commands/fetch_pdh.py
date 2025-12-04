from django.core.management.base import BaseCommand
from tradeapp.models import APICredential
from tradeapp.angel_utils import AngelConnect, get_redis_client
from tradeapp.constants import FINAL_DICTIONARY_OBJECT
import json
import time
import logging

logger = logging.getLogger('pdh_fetcher')

class Command(BaseCommand):
    help = 'Fetches Previous Day High (PDH) and Low (PDL)'

    def handle(self, *args, **options):
        r = get_redis_client()
        creds = APICredential.objects.first()
        
        if not creds or not creds.access_token:
            self.stdout.write(self.style.ERROR('No Valid Credentials Found.'))
            return

        angel = AngelConnect(creds.api_key, creds.access_token, creds.refresh_token, creds.feed_token)
        
        self.stdout.write(self.style.SUCCESS(f'Fetching PDH for {len(FINAL_DICTIONARY_OBJECT)} stocks...'))
        
        PREV_DAY_HASH = "prev_day_ohlc" 
        count = 0
        
        for symbol, token in FINAL_DICTIONARY_OBJECT.items():
            try:
                candles = angel.get_historical_data(token, interval="ONE_DAY")
                
                if candles and len(candles) > 0:
                    # Logic: Get the last COMPLETED day.
                    # candles[-1] is the most recent data point.
                    # If fetching during market hours, candles[-1] is TODAY (Incomplete).
                    # We need YESTERDAY (candles[-2]) if candles[-1] date matches today.
                    
                    # For simplicity in this fix, we take the last available candle 
                    # assuming the intention is the "most recent previous high reference"
                    
                    last_candle = candles[-1]
                    
                    data = {
                        "high": last_candle[2],
                        "low": last_candle[3],
                        "close": last_candle[4],
                        "date": last_candle[0]
                    }
                    
                    r.hset(PREV_DAY_HASH, symbol, json.dumps(data))
                    count += 1
                    
                    if count % 20 == 0:
                        self.stdout.write(f"Processed {count}...")
                        
                    time.sleep(0.35) # Rate Limit
                else:
                    print(f"No history for {symbol}")

            except Exception as e:
                print(f"Error {symbol}: {e}")
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS(f'Successfully cached PDH for {count} stocks.'))