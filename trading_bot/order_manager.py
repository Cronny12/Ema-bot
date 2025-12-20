"""
Order Manager Module
====================
Handles all order execution and management with Alpaca.
"""

import time
import random
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopLossRequest,
    TrailingStopOrderRequest,
    GetOrdersRequest,
    ClosePositionRequest
)
from alpaca.trading.enums import (
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    QueryOrderStatus
)

import config

logger = logging.getLogger(__name__)


class OrderManager:
    """Manages order execution and tracking."""
    
    def __init__(self):
        self.trading_client = TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=True  # Paper trading
        )
        self.pending_orders: Dict[str, dict] = {}
        self.error_count = 0
        self.last_error_time: Optional[datetime] = None
    
    def _generate_client_order_id(self, symbol: str) -> str:
        """Generate unique client order ID to prevent duplicates."""
        return f"{symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with exponential backoff retry logic."""
        for attempt in range(config.MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == config.MAX_RETRIES - 1:
                    raise
                delay = config.RETRY_DELAYS[attempt] + random.uniform(0, config.RETRY_JITTER_MAX)
                logger.warning(f"Retry {attempt + 1}/{config.MAX_RETRIES} after {delay:.2f}s: {e}")
                time.sleep(delay)
        return None
    
    def _track_error(self):
        """Track API errors for kill-switch."""
        now = datetime.now()
        if self.last_error_time and (now - self.last_error_time).total_seconds() > config.KILL_SWITCH_WINDOW_MINUTES * 60:
            self.error_count = 0
        self.error_count += 1
        self.last_error_time = now
    
    def should_trigger_kill_switch(self) -> bool:
        """Check if kill-switch should be triggered."""
        return self.error_count >= config.KILL_SWITCH_ERROR_COUNT
    
    def get_account(self) -> dict:
        """Get account information."""
        try:
            account = self._retry_with_backoff(self.trading_client.get_account)
            return {
                'equity': float(account.equity),
                'cash': float(account.cash),
                'buying_power': float(account.buying_power),
                'portfolio_value': float(account.portfolio_value),
                'day_trade_count': account.daytrade_count,
                'pattern_day_trader': account.pattern_day_trader
            }
        except Exception as e:
            logger.error(f"Error getting account: {e}")
            self._track_error()
            return {}
    
    def get_positions(self) -> List[dict]:
        """Get all open positions."""
        try:
            positions = self._retry_with_backoff(self.trading_client.get_all_positions)
            return [{
                'symbol': p.symbol,
                'qty': float(p.qty),
                'side': 'long' if float(p.qty) > 0 else 'short',
                'avg_entry_price': float(p.avg_entry_price),
                'market_value': float(p.market_value),
                'unrealized_pl': float(p.unrealized_pl),
                'unrealized_plpc': float(p.unrealized_plpc),
                'current_price': float(p.current_price)
            } for p in positions]
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            self._track_error()
            return []
    
    def get_position(self, symbol: str) -> Optional[dict]:
        """Get position for a specific symbol."""
        try:
            position = self._retry_with_backoff(
                self.trading_client.get_open_position, symbol
            )
            return {
                'symbol': position.symbol,
                'qty': float(position.qty),
                'side': 'long' if float(position.qty) > 0 else 'short',
                'avg_entry_price': float(position.avg_entry_price),
                'market_value': float(position.market_value),
                'unrealized_pl': float(position.unrealized_pl),
                'current_price': float(position.current_price)
            }
        except Exception as e:
            if "position does not exist" not in str(e).lower():
                logger.error(f"Error getting position for {symbol}: {e}")
            return None
    
    def submit_market_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        time_in_force: str = "day"
    ) -> Optional[dict]:
        """Submit a market order."""
        try:
            client_order_id = self._generate_client_order_id(symbol)
            
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif = TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC
            
            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
                client_order_id=client_order_id
            )
            
            order = self._retry_with_backoff(
                self.trading_client.submit_order, request
            )
            
            logger.info(f"Market order submitted: {side} {qty} {symbol} @ market")
            
            return {
                'order_id': order.id,
                'client_order_id': order.client_order_id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side.value,
                'type': order.type.value,
                'status': order.status.value,
                'submitted_at': order.submitted_at
            }
            
        except Exception as e:
            logger.error(f"Error submitting market order for {symbol}: {e}")
            self._track_error()
            return None
    
    def submit_limit_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float,
        time_in_force: str = "day"
    ) -> Optional[dict]:
        """Submit a limit order."""
        try:
            client_order_id = self._generate_client_order_id(symbol)
            
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif = TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC
            
            request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
                limit_price=round(limit_price, 2),
                client_order_id=client_order_id
            )
            
            order = self._retry_with_backoff(
                self.trading_client.submit_order, request
            )
            
            logger.info(f"Limit order submitted: {side} {qty} {symbol} @ ${limit_price:.2f}")
            
            return {
                'order_id': order.id,
                'client_order_id': order.client_order_id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side.value,
                'type': order.type.value,
                'limit_price': float(order.limit_price),
                'status': order.status.value,
                'submitted_at': order.submitted_at
            }
            
        except Exception as e:
            logger.error(f"Error submitting limit order for {symbol}: {e}")
            self._track_error()
            return None
    
    def submit_stop_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        stop_price: float,
        time_in_force: str = "gtc"
    ) -> Optional[dict]:
        """Submit a stop-loss order."""
        try:
            client_order_id = self._generate_client_order_id(symbol)
            
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif = TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC
            
            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
                client_order_id=client_order_id,
                stop_loss=StopLossRequest(stop_price=round(stop_price, 2))
            )
            
            order = self._retry_with_backoff(
                self.trading_client.submit_order, request
            )
            
            logger.info(f"Stop order submitted: {side} {qty} {symbol} @ stop ${stop_price:.2f}")
            
            return {
                'order_id': order.id,
                'client_order_id': order.client_order_id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side.value,
                'stop_price': stop_price,
                'status': order.status.value
            }
            
        except Exception as e:
            logger.error(f"Error submitting stop order for {symbol}: {e}")
            self._track_error()
            return None
    
    def submit_trailing_stop_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        trail_percent: float,
        time_in_force: str = "gtc"
    ) -> Optional[dict]:
        """Submit a trailing stop order."""
        try:
            client_order_id = self._generate_client_order_id(symbol)
            
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif = TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC
            
            request = TrailingStopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
                trail_percent=round(trail_percent, 2),
                client_order_id=client_order_id
            )
            
            order = self._retry_with_backoff(
                self.trading_client.submit_order, request
            )
            
            logger.info(f"Trailing stop submitted: {side} {qty} {symbol} @ {trail_percent}% trail")
            
            return {
                'order_id': order.id,
                'client_order_id': order.client_order_id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side.value,
                'trail_percent': trail_percent,
                'status': order.status.value
            }
            
        except Exception as e:
            logger.error(f"Error submitting trailing stop for {symbol}: {e}")
            self._track_error()
            return None
    
    def get_order(self, order_id: str) -> Optional[dict]:
        """Get order by ID."""
        try:
            order = self._retry_with_backoff(
                self.trading_client.get_order_by_id, order_id
            )
            return {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'filled_qty': float(order.filled_qty) if order.filled_qty else 0,
                'side': order.side.value,
                'type': order.type.value,
                'status': order.status.value,
                'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None
            }
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}")
            return None
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """Get all open orders, optionally filtered by symbol."""
        try:
            request = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[symbol] if symbol else None
            )
            orders = self._retry_with_backoff(
                self.trading_client.get_orders, request
            )
            return [{
                'order_id': o.id,
                'symbol': o.symbol,
                'qty': float(o.qty),
                'filled_qty': float(o.filled_qty) if o.filled_qty else 0,
                'side': o.side.value,
                'type': o.type.value,
                'status': o.status.value,
                'limit_price': float(o.limit_price) if o.limit_price else None,
                'stop_price': float(o.stop_price) if o.stop_price else None
            } for o in orders]
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by ID."""
        try:
            self._retry_with_backoff(
                self.trading_client.cancel_order_by_id, order_id
            )
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self._retry_with_backoff(self.trading_client.cancel_orders)
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return False
    
    def close_position(self, symbol: str) -> Optional[dict]:
        """Close a position for a symbol."""
        try:
            order = self._retry_with_backoff(
                self.trading_client.close_position, symbol
            )
            logger.info(f"Position closed for {symbol}")
            return {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side.value
            }
        except Exception as e:
            if "position does not exist" not in str(e).lower():
                logger.error(f"Error closing position for {symbol}: {e}")
            return None
    
    def close_all_positions(self) -> bool:
        """Close all open positions."""
        try:
            self._retry_with_backoff(self.trading_client.close_all_positions)
            logger.info("All positions closed")
            return True
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return False
    
    def check_fill_status(self, order_id: str, wait_minutes: int = 2) -> Tuple[str, float]:
        """
        Check order fill status.
        Returns (status, fill_percent).
        """
        order = self.get_order(order_id)
        if order is None:
            return "error", 0.0
        
        filled_qty = order.get('filled_qty', 0)
        total_qty = order.get('qty', 1)
        fill_percent = filled_qty / total_qty if total_qty > 0 else 0
        
        return order['status'], fill_percent
    
    def handle_partial_fill(
        self,
        order_id: str,
        original_price: float,
        reprice_adjustment: float = 0.001
    ) -> Optional[dict]:
        """
        Handle partial fills - cancel and reprice if < 70% filled.
        """
        status, fill_percent = self.check_fill_status(order_id)
        
        if fill_percent >= config.PARTIAL_FILL_THRESHOLD:
            return None  # Good enough fill
        
        order = self.get_order(order_id)
        if order is None:
            return None
        
        # Cancel the partial order
        self.cancel_order(order_id)
        
        # Calculate remaining qty
        remaining_qty = int(order['qty'] - order['filled_qty'])
        if remaining_qty <= 0:
            return None
        
        # Reprice with adjustment
        if order['side'] == 'buy':
            new_price = original_price * (1 + reprice_adjustment)
        else:
            new_price = original_price * (1 - reprice_adjustment)
        
        # Submit new limit order
        return self.submit_limit_order(
            symbol=order['symbol'],
            qty=remaining_qty,
            side=order['side'],
            limit_price=new_price
        )
    
    def calculate_slippage(self, signal_price: float, fill_price: float) -> float:
        """Calculate slippage in basis points."""
        if signal_price == 0:
            return 0
        return abs(fill_price - signal_price) / signal_price * 10000
    
    def adjust_size_for_slippage(
        self,
        base_size: int,
        observed_slippage: float,
        target_slippage: float = config.TARGET_SLIPPAGE_BPS
    ) -> int:
        """
        Dynamically adjust position size based on observed slippage.
        """
        if observed_slippage <= 0:
            return base_size
        
        adjustment_ratio = target_slippage / observed_slippage
        
        # Cap adjustment at ±50%
        adjustment_ratio = max(1 - config.SLIPPAGE_SIZE_CAP, 
                              min(1 + config.SLIPPAGE_SIZE_CAP, adjustment_ratio))
        
        return max(1, int(base_size * adjustment_ratio))
