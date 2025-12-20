"""
Trading Bot Configuration
=========================
All configurable parameters for the 5-Minute EMA Crossover Bot.
"""

import os
from datetime import time
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# ALPACA API CREDENTIALS
# =============================================================================
# ⚠️ IMPORTANT: Replace these placeholder credentials with your real Alpaca API keys!
# Get your keys from: https://app.alpaca.markets/paper/dashboard/overview
# For paper trading, use the paper trading keys (not live!)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "PKXXXXXXXXXXXXXXXXXX")  # <-- REPLACE WITH YOUR API KEY
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")  # <-- REPLACE WITH YOUR SECRET KEY
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")  # Paper trading URL

# For LIVE trading (use with caution!):
# ALPACA_BASE_URL = "https://api.alpaca.markets"

# =============================================================================
# EMAIL CONFIGURATION
# =============================================================================
EMAIL_ADDRESS = "nicholascronnelly@icloud.com"
# For sending emails, you'll need to configure SMTP settings:
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.mail.me.com")  # iCloud SMTP
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")  # Your iCloud email
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # App-specific password

# =============================================================================
# TRADING HOURS (Dublin Time - Irish Standard Time / Irish Summer Time)
# =============================================================================
MARKET_OPEN_DUBLIN = time(14, 30)   # 14:30 Dublin = 9:30 AM ET
MARKET_CLOSE_DUBLIN = time(21, 0)   # 21:00 Dublin = 4:00 PM ET
ENTRY_START_DUBLIN = time(14, 35)   # Entries allowed from 14:35
ENTRY_END_DUBLIN = time(20, 30)     # No new entries after 20:30
FLAT_BY_DUBLIN = time(20, 58)       # Close all positions by 20:58
TIMEZONE = "Europe/Dublin"

# Gap filter: skip first 10 minutes after gap
GAP_SKIP_MINUTES = 10

# =============================================================================
# EMA CROSSOVER PARAMETERS
# =============================================================================
# Default EMA periods (will be optimized adaptively)
DEFAULT_FAST_EMA = 9
DEFAULT_SLOW_EMA = 21

# Adaptive EMA optimization ranges
FAST_EMA_RANGE = (9, 12)
SLOW_EMA_RANGE = (18, 24)

# Walk-forward optimization window
OPTIMIZATION_WINDOW_DAYS = 90

# Multi-timeframe confirmation
TIMEFRAME_5MIN = "5Min"
TIMEFRAME_15MIN = "15Min"
TIMEFRAME_1DAY = "1Day"

# =============================================================================
# ENTRY FILTERS
# =============================================================================
# Momentum confirmation
RSI_PERIOD = 14
RSI_LONG_THRESHOLD = 55      # RSI > 55 for longs
RSI_SHORT_THRESHOLD = 45     # RSI < 45 for shorts
RSI_HIGH_VOL_LONG = 60       # Higher threshold in high-vol regimes
RSI_HIGH_VOL_SHORT = 40      # Lower threshold in high-vol regimes

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
MACD_LONG_THRESHOLD = 0      # MACD histogram > 0 for longs
MACD_SHORT_THRESHOLD = 0     # MACD histogram < 0 for shorts
MACD_HIGH_VOL_LONG = 0.5     # Higher threshold in high-vol regimes
MACD_HIGH_VOL_SHORT = -0.5   # Lower threshold in high-vol regimes

# Regime filter
ADX_PERIOD = 14
ADX_THRESHOLD = 18           # Skip if ADX < 18 (choppy market)

# Trend filter
SMA_200_PERIOD = 200         # Daily 200 SMA for trend direction

# ATR filter
ATR_PERIOD = 14
ATR_PERCENT_THRESHOLD = 0.0015  # 0.15% of price minimum

# Gap filter
GAP_THRESHOLD = 0.01         # 1.0% gap threshold

# Don't chase guard
DONT_CHASE_ATR_MULTIPLIER = 0.75  # Entry-to-EMA21 distance <= 0.75× ATR

# =============================================================================
# LIQUIDITY FILTERS
# =============================================================================
MAX_SPREAD_BPS = 10          # Max median spread in basis points
MIN_ADV_DOLLARS = 50_000_000  # Minimum average daily volume in dollars
MIN_PRICE = 5.0              # Minimum stock price

# Universe selection criteria
UNIVERSE_MIN_ADV = 200_000_000  # $200M ADV for universe
UNIVERSE_MIN_PRICE = 10.0       # $10 minimum price
UNIVERSE_MAX_SPREAD_BPS = 5     # 5 bps max spread for universe

# =============================================================================
# MARKET BREADTH FILTER (SPY)
# =============================================================================
SPY_SYMBOL = "SPY"

# =============================================================================
# RISK & POSITION SIZING
# =============================================================================
RISK_PER_TRADE = 0.0075      # 0.75% of equity per trade
MIN_RISK_PER_TRADE = 0.005   # Minimum 0.5%
MAX_RISK_PER_TRADE = 0.01    # Maximum 1.0%

# Position limits
MAX_CONCURRENT_POSITIONS = 5
TOTAL_OPEN_RISK_CAP = 0.035  # 3.5% total equity at risk
SECTOR_EXPOSURE_CAP = 0.40   # 40% max in any sector

# Stop distance minimums
MIN_STOP_SPREAD_MULTIPLIER = 3   # Min stop >= 3× median spread
MIN_STOP_PERCENT = 0.005         # Min stop >= 0.5% of price

# Consecutive loss filter
MAX_CONSECUTIVE_LOSSES = 3

