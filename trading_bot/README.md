# 5-Minute EMA Crossover Trading Bot

An algorithmic trading bot implementing a 5-minute EMA crossover strategy with multiple filters, risk management, and comprehensive logging. Sends email update and creates Excel sheet with trades and data. Instructions are included.

## Features

- **EMA Crossover Strategy**: 9/21 EMA crossover on 5-minute bars with adaptive optimization
- **Multi-Timeframe Confirmation**: 15-minute trend confirmation
- **Momentum Filters**: RSI and MACD confirmation
- **Regime Detection**: ADX-based trend strength filtering
- **Market Breadth**: SPY-based market direction confirmation
- **Risk Management**: Position sizing, sector caps, daily loss limits
- **Trailing Stops**: ATR-based adaptive trailing stops
- **Paper Trading**: Configured for Alpaca paper trading by default
- **Excel Logging**: Comprehensive trade log in Excel format
- **Email Alerts**: Error notifications and daily reports

## Prerequisites

- Python 3.9 or higher
- Alpaca Trading Account (paper or live)

## Installation

### 1. Clone/Download the Bot

```bash
# Navigate to the trading bot directory
cd trading_bot
```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv venv

# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure API Credentials

**⚠️ IMPORTANT: You must update your Alpaca API credentials before running the bot!**

Edit `config.py` and replace the placeholder credentials:

```python
# Find these lines and replace with your actual credentials:
ALPACA_API_KEY = "PKXXXXXXXXXXXXXXXXXX"      # <-- Your API Key
ALPACA_SECRET_KEY = "XXXXXXXX..."            # <-- Your Secret Key
```

**To get your Alpaca API keys:**
1. Go to https://app.alpaca.markets/
2. Sign up or log in
3. Navigate to "Paper Trading" > "API Keys"
4. Generate new keys and copy them to config.py

**Alternative: Use Environment Variables (More Secure)**

```bash
export ALPACA_API_KEY="your_api_key_here"
export ALPACA_SECRET_KEY="your_secret_key_here"
```

Or create a `.env` file:

```
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
```

### 5. Configure Email (Optional)

To receive email alerts and daily reports, configure SMTP in `config.py` or via environment variables:

```python
SMTP_SERVER = "smtp.mail.me.com"  # For iCloud
SMTP_PORT = 587
SMTP_USERNAME = "your_email@icloud.com"
SMTP_PASSWORD = "your_app_specific_password"  # Generate in Apple ID settings
```

## Usage

### Check Status

```bash
python main.py --status
```

This shows:
- Account equity and buying power
- Open positions
- Bot state (kill switch, circuit breaker, etc.)
- Trading universe
- Market status

### Test Run

```bash
python main.py --test
```

Runs a single iteration of the trading loop for testing.

### Production Run

```bash
python main.py
```

Starts the bot in continuous mode:
- Runs every 5 minutes during market hours (14:30-21:00 Dublin time)
- Sends daily report at 21:05
- Handles graceful shutdown on Ctrl+C

### Running in Background (Linux/macOS)

```bash
nohup python main.py > output.log 2>&1 &
```

Or use `screen` or `tmux`:

```bash
screen -S tradingbot
python main.py
# Press Ctrl+A, then D to detach
# screen -r tradingbot to reattach
```

## Project Structure

```
trading_bot/
├── main.py              # Entry point
├── config.py            # All configuration parameters
├── trading_engine.py    # Main trading logic orchestrator
├── data_manager.py      # Market data fetching
├── order_manager.py     # Order execution and management
├── risk_manager.py      # Position sizing and risk controls
├── indicators.py        # Technical indicator calculations
├── trade_logger.py      # Excel spreadsheet logging
├── email_notifier.py    # Email notifications
├── state_manager.py     # State persistence and recovery
├── requirements.txt     # Python dependencies
├── README.md           # This file
└── logs/               # Log files directory (created automatically)
    ├── trade_log.xlsx  # Trade history spreadsheet
    ├── bot_state.json  # Persisted state
    └── bot_YYYYMMDD.log # Daily log files
```

## Configuration

All parameters are in `config.py`. Key settings:

### Trading Hours (Dublin Time)
- Market Open: 14:30
- Market Close: 21:00
- Entry Window: 14:35 - 20:30
- Flatten By: 20:58

### Risk Parameters
- Risk per trade: 0.75% (min 0.5%, max 1.0%)
- Max concurrent positions: 5
- Total risk cap: 3.5%
- Sector exposure cap: 40%
- Max daily loss: -3%

### Entry Filters
- ADX > 18 (trend strength)
- ATR% >= 0.15% (volatility)
- RSI > 55 (longs) / < 45 (shorts)
- Multi-timeframe confirmation (15-min)

### Trading Universe
Default top 20 US stocks by liquidity:
```
AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, BRK.B, JPM, V,
UNH, XOM, JNJ, WMT, MA, PG, HD, CVX, MRK, ABBV
```

Universe is automatically rebalanced monthly based on liquidity metrics.

## Trade Log (Excel)

The trade log (`logs/trade_log.xlsx`) contains four sheets:

1. **Trades**: All trade entries and exits with full details
2. **Daily Summary**: End-of-day performance statistics
3. **Shadow Mode**: Filtered signals for strategy analysis
4. **Alternative Exits**: Comparison of exit strategies

## Safety Features

### Kill Switch
Triggers after 3 consecutive API/data errors within 10 minutes:
- Flattens all positions
- Requires manual restart
- Sends email alert

### Circuit Breaker
Activates when:
- VIX > 30
- SPY ATR% > 2× 20-day median

Pauses new entries but manages exits.

### Daily Loss Limit
If daily P&L reaches -3%:
- Closes all positions
- Pauses entries until next session

### Consecutive Loss Filter
After 3 consecutive losses:
- Pauses new entries until next session

## Troubleshooting

### "Failed to initialize session"
- Check Alpaca API credentials
- Verify paper trading is enabled
- Check internet connection

### "No data returned for symbol"
- Market may be closed
- Symbol may be halted
- Check Alpaca data subscription

### Positions not being managed
- Check if kill switch was triggered
- Review logs for errors
- Verify positions exist in Alpaca dashboard

### Email not sending
- Check SMTP credentials
- For iCloud, use app-specific password
- Check spam folder

## Going Live

**⚠️ WARNING: Use at your own risk. Paper trade extensively first.**

To switch to live trading:

1. Get live API keys from Alpaca
2. Update `config.py`:
   ```python
   ALPACA_BASE_URL = "https://api.alpaca.markets"
   ```
3. Consider reducing position sizes initially
4. Monitor closely for the first few sessions

## Support

- Review logs in `logs/` directory
- Check Alpaca status: https://status.alpaca.markets/
- Alpaca documentation: https://alpaca.markets/docs/

## Disclaimer

This software is for educational purposes only. Trading involves substantial risk of loss. Past performance is not indicative of future results. Always paper trade and backtest extensively before risking real capital.
