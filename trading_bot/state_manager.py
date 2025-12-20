"""
State Manager Module
====================
Handles state persistence and recovery for self-healing restarts.
"""

import json
import os
from datetime import datetime, date
from typing import Dict, List, Any, Optional
import logging

import config

logger = logging.getLogger(__name__)


class StateManager:
    """Manages bot state persistence and recovery."""
    
    STATE_FILE = "bot_state.json"
    
    def __init__(self):
        self.state_path = os.path.join(config.LOG_DIR, self.STATE_FILE)
        self.state: Dict[str, Any] = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        """Load state from file."""
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, 'r') as f:
                    state = json.load(f)
                logger.info("State loaded from file")
                return state
            except Exception as e:
                logger.error(f"Error loading state: {e}")
        
        return self._default_state()
    
    def _default_state(self) -> Dict[str, Any]:
        """Return default state structure."""
        return {
            'last_run': None,
            'last_session_date': None,
            'active_trades': {},
            'pending_stops': {},
            'daily_pnl': 0.0,
            'daily_start_equity': 0.0,
            'consecutive_losses': 0,
            'peak_equity': 0.0,
            'trade_counter': 0,
            'ema_periods': {},  # symbol -> {fast, slow}
            'last_universe_update': None,
            'universe': config.TRADING_UNIVERSE.copy(),
            'error_count': 0,
            'kill_switch_active': False,
            'paused_until_next_session': False,
            'circuit_breaker_active': False,
            'bars_since_entry': {},  # trade_id -> bar_count
            'observed_slippage': {}  # symbol -> avg slippage bps
        }
    
    def save_state(self):
        """Save current state to file."""
        try:
            os.makedirs(config.LOG_DIR, exist_ok=True)
            self.state['last_run'] = datetime.now().isoformat()
            
            with open(self.state_path, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
            
            logger.debug("State saved")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def update_trade(self, trade_id: str, trade_data: Dict[str, Any]):
        """Update or add a trade to state."""
        self.state['active_trades'][trade_id] = trade_data
        self.save_state()
    
    def remove_trade(self, trade_id: str):
        """Remove a closed trade from state."""
        if trade_id in self.state['active_trades']:
            del self.state['active_trades'][trade_id]
        if trade_id in self.state['bars_since_entry']:
            del self.state['bars_since_entry'][trade_id]
        self.save_state()
    
    def get_active_trades(self) -> Dict[str, Dict]:
        """Get all active trades."""
        return self.state.get('active_trades', {})
    
    def update_stop(self, symbol: str, stop_order_id: str, stop_price: float):
        """Track pending stop orders."""
        self.state['pending_stops'][symbol] = {
            'order_id': stop_order_id,
            'stop_price': stop_price,
            'updated_at': datetime.now().isoformat()
        }
        self.save_state()
    
    def remove_stop(self, symbol: str):
        """Remove stop order tracking."""
        if symbol in self.state['pending_stops']:
            del self.state['pending_stops'][symbol]
            self.save_state()
    
    def get_pending_stops(self) -> Dict[str, Dict]:
        """Get all pending stop orders."""
        return self.state.get('pending_stops', {})
    
    def update_daily_stats(
        self,
        daily_pnl: float,
        daily_start_equity: float,
        consecutive_losses: int,
        peak_equity: float
    ):
        """Update daily statistics."""
        self.state['daily_pnl'] = daily_pnl
        self.state['daily_start_equity'] = daily_start_equity
        self.state['consecutive_losses'] = consecutive_losses
        self.state['peak_equity'] = peak_equity
        self.state['last_session_date'] = date.today().isoformat()
        self.save_state()
    
    def update_ema_periods(self, symbol: str, fast: int, slow: int):
        """Store optimized EMA periods for a symbol."""
        self.state['ema_periods'][symbol] = {
            'fast': fast,
            'slow': slow,
            'optimized_at': datetime.now().isoformat()
        }
        self.save_state()
    
    def get_ema_periods(self, symbol: str) -> Optional[Dict[str, int]]:
        """Get stored EMA periods for a symbol."""
        return self.state.get('ema_periods', {}).get(symbol)
    
    def update_universe(self, universe: List[str]):
        """Update trading universe."""
        self.state['universe'] = universe
        self.state['last_universe_update'] = datetime.now().isoformat()
        self.save_state()
    
    def get_universe(self) -> List[str]:
        """Get current trading universe."""
        return self.state.get('universe', config.TRADING_UNIVERSE.copy())
    
    def should_update_universe(self) -> bool:
        """Check if universe should be updated (monthly)."""
        last_update = self.state.get('last_universe_update')
        if last_update is None:
            return True
        
        try:
            last_date = datetime.fromisoformat(last_update)
            days_since = (datetime.now() - last_date).days
            return days_since >= 30
        except:
            return True
    
    def increment_trade_counter(self) -> int:
        """Increment and return trade counter."""
        self.state['trade_counter'] = self.state.get('trade_counter', 0) + 1
        self.save_state()
        return self.state['trade_counter']
    
    def update_error_count(self, count: int):
        """Update error count for kill-switch tracking."""
        self.state['error_count'] = count
        self.save_state()
    
    def set_kill_switch(self, active: bool):
        """Set kill-switch status."""
        self.state['kill_switch_active'] = active
        self.save_state()
    
    def is_kill_switch_active(self) -> bool:
        """Check if kill-switch is active."""
        return self.state.get('kill_switch_active', False)
    
    def set_paused(self, paused: bool):
        """Set paused status."""
        self.state['paused_until_next_session'] = paused
        self.save_state()
    
    def is_paused(self) -> bool:
        """Check if trading is paused."""
        return self.state.get('paused_until_next_session', False)
    
    def set_circuit_breaker(self, active: bool):
        """Set circuit breaker status."""
        self.state['circuit_breaker_active'] = active
        self.save_state()
    
    def is_circuit_breaker_active(self) -> bool:
        """Check if circuit breaker is active."""
        return self.state.get('circuit_breaker_active', False)
    
    def increment_bars_held(self, trade_id: str) -> int:
        """Increment bars held counter for a trade."""
        current = self.state.get('bars_since_entry', {}).get(trade_id, 0)
        self.state.setdefault('bars_since_entry', {})[trade_id] = current + 1
        self.save_state()
        return current + 1
    
    def get_bars_held(self, trade_id: str) -> int:
        """Get bars held for a trade."""
        return self.state.get('bars_since_entry', {}).get(trade_id, 0)
    
    def update_observed_slippage(self, symbol: str, slippage_bps: float):
        """Update observed slippage for a symbol (rolling average)."""
        current = self.state.get('observed_slippage', {}).get(symbol, slippage_bps)
        # Exponential moving average
        new_avg = 0.7 * current + 0.3 * slippage_bps
        self.state.setdefault('observed_slippage', {})[symbol] = new_avg
        self.save_state()
    
    def get_observed_slippage(self, symbol: str) -> float:
        """Get observed slippage for a symbol."""
        return self.state.get('observed_slippage', {}).get(symbol, config.TARGET_SLIPPAGE_BPS)
    
    def reset_for_new_session(self):
        """Reset session-specific state for new trading day."""
        today = date.today().isoformat()
        if self.state.get('last_session_date') != today:
            self.state['daily_pnl'] = 0.0
            self.state['consecutive_losses'] = 0
            self.state['paused_until_next_session'] = False
            self.state['circuit_breaker_active'] = False
            self.state['error_count'] = 0
            self.state['last_session_date'] = today
            self.save_state()
            logger.info("State reset for new session")
    
    def reconcile_positions(self, broker_positions: List[Dict]) -> Dict[str, Any]:
        """
        Reconcile state with actual broker positions.
        Returns discrepancies found.
        """
        discrepancies = {
            'missing_in_state': [],
            'missing_in_broker': [],
            'qty_mismatch': []
        }
        
        state_trades = self.get_active_trades()
        state_symbols = {t['symbol'] for t in state_trades.values()}
        broker_symbols = {p['symbol'] for p in broker_positions}
        
        # Positions in broker but not in state
        for pos in broker_positions:
            if pos['symbol'] not in state_symbols:
                discrepancies['missing_in_state'].append(pos)
                logger.warning(f"Position {pos['symbol']} in broker but not in state")
        
        # Positions in state but not in broker
        for trade_id, trade in state_trades.items():
            if trade['symbol'] not in broker_symbols:
                discrepancies['missing_in_broker'].append(trade)
                logger.warning(f"Trade {trade_id} in state but not in broker")
                # Clean up state
                self.remove_trade(trade_id)
        
        return discrepancies
    
    def get_full_state(self) -> Dict[str, Any]:
        """Get complete state for debugging."""
        return self.state.copy()