# Pyramiding
MAX_PYRAMID_ADDS = 2
PYRAMID_PROFIT_THRESHOLD = 1.0   # +1R unrealized profit to add
MAX_PYRAMID_RISK_MULTIPLIER = 1.5  # Total pyramided risk <= 1.5× base

# =============================================================================
# EXIT LOGIC
# =============================================================================
# Trailing stop (ATR-based)
TSL_HIGH_VOL_ATR_MULT = 1.5  # 1.5× ATR% in high volatility
TSL_LOW_VOL_ATR_MULT = 2.5   # 2.5× ATR% in low volatility

# Partial profit-taking
PARTIAL_TAKE_PROFIT_R = 1.5  # At +1.5R, take partial
PARTIAL_TAKE_PERCENT = 0.50  # Take 50% off

# Time stop
TIME_STOP_BARS = 12          # ~1 hour (12 × 5-min bars)
TIME_STOP_MIN_R = 0.25       # Exit if < +0.25R after time stop

# =============================================================================
# EXECUTION & ORDER MANAGEMENT
# =============================================================================
# Retry logic
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]     # Exponential backoff (seconds)
RETRY_JITTER_MAX = 0.5       # Random jitter up to 0.5s

# Partial fills
PARTIAL_FILL_WAIT_MINUTES = 2
PARTIAL_FILL_THRESHOLD = 0.70  # Reprice if < 70% filled

# Slippage
TARGET_SLIPPAGE_BPS = 5      # Target slippage in basis points
SLIPPAGE_SIZE_CAP = 0.50     # Cap size adjustment at ±50%

# Stale data
MAX_BAR_AGE_MINUTES = 3
MAX_GAP_ATR_MULTIPLIER = 8

# =============================================================================
# RISK CONTROLS
# =============================================================================
# Daily loss cap
MAX_DAILY_LOSS = 0.03        # -3% daily loss triggers flatten

# Global circuit breaker
VIX_THRESHOLD = 30
SPY_ATR_CIRCUIT_BREAKER_MULT = 2.0  # SPY ATR > 2× 20-day median

# News filter
EARNINGS_BLACKOUT_DAYS = 1   # Skip T-1 to T+1 around earnings
FED_EVENT_PAUSE_MINUTES = 30 # Pause ±30 min around Fed/CPI/payroll

# Equity curve scaling
EQUITY_CURVE_LOOKBACK = 20   # Days for slope calculation
EQUITY_CURVE_BOOST = 0.25    # +25% position size if rising
DRAWDOWN_RISK_REDUCTION = 0.50  # Reduce risk by 50% if in drawdown

# Corporate action filter
CORPORATE_ACTION_BUFFER_SESSIONS = 2
DIVIDEND_YIELD_THRESHOLD = 0.02  # 2% yield

# =============================================================================
# MONITORING & RELIABILITY
# =============================================================================
# Kill-switch
KILL_SWITCH_ERROR_COUNT = 3
KILL_SWITCH_WINDOW_MINUTES = 10

# Logging
LOG_RETENTION_DAYS = 90
LOG_DIR = "logs"
TRADE_LOG_FILE = "trade_log.xlsx"

# =============================================================================
# TRADING UNIVERSE
# =============================================================================
# Top 20 US stocks by liquidity - to be rotated monthly
# This is a starting universe; will be dynamically updated
TRADING_UNIVERSE = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft
    "GOOGL",  # Alphabet
    "AMZN",   # Amazon
    "NVDA",   # NVIDIA
    "META",   # Meta Platforms
    "TSLA",   # Tesla
    "BRK.B",  # Berkshire Hathaway
    "JPM",    # JPMorgan Chase
    "V",      # Visa
    "UNH",    # UnitedHealth
    "XOM",    # Exxon Mobil
    "JNJ",    # Johnson & Johnson
    "WMT",    # Walmart
    "MA",     # Mastercard
    "PG",     # Procter & Gamble
    "HD",     # Home Depot
    "CVX",    # Chevron
    "MRK",    # Merck
    "ABBV",   # AbbVie
]

# Sector mapping for exposure cap
SECTOR_MAP = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "GOOGL": "Technology",
    "AMZN": "Consumer Discretionary",
    "NVDA": "Technology",
    "META": "Technology",
    "TSLA": "Consumer Discretionary",
    "BRK.B": "Financials",
    "JPM": "Financials",
    "V": "Financials",
    "UNH": "Healthcare",
    "XOM": "Energy",
    "JNJ": "Healthcare",
    "WMT": "Consumer Staples",
    "MA": "Financials",
    "PG": "Consumer Staples",
    "HD": "Consumer Discretionary",
    "CVX": "Energy",
    "MRK": "Healthcare",
    "ABBV": "Healthcare",
}

# =============================================================================
# US MARKET HOLIDAYS 2024-2025
# =============================================================================
US_MARKET_HOLIDAYS = [
    # 2024
    "2024-01-01",  # New Year's Day
    "2024-01-15",  # MLK Day
    "2024-02-19",  # Presidents Day
    "2024-03-29",  # Good Friday
    "2024-05-27",  # Memorial Day
    "2024-06-19",  # Juneteenth
    "2024-07-04",  # Independence Day
    "2024-09-02",  # Labor Day
    "2024-11-28",  # Thanksgiving
    "2024-12-25",  # Christmas
    # 2025
    "2025-01-01",  # New Year's Day
    "2025-01-20",  # MLK Day
    "2025-02-17",  # Presidents Day
    "2025-04-18",  # Good Friday
    "2025-05-26",  # Memorial Day
    "2025-06-19",  # Juneteenth
    "2025-07-04",  # Independence Day
    "2025-09-01",  # Labor Day
    "2025-11-27",  # Thanksgiving
    "2025-12-25",  # Christmas
]