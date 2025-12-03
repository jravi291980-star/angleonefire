from django.core.management.base import BaseCommand
from tradeapp.models import APICredential
from tradeapp.angel_utils import AngelConnect
from tradeapp.constants import FINAL_DICTIONARY_OBJECT
import redis
import json
import time
import logging

logger = logging.getLogger('pdh_fetcher')

class Command(BaseCommand):
    help = 'Fetches Previous Day High (PDH) and Low (PDL) for the stock universe and caches in Redis.'

    def handle(self, *args, **options):
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        creds = APICredential.objects.first()
        
        if not creds:
            self.stdout.write(self.style.ERROR('No Credentials Found'))
            return

        angel = AngelConnect(creds.api_key, creds.access_token, creds.refresh_token, creds.feed_token)
        
        self.stdout.write(self.style.SUCCESS(f'Fetching PDH for {len(FINAL_DICTIONARY_OBJECT)} stocks...'))
        
        PREV_DAY_HASH = "prev_day_ohlc" 
        
        count = 0
        for symbol, token in FINAL_DICTIONARY_OBJECT.items():
            try:
                candles = angel.get_historical_data(token, interval="ONE_DAY")
                
                if candles and len(candles) > 0:
                    prev_day_candle = candles[-1]
                    pd_high = prev_day_candle[2]
                    pd_low = prev_day_candle[3]
                    
                    data = {
                        "high": pd_high,
                        "low": pd_low,
                        "close": prev_day_candle[4],
                        "date": prev_day_candle[0]
                    }
                    
                    r.hset(PREV_DAY_HASH, symbol, json.dumps(data))
                    count += 1
                    time.sleep(0.35) 
                else:
                    logger.warning(f"No history found for {symbol}")

            except Exception as e:
                logger.error(f"Failed to fetch PDH for {symbol}: {e}")
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS(f'Successfully cached PDH for {count} stocks.'))