"""
Technical Indicators Module
===========================
All technical indicator calculations for the trading bot.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional


def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return data.ewm(span=period, adjust=False).mean()


def calculate_sma(data: pd.Series, period: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    return data.rolling(window=period).mean()


def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD, Signal line, and Histogram."""
    ema_fast = calculate_ema(data, fast)
    ema_slow = calculate_ema(data, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr


def calculate_atr_percent(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate ATR as percentage of price."""
    atr = calculate_atr(high, low, close, period)
    return atr / close


def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Average Directional Index (ADX)."""
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[(plus_dm < minus_dm)] = 0
    minus_dm[(minus_dm < plus_dm)] = 0
    
    atr = calculate_atr(high, low, close, period)
    plus_di = 100 * calculate_ema(plus_dm, period) / atr
    minus_di = 100 * calculate_ema(minus_dm, period) / atr
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = calculate_ema(dx, period)
    return adx


def detect_ema_crossover(fast_ema: pd.Series, slow_ema: pd.Series) -> Tuple[bool, bool]:
    """
    Detect EMA crossover.
    Returns (bullish_cross, bearish_cross).
    """
    if len(fast_ema) < 2 or len(slow_ema) < 2:
        return False, False
    
    prev_fast = fast_ema.iloc[-2]
    prev_slow = slow_ema.iloc[-2]
    curr_fast = fast_ema.iloc[-1]
    curr_slow = slow_ema.iloc[-1]
    
    bullish_cross = prev_fast <= prev_slow and curr_fast > curr_slow
    bearish_cross = prev_fast >= prev_slow and curr_fast < curr_slow
    
    return bullish_cross, bearish_cross


def is_trend_bullish(fast_ema: pd.Series, slow_ema: pd.Series) -> bool:
    """Check if current trend is bullish (fast EMA > slow EMA)."""
    if len(fast_ema) < 1 or len(slow_ema) < 1:
        return False
    return fast_ema.iloc[-1] > slow_ema.iloc[-1]


def is_trend_bearish(fast_ema: pd.Series, slow_ema: pd.Series) -> bool:
    """Check if current trend is bearish (fast EMA < slow EMA)."""
    if len(fast_ema) < 1 or len(slow_ema) < 1:
        return False
    return fast_ema.iloc[-1] < slow_ema.iloc[-1]


def is_above_sma(price: float, sma: pd.Series) -> bool:
    """Check if price is above SMA."""
    if len(sma) < 1 or pd.isna(sma.iloc[-1]):
        return False
    return price > sma.iloc[-1]


def is_below_sma(price: float, sma: pd.Series) -> bool:
    """Check if price is below SMA."""
    if len(sma) < 1 or pd.isna(sma.iloc[-1]):
        return False
    return price < sma.iloc[-1]


def calculate_volatility_regime(atr_percent: pd.Series, lookback: int = 20) -> str:
    """
    Determine volatility regime based on ATR%.
    Returns 'high', 'normal', or 'low'.
    """
    if len(atr_percent) < lookback:
        return "normal"
    
    current_atr = atr_percent.iloc[-1]
    median_atr = atr_percent.iloc[-lookback:].median()
    
    if current_atr > median_atr * 1.5:
        return "high"
    elif current_atr < median_atr * 0.7:
        return "low"
    return "normal"


def optimize_ema_periods(
    close: pd.Series,
    fast_range: Tuple[int, int],
    slow_range: Tuple[int, int],
    window_days: int = 90
) -> Tuple[int, int]:
    """
    Walk-forward optimization of EMA periods based on Sharpe ratio.
    Returns optimal (fast_period, slow_period).
    """
    best_sharpe = -np.inf
    best_fast = fast_range[0]
    best_slow = slow_range[0]
    
    if len(close) < window_days:
        return best_fast, best_slow
    
    window_close = close.iloc[-window_days:]
    
    for fast in range(fast_range[0], fast_range[1] + 1):
        for slow in range(slow_range[0], slow_range[1] + 1):
            if fast >= slow:
                continue
            
            fast_ema = calculate_ema(window_close, fast)
            slow_ema = calculate_ema(window_close, slow)
            
            # Simulate simple crossover returns
            position = (fast_ema > slow_ema).astype(int)
            position = position.shift(1).fillna(0)
            returns = window_close.pct_change() * position
            
            if returns.std() > 0:
                sharpe = returns.mean() / returns.std() * np.sqrt(252)
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_fast = fast
                    best_slow = slow
    
    return best_fast, best_slow


def calculate_entry_to_ema_distance(entry_price: float, ema_value: float) -> float:
    """Calculate distance from entry price to EMA as absolute value."""
    return abs(entry_price - ema_value)


def check_dont_chase(entry_price: float, ema_value: float, atr: float, multiplier: float = 0.75) -> bool:
    """
    Check if entry passes the 'don't chase' guard.
    Returns True if entry is allowed (not chasing).
    """
    distance = calculate_entry_to_ema_distance(entry_price, ema_value)
    max_distance = atr * multiplier
    return distance <= max_distance


def calculate_gap_percent(current_open: float, previous_close: float) -> float:
    """Calculate gap as percentage from prior close."""
    if previous_close == 0:
        return 0
    return (current_open - previous_close) / previous_close


def is_gap_day(gap_percent: float, threshold: float = 0.01) -> bool:
    """Check if gap exceeds threshold (default 1%)."""
    return abs(gap_percent) >= threshold


def calculate_trailing_stop(
    entry_price: float,
    current_price: float,
    atr: float,
    volatility_regime: str,
    is_long: bool,
    high_vol_mult: float = 1.5,
    low_vol_mult: float = 2.5
) -> float:
    """
    Calculate ATR-based trailing stop price.
    Returns the stop price.
    """
    if volatility_regime == "high":
        atr_mult = high_vol_mult
    else:
        atr_mult = low_vol_mult
    
    stop_distance = atr * atr_mult
    
    if is_long:
        return current_price - stop_distance
    else:
        return current_price + stop_distance


def calculate_position_size(
    account_equity: float,
    risk_percent: float,
    entry_price: float,
    stop_price: float
) -> int:
    """
    Calculate position size based on risk.
    Returns number of shares.
    """
    stop_distance = abs(entry_price - stop_price)
    if stop_distance == 0:
        return 0
    
    risk_amount = account_equity * risk_percent
    shares = int(risk_amount / stop_distance)
    return max(1, shares)


def calculate_r_multiple(entry_price: float, current_price: float, stop_distance: float, is_long: bool) -> float:
    """Calculate current R-multiple (profit/loss in terms of initial risk)."""
    if stop_distance == 0:
        return 0
    
    if is_long:
        pnl = current_price - entry_price
    else:
        pnl = entry_price - current_price
    
    return pnl / stop_distance


def calculate_equity_curve_slope(equity_values: pd.Series, lookback: int = 20) -> float:
    """
    Calculate linear regression slope of equity curve.
    Returns slope as % return per day.
    """
    if len(equity_values) < lookback:
        return 0.0
    
    recent = equity_values.iloc[-lookback:]
    x = np.arange(len(recent))
    
    if recent.iloc[0] == 0:
        return 0.0
    
    # Normalize to percentage returns
    normalized = (recent / recent.iloc[0] - 1) * 100
    
    # Linear regression
    slope, _ = np.polyfit(x, normalized, 1)
    return slope


def is_in_drawdown(current_equity: float, peak_equity: float, threshold: float = 0.02) -> bool:
    """Check if account is in drawdown."""
    if peak_equity == 0:
        return False
    drawdown = (peak_equity - current_equity) / peak_equity
    return drawdown > threshold
