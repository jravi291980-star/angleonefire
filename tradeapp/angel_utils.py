# import SmartApi.smartConnect as smart
# import logging
# import time
# import os
# import redis
# from datetime import datetime, timedelta
# from tenacity import retry, stop_after_attempt, wait_exponential

# logger = logging.getLogger(__name__)

# def get_redis_client():
#     redis_url = os.environ.get('REDIS_URL')
#     if redis_url:
#         return redis.from_url(redis_url, decode_responses=True, ssl_cert_reqs=None)
#     else:
#         return redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# class AngelConnect:
#     def __init__(self, api_key, access_token=None, refresh_token=None, feed_token=None):
#         self.api_key = api_key
#         self.client = smart.SmartConnect(api_key=self.api_key)
        
#         if access_token:
#             self.client.setAccessToken(access_token)
#             self.client.setRefreshToken(refresh_token)
#             self.client.setFeedToken(feed_token)

#     @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
#     def place_order(self, symbol_token, symbol, quantity, transaction_type, product_type="INTRADAY", order_type="MARKET", price=0.0):
#         try:
#             orderparams = {
#                 "variety": "NORMAL",
#                 "tradingsymbol": symbol,
#                 "symboltoken": symbol_token,
#                 "transactiontype": transaction_type,
#                 "exchange": "NSE",
#                 "ordertype": order_type,
#                 "producttype": product_type,
#                 "duration": "DAY",
#                 "price": price,
#                 "squareoff": "0",
#                 "stoploss": "0",
#                 "quantity": quantity
#             }
#             order_id = self.client.placeOrder(orderparams)
#             return order_id
#         except Exception as e:
#             logger.error(f"Angel Utils: Place Order Failed: {e}")
#             raise e

#     def get_order_status(self, order_id):
#         try:
#             book = self.client.orderBook()
#             if not book or 'data' not in book:
#                 return None
#             for order in book['data']:
#                 if order['orderid'] == order_id:
#                     return {
#                         'status': order['orderstatus'],
#                         'filled_quantity': int(order.get('filledshares', 0)),
#                         'average_price': float(order.get('averageprice', 0.0)),
#                         'text': order.get('text', '')
#                     }
#             return None
#         except Exception as e:
#             logger.error(f"Angel Utils: Get Order Status Failed: {e}")
#             return None

#     def get_historical_data(self, token, interval="ONE_DAY"):
#         """
#         Fetches historical data with STRICT time formatting.
#         Format must be: yyyy-MM-dd 09:15 to yyyy-MM-dd 15:30
#         """
#         try:
#             today = datetime.now()
            
#             # We fetch the last 5 days to automatically handle weekends/holidays.
#             # If we only asked for "yesterday", it would fail on Mondays.
#             from_date_obj = today - timedelta(days=5)
            
#             # Formatting as per Official Doc: '%Y-%m-%d %H:%M'
#             # Timestamps MUST be 09:15 and 15:30
#             from_str = from_date_obj.strftime("%Y-%m-%d 09:15")
#             to_str = today.strftime("%Y-%m-%d 15:30")
            
#             params = {
#                 "exchange": "NSE",
#                 "symboltoken": token,
#                 "interval": interval,
#                 "fromdate": from_str,
#                 "todate": to_str
#             }
            
#             data = self.client.getCandleData(params)
#             return data['data'] if data and 'data' in data else None
#         except Exception as e:
#             logger.error(f"Error fetching history for {token}: {e}")
#             return None

import SmartApi.smartConnect as smart
import logging
import time
import os
import redis
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# --- Redis Client (Good as is) ---
def get_redis_client():
    """Initializes the Redis client."""
    # Assuming __redis_config is available in your execution environment for local testing
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        return redis.from_url(redis_url, decode_responses=True, ssl_cert_reqs=None)
    else:
        # Note: You should ensure your environment variables are correctly set up
        # for a production environment.
        return redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# --- Angel Connect Class (Updated) ---
