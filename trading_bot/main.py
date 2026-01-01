#!/usr/bin/env python3

# command to activate this: cd trading_bot
# then run: python3 main.py

"""
5-Minute EMA Crossover Trading Bot
==================================
Main entry point for running the trading bot.

Usage:
    python main.py              # Run in live mode
    python main.py --test       # Run single loop for testing
    python main.py --status     # Check current status
"""

import sys
import os
import signal
import time
import argparse
import logging
from datetime import datetime
import schedule
import pytz

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from trading_engine import TradingEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(config.LOG_DIR, f"bot_{datetime.now().strftime('%Y%m%d')}.log")
        )
    ]
)

logger = logging.getLogger(__name__)

# Global engine instance for signal handling
engine: TradingEngine = None


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    if engine:
        engine.graceful_shutdown()
    sys.exit(0)


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def run_trading_loop():
    """Run a single iteration of the trading loop."""
    global engine
    try:
        engine.run_loop()
    except Exception as e:
        logger.error(f"Error in trading loop: {e}", exc_info=True)


def run_eod_report():
    """Run end of day report."""
    global engine
    try:
        engine.end_of_day_report()
    except Exception as e:
        logger.error(f"Error generating EOD report: {e}", exc_info=True)


def check_status():
    """Check and display current bot status."""
    global engine
    engine = TradingEngine()
    
    print("\n" + "=" * 60)
    print("5-MINUTE EMA CROSSOVER BOT - STATUS")
    print("=" * 60)
    
    # Account info
    account = engine.order_manager.get_account()
    if account:
        print(f"\n📊 ACCOUNT:")
        print(f"   Equity:       ${account['equity']:,.2f}")
        print(f"   Cash:         ${account['cash']:,.2f}")
        print(f"   Buying Power: ${account['buying_power']:,.2f}")
    else:
        print("\n❌ Could not retrieve account info")
    
    # Positions
    positions = engine.order_manager.get_positions()
    print(f"\n📈 OPEN POSITIONS: {len(positions)}")
    for pos in positions:
        pnl_color = "🟢" if pos['unrealized_pl'] >= 0 else "🔴"
        print(f"   {pos['symbol']:6} | {pos['side']:5} | Qty: {pos['qty']:6.0f} | "
              f"Entry: ${pos['avg_entry_price']:8.2f} | "
              f"P&L: {pnl_color} ${pos['unrealized_pl']:8.2f}")
    
    # State
    state = engine.state_manager.get_full_state()
    print(f"\n⚙️  BOT STATE:")
    print(f"   Kill Switch:     {'🔴 ACTIVE' if state.get('kill_switch_active') else '🟢 Normal'}")
    print(f"   Circuit Breaker: {'🟡 Active' if state.get('circuit_breaker_active') else '🟢 Normal'}")
    print(f"   Paused:          {'🟡 Yes' if state.get('paused_until_next_session') else '🟢 No'}")
    print(f"   Consecutive Losses: {state.get('consecutive_losses', 0)}")
    print(f"   Daily P&L:       ${state.get('daily_pnl', 0):,.2f}")
    
    # Universe
    universe = state.get('universe', [])
    print(f"\n🌐 TRADING UNIVERSE: {len(universe)} symbols")
    print(f"   {', '.join(universe[:10])}...")
    
    # Market status
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    print(f"\n🕐 MARKET STATUS:")
    print(f"   Current Time (Dublin): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Market Open:  {engine.is_market_open()}")
    print(f"   Entry Window: {engine.is_entry_allowed_time()}")
    
    print("\n" + "=" * 60)


def run_test():
    """Run a single test iteration."""
    global engine
    engine = TradingEngine()
    
    logger.info("=" * 60)
    logger.info("RUNNING TEST ITERATION")
    logger.info("=" * 60)
    
    # Initialize session
    if not engine.initialize_session():
        logger.error("Failed to initialize session")
        return
    
    # Run one loop
    engine.run_loop()
    
    logger.info("Test iteration complete")


def main():
    """Main entry point."""
    global engine
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='5-Minute EMA Crossover Trading Bot')
    parser.add_argument('--test', action='store_true', help='Run single test iteration')
    parser.add_argument('--status', action='store_true', help='Check current status')
    args = parser.parse_args()
    
    # Ensure log directory exists
    os.makedirs(config.LOG_DIR, exist_ok=True)
    
    # Handle different modes
    if args.status:
        check_status()
        return
    
    if args.test:
        run_test()
        return
    
    # Production mode
    logger.info("=" * 60)
    logger.info("5-MINUTE EMA CROSSOVER BOT - STARTING")
    logger.info("=" * 60)
    logger.info(f"Paper Trading: {config.ALPACA_BASE_URL}")
    logger.info(f"Timezone: {config.TIMEZONE}")
    logger.info(f"Market Hours: {config.MARKET_OPEN_DUBLIN} - {config.MARKET_CLOSE_DUBLIN}")
    logger.info(f"Entry Window: {config.ENTRY_START_DUBLIN} - {config.ENTRY_END_DUBLIN}")
    logger.info("=" * 60)
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Initialize engine
    engine = TradingEngine()
    
    # Initialize session
    if not engine.initialize_session():
        logger.error("Failed to initialize session - check API credentials")
        return
    
    # Schedule jobs
    # Main trading loop every 5 minutes
    schedule.every(5).minutes.do(run_trading_loop)
    
    # End of day report at 21:05 Dublin time
    schedule.every().day.at("21:05").do(run_eod_report)
    
    logger.info("Scheduler started - running every 5 minutes during market hours")
    logger.info("Press Ctrl+C to stop")
    
    # Run initial loop
    run_trading_loop()
    
    # Main loop
    while True:
        try:
            schedule.run_pending()
            time.sleep(10)  # Check every 10 seconds
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(60)  # Wait before retrying
    
    # Graceful shutdown
    engine.graceful_shutdown()
    logger.info("Bot stopped")


if __name__ == "__main__":
    main()
