"""
Trading Engine Module
=====================
Main trading logic orchestrating all components.
"""

import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging
import pytz

import config
from data_manager import DataManager
from order_manager import OrderManager
from risk_manager import RiskManager
from trade_logger import TradeLogger
from email_notifier import EmailNotifier
from state_manager import StateManager
from indicators import (
    calculate_ema, calculate_sma, calculate_rsi, calculate_macd,
    calculate_atr, calculate_atr_percent, calculate_adx,
    detect_ema_crossover, is_trend_bullish, is_trend_bearish,
    is_above_sma, is_below_sma, calculate_volatility_regime,
    optimize_ema_periods, check_dont_chase, calculate_gap_percent,
    is_gap_day, calculate_trailing_stop, calculate_position_size,
    calculate_r_multiple
)

logger = logging.getLogger(__name__)


class TradingEngine:
    """Main trading engine orchestrating all components."""
    
    def __init__(self):
        self.data_manager = DataManager()
        self.order_manager = OrderManager()
        self.risk_manager = RiskManager()
        self.trade_logger = TradeLogger()
        self.email_notifier = EmailNotifier()
        self.state_manager = StateManager()
        
        self.tz = pytz.timezone(config.TIMEZONE)
        self.daily_errors = 0
        self.session_trades = []
        self.session_pnl = []
    
    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        now = datetime.now(self.tz)
        current_time = now.time()
        
        # Check if it's a weekday
        if now.weekday() >= 5:
            return False
        
        # Check holidays
        today_str = now.strftime('%Y-%m-%d')
        if today_str in config.US_MARKET_HOLIDAYS:
            return False
        
        # Check market hours
        return config.MARKET_OPEN_DUBLIN <= current_time <= config.MARKET_CLOSE_DUBLIN
    
    def is_entry_allowed_time(self) -> bool:
        """Check if current time allows new entries."""
        now = datetime.now(self.tz)
        current_time = now.time()
        return config.ENTRY_START_DUBLIN <= current_time <= config.ENTRY_END_DUBLIN
    
    def should_flatten_positions(self) -> bool:
        """Check if it's time to flatten all positions."""
        now = datetime.now(self.tz)
        return now.time() >= config.FLAT_BY_DUBLIN
    
    def initialize_session(self):
        """Initialize for a new trading session."""
        logger.info("Initializing trading session...")
        
        # Reset state for new session
        self.state_manager.reset_for_new_session()
        
        # Get account info
        account = self.order_manager.get_account()
        if not account:
            logger.error("Failed to get account info")
            return False
        
        equity = account['equity']
        logger.info(f"Account equity: ${equity:,.2f}")
        
        # Initialize risk manager
        self.risk_manager.initialize_day(equity)
        
        # Check for universe update (monthly)
        if self.state_manager.should_update_universe():
            logger.info("Updating trading universe...")
            new_universe = self.data_manager.build_universe(top_n=20)
            if new_universe:
                self.state_manager.update_universe(new_universe)
        
        # Reconcile positions with broker
        positions = self.order_manager.get_positions()
        discrepancies = self.state_manager.reconcile_positions(positions)
        
        if discrepancies['missing_in_state']:
            logger.warning(f"Found {len(discrepancies['missing_in_state'])} untracked positions")
        
        # Re-arm stops for existing positions
        self._rearm_stops()
        
        self.daily_errors = 0
        self.session_trades = []
        self.session_pnl = []
        
        logger.info("Session initialized successfully")
        return True
    
    def _rearm_stops(self):
        """Re-arm stop orders for existing positions."""
        active_trades = self.state_manager.get_active_trades()
        
        for trade_id, trade in active_trades.items():
            symbol = trade['symbol']
            stop_price = trade.get('stop_price')
            qty = trade.get('qty', 0)
            side = trade.get('side', 'long')
            
            if stop_price and qty > 0:
                # Cancel any existing stops
                open_orders = self.order_manager.get_open_orders(symbol)
                for order in open_orders:
                    if order.get('type') in ['stop', 'trailing_stop']:
                        self.order_manager.cancel_order(order['order_id'])
                
                # Submit new stop
                stop_side = 'sell' if side == 'long' else 'buy'
                stop_order = self.order_manager.submit_stop_order(
                    symbol=symbol,
                    qty=qty,
                    side=stop_side,
                    stop_price=stop_price
                )
                
                if stop_order:
                    self.state_manager.update_stop(symbol, stop_order['order_id'], stop_price)
                    logger.info(f"Re-armed stop for {symbol} @ ${stop_price:.2f}")
    
    def run_loop(self):
        """Run one iteration of the main trading loop."""
        try:
            # Check kill switch
            if self.state_manager.is_kill_switch_active():
                logger.warning("Kill switch active - manual restart required")
                return
            
            # Check if market is open
            if not self.is_market_open():
                logger.debug("Market closed")
                return
            
            # Get account info
            account = self.order_manager.get_account()
            if not account:
                self._handle_error("Failed to get account info")
                return
            
            equity = account['equity']
            
            # Check daily loss limit
            if self.risk_manager.check_daily_loss_limit():
                self._flatten_all("Daily loss limit hit")
                self.email_notifier.send_daily_loss_alert(
                    self.risk_manager.daily_pnl,
                    self.risk_manager.daily_pnl / self.risk_manager.daily_start_equity
                )
                return
            
            # Check circuit breaker
            vix = self.data_manager.get_vix()
            spy_data = self.data_manager.get_spy_data("5Min", lookback_days=30)
            if not spy_data.empty:
                spy_atr_pct = calculate_atr_percent(
                    spy_data['high'], spy_data['low'], spy_data['close']
                )
                spy_atr_median = spy_atr_pct.iloc[-20:].median() if len(spy_atr_pct) >= 20 else spy_atr_pct.iloc[-1]
                
                if self.risk_manager.check_circuit_breaker(vix, spy_atr_pct.iloc[-1], spy_atr_median):
                    self.state_manager.set_circuit_breaker(True)
                    self.email_notifier.send_circuit_breaker_alert(
                        "Market volatility exceeded threshold", vix
                    )
            
            # Process existing positions
            self._manage_exits(equity)
            
            # Check for flat time
            if self.should_flatten_positions():
                self._flatten_all("End of day flat rule")
                return
            
            # Look for new entries if allowed
            if (self.is_entry_allowed_time() and 
                self.risk_manager.can_enter_new_trade() and
                not self.state_manager.is_paused()):
                self._scan_for_entries(equity)
            
            # Save state
            self.state_manager.save_state()
            
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self._handle_error(str(e))
    
    def _scan_for_entries(self, equity: float):
        """Scan universe for entry signals."""
        universe = self.state_manager.get_universe()
        positions = self.order_manager.get_positions()
        current_position_count = len(positions)
        
        # Check position limit
        if not self.risk_manager.check_position_limit(current_position_count):
            return
        
        # Get SPY for market breadth filter
        spy_data = self.data_manager.get_spy_data("5Min", lookback_days=5)
        if spy_data.empty:
            logger.warning("No SPY data available")
            return
        
        spy_ema9 = calculate_ema(spy_data['close'], 9)
        spy_ema21 = calculate_ema(spy_data['close'], 21)
        spy_adx = calculate_adx(spy_data['high'], spy_data['low'], spy_data['close'])
        
        market_bullish = (is_trend_bullish(spy_ema9, spy_ema21) and 
                        spy_adx.iloc[-1] > config.ADX_THRESHOLD)
        market_bearish = (is_trend_bearish(spy_ema9, spy_ema21) and 
                        spy_adx.iloc[-1] > config.ADX_THRESHOLD)
        
        for symbol in universe:
            # Skip if already have position
            if any(p['symbol'] == symbol for p in positions):
                continue
            
            # Skip if halted
            if self.data_manager.is_symbol_halted(symbol):
                continue
            
            # Check for signal
            signal = self._check_entry_signal(symbol, market_bullish, market_bearish, equity)
            
            if signal:
                self._execute_entry(signal, equity, positions)
                
                # Re-check position limit
                positions = self.order_manager.get_positions()
                if not self.risk_manager.check_position_limit(len(positions)):
                    break
    
    def _check_entry_signal(
        self,
        symbol: str,
        market_bullish: bool,
        market_bearish: bool,
        equity: float
    ) -> Optional[Dict]:
        """Check if symbol has valid entry signal."""
        try:
            # Get data
            bars_5m = self.data_manager.get_bars(symbol, "5Min", lookback_days=30)
            bars_15m = self.data_manager.get_bars(symbol, "15Min", lookback_days=30)
            bars_daily = self.data_manager.get_bars(symbol, "1Day", lookback_days=250)
            
            if bars_5m.empty or bars_15m.empty or bars_daily.empty:
                return None
            
            # Check data freshness
            latest_bar = bars_5m.iloc[-1]
            if not self.data_manager.check_data_freshness(bars_5m.index[-1]):
                self.trade_logger.log_shadow_signal(
                    symbol, "SKIP", "Stale data",
                    latest_bar['close'], 0, 0, 0, 0, 0, 0, 0
                )
                return None
            
            close = bars_5m['close']
            high = bars_5m['high']
            low = bars_5m['low']
            
            # Get optimized EMA periods or use default
            ema_periods = self.state_manager.get_ema_periods(symbol)
            if ema_periods:
                fast_period = ema_periods['fast']
                slow_period = ema_periods['slow']
            else:
                # Optimize EMA periods
                fast_period, slow_period = optimize_ema_periods(
                    bars_daily['close'],
                    config.FAST_EMA_RANGE,
                    config.SLOW_EMA_RANGE,
                    config.OPTIMIZATION_WINDOW_DAYS
                )
                self.state_manager.update_ema_periods(symbol, fast_period, slow_period)
            
            # Calculate indicators
            fast_ema = calculate_ema(close, fast_period)
            slow_ema = calculate_ema(close, slow_period)
            
            fast_ema_15m = calculate_ema(bars_15m['close'], fast_period)
            slow_ema_15m = calculate_ema(bars_15m['close'], slow_period)
            
            sma_200 = calculate_sma(bars_daily['close'], 200)
            rsi = calculate_rsi(close)
            macd_line, signal_line, macd_hist = calculate_macd(close)
            adx = calculate_adx(high, low, close)
            atr = calculate_atr(high, low, close)
            atr_pct = calculate_atr_percent(high, low, close)
            
            current_price = close.iloc[-1]
            current_rsi = rsi.iloc[-1]
            current_adx = adx.iloc[-1]
            current_atr = atr.iloc[-1]
            current_atr_pct = atr_pct.iloc[-1]
            current_macd_hist = macd_hist.iloc[-1]
            
            # Determine volatility regime
            vol_regime = calculate_volatility_regime(atr_pct)
            
            # Check for crossover
            bullish_cross, bearish_cross = detect_ema_crossover(fast_ema, slow_ema)
            
            # Check trend filter (200 SMA)
            above_200sma = is_above_sma(current_price, sma_200)
            below_200sma = is_below_sma(current_price, sma_200)
            
            # Gap filter
            prev_close = self.data_manager.get_previous_close(symbol)
            if prev_close:
                gap_pct = calculate_gap_percent(bars_daily['open'].iloc[-1], prev_close)
                gap_day = is_gap_day(gap_pct, config.GAP_THRESHOLD)
                
                # Check if we're in gap skip period
                now = datetime.now(self.tz)
                market_open_time = datetime.combine(now.date(), config.MARKET_OPEN_DUBLIN)
                market_open_time = self.tz.localize(market_open_time)
                minutes_since_open = (now - market_open_time).total_seconds() / 60
                
                if gap_day and minutes_since_open < config.GAP_SKIP_MINUTES:
                    self.trade_logger.log_shadow_signal(
                        symbol, "LONG" if bullish_cross else "SHORT", "Gap filter",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
            
            # Determine signal type and validate
            signal_type = None
            
            # LONG SIGNAL
            if bullish_cross and above_200sma and market_bullish:
                # Multi-timeframe confirmation
                if not is_trend_bullish(fast_ema_15m, slow_ema_15m):
                    self.trade_logger.log_shadow_signal(
                        symbol, "LONG", "15m trend disagrees",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                # Regime filter
                if current_adx < config.ADX_THRESHOLD:
                    self.trade_logger.log_shadow_signal(
                        symbol, "LONG", "Low ADX",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                # ATR filter
                if current_atr_pct < config.ATR_PERCENT_THRESHOLD:
                    self.trade_logger.log_shadow_signal(
                        symbol, "LONG", "Low ATR%",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                # Momentum confirmation (adaptive thresholds)
                rsi_threshold = config.RSI_HIGH_VOL_LONG if vol_regime == "high" else config.RSI_LONG_THRESHOLD
                macd_threshold = config.MACD_HIGH_VOL_LONG if vol_regime == "high" else config.MACD_LONG_THRESHOLD
                
                if not (current_rsi > rsi_threshold or current_macd_hist > macd_threshold):
                    self.trade_logger.log_shadow_signal(
                        symbol, "LONG", "Momentum confirmation failed",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                # Don't chase guard
                if not check_dont_chase(current_price, slow_ema.iloc[-1], current_atr):
                    self.trade_logger.log_shadow_signal(
                        symbol, "LONG", "Don't chase",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                signal_type = "LONG"
            
            # SHORT SIGNAL
            elif bearish_cross and below_200sma and market_bearish:
                # Multi-timeframe confirmation
                if not is_trend_bearish(fast_ema_15m, slow_ema_15m):
                    self.trade_logger.log_shadow_signal(
                        symbol, "SHORT", "15m trend disagrees",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                # Regime filter
                if current_adx < config.ADX_THRESHOLD:
                    self.trade_logger.log_shadow_signal(
                        symbol, "SHORT", "Low ADX",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                # ATR filter
                if current_atr_pct < config.ATR_PERCENT_THRESHOLD:
                    self.trade_logger.log_shadow_signal(
                        symbol, "SHORT", "Low ATR%",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                # Momentum confirmation (adaptive thresholds)
                rsi_threshold = config.RSI_HIGH_VOL_SHORT if vol_regime == "high" else config.RSI_SHORT_THRESHOLD
                macd_threshold = config.MACD_HIGH_VOL_SHORT if vol_regime == "high" else config.MACD_SHORT_THRESHOLD
                
                if not (current_rsi < rsi_threshold or current_macd_hist < macd_threshold):
                    self.trade_logger.log_shadow_signal(
                        symbol, "SHORT", "Momentum confirmation failed",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                # Don't chase guard
                if not check_dont_chase(current_price, slow_ema.iloc[-1], current_atr):
                    self.trade_logger.log_shadow_signal(
                        symbol, "SHORT", "Don't chase",
                        current_price, 0, 0, fast_period, slow_period,
                        current_rsi, current_adx, current_atr_pct
                    )
                    return None
                
                signal_type = "SHORT"
            
            if signal_type is None:
                return None
            
            # Liquidity filter
            spread = self.data_manager.get_spread_estimate(symbol)
            adv = self.data_manager.calculate_adv_dollars(symbol)
            
            if spread > config.MAX_SPREAD_BPS or adv < config.MIN_ADV_DOLLARS or current_price < config.MIN_PRICE:
                self.trade_logger.log_shadow_signal(
                    symbol, signal_type, "Liquidity filter",
                    current_price, 0, 0, fast_period, slow_period,
                    current_rsi, current_adx, current_atr_pct
                )
                return None
            
            # Calculate stop and position size
            is_long = signal_type == "LONG"
            stop_price = calculate_trailing_stop(
                current_price, current_price, current_atr,
                vol_regime, is_long
            )
            
            return {
                'symbol': symbol,
                'signal_type': signal_type,
                'entry_price': current_price,
                'stop_price': stop_price,
                'atr': current_atr,
                'atr_pct': current_atr_pct,
                'rsi': current_rsi,
                'adx': current_adx,
                'ema_fast': fast_period,
                'ema_slow': slow_period,
                'vol_regime': vol_regime,
                'spread': spread
            }
            
        except Exception as e:
            logger.error(f"Error checking signal for {symbol}: {e}")
            return None
    
    def _execute_entry(self, signal: Dict, equity: float, positions: List[Dict]):
        """Execute an entry trade."""
        symbol = signal['symbol']
        is_long = signal['signal_type'] == "LONG"
        entry_price = signal['entry_price']
        stop_price = signal['stop_price']
        
        # Calculate position size
        shares, risk_amount = self.risk_manager.calculate_position_size(
            equity, entry_price, stop_price, signal['spread'] * entry_price / 10000
        )
        
        # Check total risk capacity
        if not self.risk_manager.check_total_risk_capacity(risk_amount, equity):
            self.trade_logger.log_shadow_signal(
                symbol, signal['signal_type'], "Risk cap exceeded",
                entry_price, stop_price, shares,
                signal['ema_fast'], signal['ema_slow'],
                signal['rsi'], signal['adx'], signal['atr_pct']
            )
            return
        
        # Check sector exposure
        position_value = shares * entry_price
        if not self.risk_manager.check_sector_exposure(symbol, position_value, positions, equity):
            self.trade_logger.log_shadow_signal(
                symbol, signal['signal_type'], "Sector cap exceeded",
                entry_price, stop_price, shares,
                signal['ema_fast'], signal['ema_slow'],
                signal['rsi'], signal['adx'], signal['atr_pct']
            )
            return
        
        # Adjust for observed slippage
        observed_slip = self.state_manager.get_observed_slippage(symbol)
        shares = self.order_manager.adjust_size_for_slippage(shares, observed_slip)
        
        # Submit order
        side = "buy" if is_long else "sell"
        order = self.order_manager.submit_market_order(symbol, shares, side)
        
        if order is None:
            self._handle_error(f"Failed to submit entry order for {symbol}")
            return
        
        # Wait briefly for fill
        time.sleep(1)
        
        # Check fill
        filled_order = self.order_manager.get_order(order['order_id'])
        if filled_order is None or filled_order['status'] not in ['filled', 'partially_filled']:
            logger.warning(f"Entry order for {symbol} not immediately filled")
            return
        
        fill_price = filled_order.get('filled_avg_price', entry_price)
        filled_qty = int(filled_order.get('filled_qty', shares))
        
        # Calculate slippage
        slippage = self.order_manager.calculate_slippage(entry_price, fill_price)
        self.state_manager.update_observed_slippage(symbol, slippage)
        
        # Recalculate stop based on fill price
        actual_stop = calculate_trailing_stop(
            fill_price, fill_price, signal['atr'],
            signal['vol_regime'], is_long
        )
        
        # Submit stop order
        stop_side = "sell" if is_long else "buy"
        stop_order = self.order_manager.submit_trailing_stop_order(
            symbol, filled_qty, stop_side,
            trail_percent=abs(fill_price - actual_stop) / fill_price * 100
        )
        
        # Log trade
        risk_pct = risk_amount / equity
        trade_id = self.trade_logger.log_entry(
            symbol=symbol,
            side="LONG" if is_long else "SHORT",
            entry_price=fill_price,
            qty=filled_qty,
            stop_price=actual_stop,
            risk_amount=risk_amount,
            risk_percent=risk_pct,
            signal_type="EMA Crossover",
            ema_fast=signal['ema_fast'],
            ema_slow=signal['ema_slow'],
            rsi=signal['rsi'],
            adx=signal['adx'],
            atr_percent=signal['atr_pct'],
            regime=signal['vol_regime'],
            notes=f"Slippage: {slippage:.1f}bps"
        )
        
        # Update state
        self.state_manager.update_trade(trade_id, {
            'symbol': symbol,
            'side': 'long' if is_long else 'short',
            'entry_price': fill_price,
            'qty': filled_qty,
            'stop_price': actual_stop,
            'risk_amount': risk_amount,
            'entry_time': datetime.now().isoformat(),
            'ema_fast': signal['ema_fast'],
            'ema_slow': signal['ema_slow'],
            'vol_regime': signal['vol_regime'],
            'pyramid_adds': 0
        })
        
        if stop_order:
            self.state_manager.update_stop(symbol, stop_order['order_id'], actual_stop)
        
        self.risk_manager.register_trade_risk(symbol, risk_amount)
        self.session_trades.append(trade_id)
        
        logger.info(f"Entry executed: {trade_id} {side.upper()} {filled_qty} {symbol} @ ${fill_price:.2f}")
    
    def _manage_exits(self, equity: float):
        """Manage exits for all open positions."""
        active_trades = self.state_manager.get_active_trades()
        
        for trade_id, trade in list(active_trades.items()):
            symbol = trade['symbol']
            
            try:
                # Get current position from broker
                position = self.order_manager.get_position(symbol)
                if position is None:
                    # Position was closed (stop hit)
                    self._handle_closed_position(trade_id, trade)
                    continue
                
                # Get current market data
                bars = self.data_manager.get_bars(symbol, "5Min", lookback_days=5)
                if bars.empty:
                    continue
                
                current_price = bars['close'].iloc[-1]
                is_long = trade['side'] == 'long'
                entry_price = trade['entry_price']
                stop_distance = abs(entry_price - trade['stop_price'])
                
                # Calculate R-multiple
                r_mult = calculate_r_multiple(entry_price, current_price, stop_distance, is_long)
                
                # Increment bars held
                bars_held = self.state_manager.increment_bars_held(trade_id)
                
                # Check time stop
                if bars_held >= config.TIME_STOP_BARS and r_mult < config.TIME_STOP_MIN_R:
                    self._exit_trade(trade_id, trade, current_price, "Time stop", bars_held)
                    continue
                
                # Check opposite EMA cross
                fast_ema = calculate_ema(bars['close'], trade['ema_fast'])
                slow_ema = calculate_ema(bars['close'], trade['ema_slow'])
                bullish_cross, bearish_cross = detect_ema_crossover(fast_ema, slow_ema)
                
                if (is_long and bearish_cross) or (not is_long and bullish_cross):
                    self._exit_trade(trade_id, trade, current_price, "Opposite EMA cross", bars_held)
                    continue
                
                # Check partial profit taking at +1.5R
                if r_mult >= config.PARTIAL_TAKE_PROFIT_R and not trade.get('partial_taken'):
                    self._take_partial_profit(trade_id, trade, position, current_price)
                
                # Update trailing stop
                atr = calculate_atr(bars['high'], bars['low'], bars['close'])
                new_stop = calculate_trailing_stop(
                    entry_price, current_price, atr.iloc[-1],
                    trade['vol_regime'], is_long
                )
                
                # Only update if more favorable
                current_stop = trade['stop_price']
                if (is_long and new_stop > current_stop) or (not is_long and new_stop < current_stop):
                    self._update_stop(trade_id, trade, new_stop)
                
                # Log alternative exits for shadow mode
                self._log_alternative_exits(trade_id, entry_price, current_price, stop_distance, is_long, r_mult)
                
            except Exception as e:
                logger.error(f"Error managing exit for {trade_id}: {e}")
    
    def _exit_trade(
        self,
        trade_id: str,
        trade: Dict,
        exit_price: float,
        reason: str,
        bars_held: int
    ):
        """Exit a trade completely."""
        symbol = trade['symbol']
        is_long = trade['side'] == 'long'
        entry_price = trade['entry_price']
        qty = trade['qty']
        
        # Close position
        close_result = self.order_manager.close_position(symbol)
        if close_result is None:
            logger.error(f"Failed to close position for {symbol}")
            return
        
        # Calculate P&L
        if is_long:
            pnl = (exit_price - entry_price) * qty
        else:
            pnl = (entry_price - exit_price) * qty
        
        pnl_pct = pnl / (entry_price * qty)
        stop_distance = abs(entry_price - trade['stop_price'])
        r_mult = calculate_r_multiple(entry_price, exit_price, stop_distance, is_long)
        
        # Get slippage (approximate)
        slippage = self.state_manager.get_observed_slippage(symbol)
        
        # Log exit
        self.trade_logger.log_exit(
            trade_id=trade_id,
            exit_price=exit_price,
            exit_reason=reason,
            pnl_dollars=pnl,
            pnl_percent=pnl_pct,
            r_multiple=r_mult,
            slippage_bps=slippage,
            bars_held=bars_held
        )
        
        # Update tracking
        self.state_manager.remove_trade(trade_id)
        self.state_manager.remove_stop(symbol)
        self.risk_manager.unregister_trade_risk(symbol)
        self.risk_manager.update_daily_pnl(pnl)
        self.risk_manager.record_trade_result(pnl >= 0)
        
        self.session_pnl.append(pnl)
        
        logger.info(f"Exit: {trade_id} {symbol} @ ${exit_price:.2f} | PnL: ${pnl:.2f} ({r_mult:.2f}R) | Reason: {reason}")
    
    def _handle_closed_position(self, trade_id: str, trade: Dict):
        """Handle a position that was closed externally (stop hit)."""
        symbol = trade['symbol']
        
        # Get last price as approximate exit
        latest = self.data_manager.get_latest_bar(symbol)
        exit_price = latest['close'] if latest else trade['stop_price']
        
        bars_held = self.state_manager.get_bars_held(trade_id)
        
        self._exit_trade(trade_id, trade, exit_price, "Stop hit", bars_held)
    
    def _take_partial_profit(
        self,
        trade_id: str,
        trade: Dict,
        position: Dict,
        current_price: float
    ):
        """Take partial profits at target R-multiple."""
        symbol = trade['symbol']
        is_long = trade['side'] == 'long'
        current_qty = int(position['qty'])
        
        # Calculate partial size
        partial_qty = int(current_qty * config.PARTIAL_TAKE_PERCENT)
        if partial_qty < 1:
            return
        
        # Submit partial exit
        side = "sell" if is_long else "buy"
        order = self.order_manager.submit_market_order(symbol, partial_qty, side)
        
        if order:
            # Update trade state
            trade['partial_taken'] = True
            trade['qty'] = current_qty - partial_qty
            self.state_manager.update_trade(trade_id, trade)
            
            logger.info(f"Partial profit taken: {partial_qty} shares of {symbol} @ ${current_price:.2f}")
    
    def _update_stop(self, trade_id: str, trade: Dict, new_stop: float):
        """Update trailing stop for a trade."""
        symbol = trade['symbol']
        is_long = trade['side'] == 'long'
        
        # Cancel existing stop
        pending_stops = self.state_manager.get_pending_stops()
        if symbol in pending_stops:
            self.order_manager.cancel_order(pending_stops[symbol]['order_id'])
        
        # Submit new stop
        stop_side = "sell" if is_long else "buy"
        qty = trade['qty']
        
        stop_order = self.order_manager.submit_stop_order(
            symbol, qty, stop_side, new_stop
        )
        
        if stop_order:
            trade['stop_price'] = new_stop
            self.state_manager.update_trade(trade_id, trade)
            self.state_manager.update_stop(symbol, stop_order['order_id'], new_stop)
    
    def _log_alternative_exits(
        self,
        trade_id: str,
        entry_price: float,
        current_price: float,
        stop_distance: float,
        is_long: bool,
        current_r: float
    ):
        """Log alternative exit strategy results for shadow mode."""
        # Strategy 1: Scale-out 25% at +1R, 25% at +2R
        if current_r >= 1.0:
            self.trade_logger.log_alternative_exit(
                trade_id, "Scale 25% @1R, 25% @2R",
                current_price, 0, current_r,  # Simplified
                "Would have taken 25% at +1R"
            )
        
        # Strategy 2: Scale-out 50% at +2R
        if current_r >= 2.0:
            self.trade_logger.log_alternative_exit(
                trade_id, "Scale 50% @2R",
                current_price, 0, current_r,
                "Would have taken 50% at +2R"
            )
    
    def _flatten_all(self, reason: str):
        """Flatten all positions."""
        logger.warning(f"Flattening all positions: {reason}")
        
        # Close all positions
        self.order_manager.close_all_positions()
        
        # Cancel all orders
        self.order_manager.cancel_all_orders()
        
        # Update state
        for trade_id in list(self.state_manager.get_active_trades().keys()):
            self.state_manager.remove_trade(trade_id)
        
        for symbol in list(self.state_manager.get_pending_stops().keys()):
            self.state_manager.remove_stop(symbol)
        
        self.state_manager.set_paused(True)
    
    def _handle_error(self, error_msg: str):
        """Handle errors and check kill-switch."""
        self.daily_errors += 1
        self.state_manager.update_error_count(self.daily_errors)
        
        logger.error(error_msg)
        
        if self.order_manager.should_trigger_kill_switch():
            logger.critical("KILL SWITCH TRIGGERED")
            self._flatten_all("Kill switch triggered")
            self.state_manager.set_kill_switch(True)
            self.email_notifier.send_kill_switch_alert(
                f"Too many consecutive errors: {error_msg}"
            )
    
    def end_of_day_report(self):
        """Generate and send end-of-day report."""
        account = self.order_manager.get_account()
        equity = account['equity'] if account else 0
        
        # Calculate statistics
        total_trades = len(self.session_trades)
        winners = sum(1 for p in self.session_pnl if p >= 0)
        losers = total_trades - winners
        
        winning_pnl = [p for p in self.session_pnl if p >= 0]
        losing_pnl = [p for p in self.session_pnl if p < 0]
        
        avg_win = sum(winning_pnl) / len(winning_pnl) if winning_pnl else 0
        avg_loss = sum(losing_pnl) / len(losing_pnl) if losing_pnl else 0
        
        daily_pnl = sum(self.session_pnl)
        daily_pnl_pct = daily_pnl / self.risk_manager.daily_start_equity if self.risk_manager.daily_start_equity > 0 else 0
        
        # Log to Excel
        self.trade_logger.log_daily_summary(
            date_str=date.today().strftime('%Y-%m-%d'),
            starting_equity=self.risk_manager.daily_start_equity,
            ending_equity=equity,
            daily_pnl=daily_pnl,
            daily_pnl_percent=daily_pnl_pct,
            trades=total_trades,
            winners=winners,
            losers=losers,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_drawdown=self.risk_manager.get_risk_summary(equity)['current_drawdown'],
            total_slippage=0,  # Would need to aggregate
            errors=self.daily_errors,
            equity_slope=0  # Would calculate from history
        )
        
        # Send email report
        stats = {
            'daily_pnl': daily_pnl,
            'daily_pnl_percent': daily_pnl_pct,
            'win_rate': winners / total_trades if total_trades > 0 else 0,
            'trades': total_trades,
            'winners': winners,
            'losers': losers,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': (avg_win * winners) / (abs(avg_loss) * losers) if losers > 0 and avg_loss != 0 else 0
        }
        
        risk_summary = self.risk_manager.get_risk_summary(equity)
        
        self.email_notifier.send_daily_report(
            date.today().strftime('%Y-%m-%d'),
            stats,
            risk_summary,
            self.daily_errors
        )
    
    def graceful_shutdown(self):
        """Perform graceful shutdown."""
        logger.info("Initiating graceful shutdown...")
        
        # Save state
        self.state_manager.save_state()
        
        # Re-arm stops for overnight (if holding positions)
        self._rearm_stops()
        
        logger.info("Shutdown complete")
