"""
Risk Manager Module
===================
Handles position sizing, risk controls, and portfolio management.
"""

from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
import logging
import pandas as pd

import config
from indicators import calculate_equity_curve_slope, is_in_drawdown

logger = logging.getLogger(__name__)


class RiskManager:
    """Manages trading risk and position sizing."""
    
    def __init__(self):
        self.daily_pnl = 0.0
        self.daily_start_equity = 0.0
        self.consecutive_losses = 0
        self.peak_equity = 0.0
        self.equity_history: List[Tuple[date, float]] = []
        self.trade_risk: Dict[str, float] = {}  # symbol -> risk amount
        self.paused_until_next_session = False
        self.circuit_breaker_active = False
        self.last_session_date: Optional[date] = None
    
    def initialize_day(self, equity: float):
        """Initialize risk tracking for a new trading day."""
        today = date.today()
        
        if self.last_session_date != today:
            self.daily_pnl = 0.0
            self.daily_start_equity = equity
            self.paused_until_next_session = False
            self.circuit_breaker_active = False
            self.consecutive_losses = 0
            self.last_session_date = today
        
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        self.equity_history.append((today, equity))
        
        # Keep last 30 days
        if len(self.equity_history) > 30:
            self.equity_history = self.equity_history[-30:]
    
    def update_daily_pnl(self, pnl_change: float):
        """Update daily P&L tracking."""
        self.daily_pnl += pnl_change
    
    def record_trade_result(self, is_win: bool):
        """Record trade result for consecutive loss tracking."""
        if is_win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
                logger.warning(f"{self.consecutive_losses} consecutive losses - pausing entries")
                self.paused_until_next_session = True
    
    def check_daily_loss_limit(self) -> bool:
        """
        Check if daily loss limit has been hit.
        Returns True if trading should be paused.
        """
        if self.daily_start_equity == 0:
            return False
        
        daily_return = self.daily_pnl / self.daily_start_equity
        
        if daily_return <= -config.MAX_DAILY_LOSS:
            logger.warning(f"Daily loss limit hit: {daily_return:.2%}")
            self.paused_until_next_session = True
            return True
        
        return False
    
    def check_circuit_breaker(self, vix: Optional[float], spy_atr_percent: float, spy_atr_median: float) -> bool:
        """
        Check global circuit breaker conditions.
        Returns True if circuit breaker should be active.
        """
        # VIX check
        if vix and vix > config.VIX_THRESHOLD:
            logger.warning(f"Circuit breaker: VIX at {vix:.1f}")
            self.circuit_breaker_active = True
            return True
        
        # SPY ATR check
        if spy_atr_percent > spy_atr_median * config.SPY_ATR_CIRCUIT_BREAKER_MULT:
            logger.warning(f"Circuit breaker: SPY ATR% elevated")
            self.circuit_breaker_active = True
            return True
        
        self.circuit_breaker_active = False
        return False
    
    def can_enter_new_trade(self) -> bool:
        """Check if new entries are allowed."""
        if self.paused_until_next_session:
            logger.info("Entries paused until next session")
            return False
        
        if self.circuit_breaker_active:
            logger.info("Circuit breaker active - entries blocked")
            return False
        
        return True
    
    def calculate_position_size(
        self,
        account_equity: float,
        entry_price: float,
        stop_price: float,
        median_spread: float
    ) -> Tuple[int, float]:
        """
        Calculate position size based on risk parameters.
        Returns (shares, risk_amount).
        """
        stop_distance = abs(entry_price - stop_price)
        
        # Enforce minimum stop distance
        min_stop_spread = median_spread * config.MIN_STOP_SPREAD_MULTIPLIER
        min_stop_percent = entry_price * config.MIN_STOP_PERCENT
        min_stop = max(min_stop_spread, min_stop_percent)
        
        if stop_distance < min_stop:
            stop_distance = min_stop
            logger.info(f"Stop distance adjusted to minimum: ${stop_distance:.2f}")
        
        # Determine risk percent based on equity curve
        risk_percent = self.get_adjusted_risk_percent(account_equity)
        
        # Calculate risk amount
        risk_amount = account_equity * risk_percent
        
        # Calculate shares
        shares = int(risk_amount / stop_distance)
        
        # Ensure at least 1 share
        shares = max(1, shares)
        
        # Verify position doesn't exceed buying power checks handled by broker
        
        actual_risk = shares * stop_distance
        
        return shares, actual_risk
    
    def get_adjusted_risk_percent(self, current_equity: float) -> float:
        """
        Get risk percent adjusted for equity curve.
        """
        base_risk = config.RISK_PER_TRADE
        
        # Check if in drawdown
        if is_in_drawdown(current_equity, self.peak_equity):
            adjusted_risk = base_risk * (1 - config.DRAWDOWN_RISK_REDUCTION)
            logger.info(f"In drawdown - reducing risk to {adjusted_risk:.2%}")
            return max(config.MIN_RISK_PER_TRADE, adjusted_risk)
        
        # Check equity curve slope for boost
        if len(self.equity_history) >= config.EQUITY_CURVE_LOOKBACK:
            equity_series = pd.Series([e[1] for e in self.equity_history])
            slope = calculate_equity_curve_slope(equity_series, config.EQUITY_CURVE_LOOKBACK)
            
            if slope > 0.1:  # Rising steadily
                adjusted_risk = base_risk * (1 + config.EQUITY_CURVE_BOOST)
                logger.info(f"Equity rising - boosting risk to {adjusted_risk:.2%}")
                return min(config.MAX_RISK_PER_TRADE, adjusted_risk)
        
        return base_risk
    
    def check_total_risk_capacity(
        self,
        proposed_risk: float,
        account_equity: float
    ) -> bool:
        """
        Check if adding a new position would exceed total risk cap.
        """
        current_total_risk = sum(self.trade_risk.values())
        max_total_risk = account_equity * config.TOTAL_OPEN_RISK_CAP
        
        if current_total_risk + proposed_risk > max_total_risk:
            logger.warning(f"Total risk cap would be exceeded: {current_total_risk + proposed_risk:.2f} > {max_total_risk:.2f}")
            return False
        
        return True
    
    def check_position_limit(self, current_positions: int) -> bool:
        """Check if position limit allows new entry."""
        if current_positions >= config.MAX_CONCURRENT_POSITIONS:
            logger.info(f"Position limit reached: {current_positions}/{config.MAX_CONCURRENT_POSITIONS}")
            return False
        return True
    
    def check_sector_exposure(
        self,
        symbol: str,
        proposed_value: float,
        positions: List[dict],
        account_equity: float
    ) -> bool:
        """
        Check if sector exposure cap would be exceeded.
        """
        sector = config.SECTOR_MAP.get(symbol, "Unknown")
        
        # Calculate current sector exposure
        sector_exposure = 0.0
        for pos in positions:
            pos_sector = config.SECTOR_MAP.get(pos['symbol'], "Unknown")
            if pos_sector == sector:
                sector_exposure += abs(pos['market_value'])
        
        max_sector_exposure = account_equity * config.SECTOR_EXPOSURE_CAP
        
        if sector_exposure + proposed_value > max_sector_exposure:
            logger.warning(f"Sector cap would be exceeded for {sector}")
            return False
        
        return True
    
    def register_trade_risk(self, symbol: str, risk_amount: float):
        """Register risk for an open trade."""
        self.trade_risk[symbol] = risk_amount
    
    def unregister_trade_risk(self, symbol: str):
        """Remove risk tracking for a closed trade."""
        if symbol in self.trade_risk:
            del self.trade_risk[symbol]
    
    def can_pyramid(
        self,
        symbol: str,
        current_r_multiple: float,
        current_adds: int
    ) -> bool:
        """
        Check if pyramiding is allowed for a position.
        """
        if current_adds >= config.MAX_PYRAMID_ADDS:
            return False
        
        if current_r_multiple < config.PYRAMID_PROFIT_THRESHOLD:
            return False
        
        # Check total pyramided risk
        base_risk = self.trade_risk.get(symbol, 0)
        max_pyramid_risk = base_risk * config.MAX_PYRAMID_RISK_MULTIPLIER
        
        # This is a simplified check - actual implementation would track per-add risk
        return True
    
    def calculate_pyramid_size(
        self,
        base_shares: int,
        current_adds: int
    ) -> int:
        """
        Calculate size for pyramid add.
        Each add is smaller than the previous.
        """
        # Reduce size by 50% for each add
        reduction_factor = 0.5 ** current_adds
        return max(1, int(base_shares * reduction_factor))
    
    def get_risk_summary(self, account_equity: float) -> dict:
        """Get current risk summary."""
        total_risk = sum(self.trade_risk.values())
        return {
            'total_risk': total_risk,
            'total_risk_percent': total_risk / account_equity if account_equity > 0 else 0,
            'positions_at_risk': len(self.trade_risk),
            'daily_pnl': self.daily_pnl,
            'daily_pnl_percent': self.daily_pnl / self.daily_start_equity if self.daily_start_equity > 0 else 0,
            'consecutive_losses': self.consecutive_losses,
            'paused': self.paused_until_next_session,
            'circuit_breaker': self.circuit_breaker_active,
            'peak_equity': self.peak_equity,
            'current_drawdown': (self.peak_equity - account_equity) / self.peak_equity if self.peak_equity > 0 else 0
        }
