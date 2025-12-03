import json
import time
import logging
import threading
from math import floor
from datetime import datetime as dt, timedelta, time as dt_time
from typing import Dict, Optional, Any, List

import pytz
import redis
from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.utils import timezone
from django.conf import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_not_exception_type

from core.models import APICredential, Trade, StrategySettings
from core.angel_utils import AngelConnect

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# --- Redis Keys (Matching your strategy) ---
CANDLE_STREAM_KEY = getattr(settings, "BREAKOUT_CANDLE_STREAM", "candle_1m")
LIVE_OHLC_KEY = getattr(settings, "BREAKOUT_LIVE_OHLC_KEY", "live_ohlc_data")
PREV_DAY_HASH = "prev_day_ohlc" # Populated by a separate cron or script
ENTRY_OFFSET_PCT = 0.0001
STOP_OFFSET_PCT = 0.0002
BREAKOUT_MAX_CANDLE_PCT = 0.007

class CashBreakoutClient:
    """Adapted for Angel One"""

    def __init__(self, user, api_creds):
        self.user = user
        self.api_creds = api_creds
        # Initialize Angel Wrapper
        self.angel = AngelConnect(
            api_key=api_creds.api_key, 
            access_token=api_creds.access_token,
            refresh_token=api_creds.refresh_token,
            feed_token=api_creds.feed_token
        )
        
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.settings, _ = StrategySettings.objects.get_or_create(user=user)
        
        self.running = True
        self.last_reconcile_time = time.time()
        
        # In-memory State
        self.open_trades: Dict[str, Trade] = {}
        self.pending_trades: Dict[str, Trade] = {}
        
        # Redis Stream Config
        self.group_name = f"CB_GROUP:{self.user.id}"
        self.consumer_name = f"CB_CONSUMER:{threading.get_ident()}"
        
        # Init Redis Group
        try:
            self.redis_client.xgroup_create(CANDLE_STREAM_KEY, self.group_name, id='0', mkstream=True)
        except redis.exceptions.ResponseError as e:
            if 'BUSYGROUP' not in str(e): logger.error(f"Redis Group Error: {e}")

        # Load State
        self._load_trades_from_db()

    def _load_trades_from_db(self):
        """Restore state from DB on restart"""
        active_trades = Trade.objects.filter(
            user=self.user, 
            status__in=["OPEN", "PENDING_EXIT", "PENDING", "PENDING_ENTRY"]
        )
        for trade in active_trades:
            if trade.status == "PENDING":
                self.pending_trades[trade.symbol] = trade
            elif trade.status in ["OPEN", "PENDING_EXIT"]:
                self.open_trades[trade.symbol] = trade
        logger.info(f"Loaded {len(self.open_trades)} Open, {len(self.pending_trades)} Pending trades.")

    def _get_live_ohlc(self) -> Dict[str, Any]:
        try:
            raw = self.redis_client.get(LIVE_OHLC_KEY)
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _get_prev_day_high(self, symbol):
        # Retrieve from Redis Hash where you store PDH
        # You need a separate script to populate 'prev_day_ohlc' hash with {symbol: {'high': ...}}
        raw = self.redis_client.hget(PREV_DAY_HASH, symbol)
        if raw:
            try:
                data = json.loads(raw)
                return float(data.get('high', 0))
            except: pass
        return None

    def _calculate_quantity(self, entry_price, sl_price):
        risk_per_share = abs(entry_price - sl_price)
        if risk_per_share <= 0: return 0
        qty = floor(float(self.settings.per_trade_sl_amount) / risk_per_share)
        return int(qty)

    def _process_candle(self, candle):
        symbol = candle['symbol']
        token = candle['token']
        
        # 1. Skip if already monitoring/open
        if symbol in self.pending_trades or symbol in self.open_trades:
            return

        # 2. Check Daily Trade Limit
        # Implement daily count check here...

        # 3. Validation Logic
        pdh = self._get_prev_day_high(symbol)
        if not pdh: return # Missing PDH

        close = float(candle['close'])
        open_ = float(candle['open'])
        high = float(candle['high'])
        low = float(candle['low'])
        
        # Strategy Rules
        if not (close > open_): return
        if not (low < pdh < close): return
        if not (open_ < pdh): return
        
        # Calc Levels
        entry_level = high * (1.0 + ENTRY_OFFSET_PCT)
        stop_level = low - (low * STOP_OFFSET_PCT)
        target_level = entry_level + (2.5 * (entry_level - stop_level))
        
        # Create PENDING Trade in DB
        trade = Trade.objects.create(
            user=self.user,
            symbol=symbol,
            token=token,
            candle_ts=timezone.now(), # Approximation
            candle_open=open_, candle_high=high, candle_low=low, candle_close=close,
            prev_day_high=pdh,
            entry_level=entry_level,
            stop_level=stop_level,
            target_level=target_level,
            status="PENDING"
        )
        self.pending_trades[symbol] = trade
        logger.info(f"Registered PENDING: {symbol} Entry: {entry_level}")

    def _try_enter_pending(self):
        live_data = self._get_live_ohlc()
        to_remove = []
        
        for symbol, trade in self.pending_trades.items():
            if symbol not in live_data: continue
            
            ltp = float(live_data[symbol].get('ltp', 0))
            
            # 1. Expiry (6 mins)
            if timezone.now() > trade.candle_ts + timedelta(minutes=6):
                trade.status = "EXPIRED"
                trade.exit_reason = "6 Min Expiry"
                trade.save()
                to_remove.append(symbol)
                continue

            # 2. Stop Hit before Entry
            if ltp < float(trade.stop_level):
                trade.status = "EXPIRED"
                trade.exit_reason = "Price fell below SL before Entry"
                trade.save()
                to_remove.append(symbol)
                continue

            # 3. Trigger Entry
            if ltp > float(trade.entry_level):
                qty = self._calculate_quantity(ltp, float(trade.stop_level))
                if qty > 0:
                    try:
                        # Place Angel Order
                        order_id = self.angel.place_order(
                            trade.token, trade.symbol, qty, "BUY", product_type="INTRADAY"
                        )
                        trade.status = "PENDING_ENTRY"
                        trade.entry_order_id = order_id
                        trade.quantity = qty
                        trade.save()
                        logger.info(f"Entry Order Placed: {symbol} ID: {order_id}")
                    except Exception as e:
                        logger.error(f"Entry Failed: {e}")
                        trade.status = "FAILED_ENTRY"
                        trade.save()
                to_remove.append(symbol)

        for s in to_remove:
            del self.pending_trades[s]

    def reconcile_trades(self):
        """Check Order Status with Angel"""
        # 1. Check PENDING_ENTRY
        entries = Trade.objects.filter(user=self.user, status="PENDING_ENTRY")
        for trade in entries:
            status_data = self.angel.get_order_status(trade.entry_order_id)
            if status_data:
                # Angel status is lowercase 'complete' usually
                if status_data['status'].lower() == 'complete':
                    trade.status = "OPEN"
                    trade.entry_price = status_data['average_price']
                    trade.quantity = status_data['filled_quantity'] # Update actual filled
                    trade.save()
                    self.open_trades[trade.symbol] = trade
                    logger.info(f"Trade Opened: {trade.symbol} @ {trade.entry_price}")
                elif status_data['status'].lower() in ['rejected', 'cancelled']:
                    trade.status = "FAILED_ENTRY"
                    trade.save()

        # 2. Check PENDING_EXIT
        exits = Trade.objects.filter(user=self.user, status="PENDING_EXIT")
        for trade in exits:
            status_data = self.angel.get_order_status(trade.exit_order_id)
            if status_data and status_data['status'].lower() == 'complete':
                trade.status = "CLOSED"
                trade.exit_price = status_data['average_price']
                trade.pnl = (float(trade.exit_price) - float(trade.entry_price)) * trade.quantity
                trade.save()
                if trade.symbol in self.open_trades:
                    del self.open_trades[trade.symbol]
                logger.info(f"Trade Closed: {trade.symbol} PnL: {trade.pnl}")

    def monitor_trades(self):
        live_data = self._get_live_ohlc()
        for symbol, trade in list(self.open_trades.items()):
            if symbol not in live_data: continue
            
            ltp = float(live_data[symbol].get('ltp', 0))
            entry_price = float(trade.entry_price)
            stop_level = float(trade.stop_level)
            target_level = float(trade.target_level)
            
            # 1. Breakeven TSL Logic (1.25R)
            risk = entry_price - stop_level
            if risk > 0:
                be_trigger = entry_price + (1.25 * risk)
                if ltp >= be_trigger and stop_level < entry_price:
                    trade.stop_level = entry_price # Move to BE
                    trade.save()
                    logger.info(f"TSL Moved to BE: {symbol}")

            # 2. Exit Logic (Target or Stop)
            exit_needed = False
            reason = ""
            
            if ltp >= target_level:
                exit_needed = True
                reason = "Target Hit"
            elif ltp <= stop_level:
                exit_needed = True
                reason = "Stop Loss Hit"
            
            if exit_needed:
                try:
                    order_id = self.angel.place_order(
                        trade.token, trade.symbol, trade.quantity, "SELL", product_type="INTRADAY"
                    )
                    trade.status = "PENDING_EXIT"
                    trade.exit_order_id = order_id
                    trade.exit_reason = reason
                    trade.save()
                    logger.info(f"Exit Triggered: {symbol} ({reason})")
                except Exception as e:
                    logger.error(f"Exit Order Failed: {e}")

    def run(self):
        logger.info("Algo Engine Started...")
        while self.running:
            try:
                # 1. Read Stream for Candles
                messages = self.redis_client.xreadgroup(
                    self.group_name, self.consumer_name, {CANDLE_STREAM_KEY: '>'}, count=10, block=1000
                )
                
                if messages:
                    for _, msg_list in messages:
                        for msg_id, msg_data in msg_list:
                            candle = json.loads(msg_data['data'])
                            self._process_candle(candle)
                            self.redis_client.xack(CANDLE_STREAM_KEY, self.group_name, msg_id)

                # 2. Monitor & Reconcile
                self._try_enter_pending()
                self.monitor_trades()
                
                if time.time() - self.last_reconcile_time > 1:
                    self.reconcile_trades()
                    self.last_reconcile_time = time.time()
                
            except Exception as e:
                logger.error(f"Engine Loop Error: {e}")
                time.sleep(1)

class Command(BaseCommand):
    help = 'Runs the Angel Algo Engine'

    def handle(self, *args, **options):
        # Find first valid user with creds
        creds = APICredential.objects.first()
        if not creds: return
        
        client = CashBreakoutClient(creds.user, creds)
        client.run()