class AngelConnect:
    def __init__(self, api_key, client_id, password, access_token=None, refresh_token=None, feed_token=None):
        self.api_key = api_key
        # Add client_id and password for re-authentication
        self.client_id = client_id 
        self.password = password
        
        self.client = smart.SmartConnect(api_key=self.api_key)
        self.refresh_token = refresh_token
        
        if access_token:
            self.client.setAccessToken(access_token)
            self.client.setRefreshToken(refresh_token)
            self.client.setFeedToken(feed_token)

    def refresh_access_token(self):
        """
        ATTENTION: This method is CRITICAL for fixing the 'Invalid Token' error.
        You must implement the actual Angel One API call here to regenerate the token.
        """
        logger.info("Attempting to refresh access token...")
        
        # 1. Use client ID and stored password/TOPT to generate a new token via login API
        #    Example: Call the '/rest/auth/angelbroking/user/v1/loginByPassword' endpoint
        #    This call will return new access_token, refresh_token, and feed_token.
        
        try:
            # Example using the SDK's generated token (if you are only using refresh_token)
            # You might need to call a different method depending on the API flow you use.
            data = self.client.generateSession(self.client_id, self.password, self.refresh_token)
            
            if data and data.get('status'):
                new_access_token = data['data']['jwtToken']
                new_refresh_token = data['data']['refreshToken']
                new_feed_token = data['data']['feedToken']
                
                self.client.setAccessToken(new_access_token)
                self.client.setRefreshToken(new_refresh_token)
                self.client.setFeedToken(new_feed_token)

                logger.info("Token successfully refreshed.")
                # You should also save these new tokens to Redis/DB here!
                # E.g., self.redis_client.set('angel_access_token', new_access_token)
                return True
            else:
                logger.error(f"Token refresh failed: {data.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"Exception during token refresh: {e}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def place_order(self, symbol_token, symbol, quantity, transaction_type, product_type="INTRADAY", order_type="MARKET", price=0.0):
        # ... (Order placing logic is fine, though you might need to add a token refresh logic before the call)
        try:
            # Check token validity before placing a critical order
            # (A more complex check involving a lightweight API call or timestamp validation is ideal)
            orderparams = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": symbol_token,
                "transactiontype": transaction_type,
                "exchange": "NSE",
                "ordertype": order_type,
                "producttype": product_type,
                "duration": "DAY",
                "price": price,
                "squareoff": "0",
                "stoploss": "0",
                "quantity": quantity
            }
            order_id = self.client.placeOrder(orderparams)
            return order_id
        except Exception as e:
            logger.error(f"Angel Utils: Place Order Failed: {e}")
            # If token error, try refreshing once
            if "Invalid Token" in str(e) and self.refresh_access_token():
                logger.warning("Retrying order after successful token refresh.")
                # The @retry decorator will automatically handle the retry now
                raise e # Re-raise to trigger tenacity retry
            raise e

    def _extract_previous_day_high_low(self, candles):
        """
        Helper function to find the high/low of the last COMPLETED trading day.
        Candle data format: [[Timestamp, Open, High, Low, Close, Volume], ...]
        """
        if not candles or len(candles) < 2:
            # We expect at least one completed day
            return None
        
        # The last candle is usually the current (incomplete) day.
        # The second to last candle is the previous completed day.
        # We assume the data is sorted chronologically by the API.
        
        # Ensure the date is a past date (to avoid incomplete current day)
        # We iterate from the end to find the first candle that is not today's date
        
        # Define today's date start (YYYY-MM-DD)
        today_date_str = datetime.now().strftime("%Y-%m-%d")

        for candle_data in reversed(candles):
            # Candle timestamp is the first element
            candle_timestamp_str = candle_data[0] # e.g., '2025-12-03T09:15:00.000000Z'
            
            # Extract the date part
            candle_date_part = candle_timestamp_str.split('T')[0]
            
            if candle_date_part != today_date_str:
                # Found the last completed day!
                # High is index 2, Low is index 3
                return {
                    "date": candle_date_part,
                    "high": float(candle_data[2]),
                    "low": float(candle_data[3])
                }
        
        return None # Only today's data or no data found.


    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def get_historical_data(self, token, interval="ONE_DAY"):
        """
        Fetches historical data and returns the previous day's high/low.
        """
        try:
            today = datetime.now()
            
            # Request 5 days of data to safely capture the last completed trading day.
            from_date_obj = today - timedelta(days=5)
            
            from_str = from_date_obj.strftime("%Y-%m-%d 09:15")
            to_str = today.strftime("%Y-%m-%d 15:30")
            
            params = {
                "exchange": "NSE",
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_str,
                "todate": to_str
            }
            
            data = self.client.getCandleData(params)
            
            # 1. Check for Invalid Token explicitly in the response
            if not data.get('success', True) and data.get('errorCode') == 'AG8001':
                logger.error("Invalid Token detected. Attempting to refresh...")
                if self.refresh_access_token():
                    # Token refresh successful, raise exception to trigger retry
                    raise Exception("Token Refreshed. Retrying historical data fetch.")
                else:
                    logger.error("Token refresh failed. Cannot fetch data.")
                    return None
            
            candles = data.get('data')
            
            if candles:
                return self._extract_previous_day_high_low(candles)
            else:
                logger.warning(f"No history found for {token} in the requested range.")
                return None
            
        except Exception as e:
            logger.error(f"Final error fetching history for {token}: {e}")
            # Raise the exception again if it was a tenacity retry trigger
            if "Retrying" in str(e): 
                raise e
            return None