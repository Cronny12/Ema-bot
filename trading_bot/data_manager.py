"""
Data Manager Module
===================
Handles all data fetching from Alpaca API.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestBarRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus

import config

logger = logging.getLogger(__name__)


class DataManager:
    """Manages market data retrieval from Alpaca."""
    
    def __init__(self):
        self.data_client = StockHistoricalDataClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY
        )
        self.trading_client = TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=True
        )
        self._bar_cache: Dict[str, pd.DataFrame] = {}
        self._cache_timestamp: Optional[datetime] = None
    
    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: int = 100
    ) -> pd.DataFrame:
        """
        Fetch historical bars for a symbol.
        
        Args:
            symbol: Stock ticker
            timeframe: '1Min', '5Min', '15Min', '1Day'
            lookback_days: Number of days to look back
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            if timeframe == "1Min":
                tf = TimeFrame(1, TimeFrameUnit.Minute)
            elif timeframe == "5Min":
                tf = TimeFrame(5, TimeFrameUnit.Minute)
            elif timeframe == "15Min":
                tf = TimeFrame(15, TimeFrameUnit.Minute)
            elif timeframe == "1Day":
                tf = TimeFrame(1, TimeFrameUnit.Day)
            else:
                raise ValueError(f"Unsupported timeframe: {timeframe}")
            
            end = datetime.now()
            start = end - timedelta(days=lookback_days)
            
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end
            )
            
            bars = self.data_client.get_stock_bars(request)
            
            if symbol not in bars.data or not bars.data[symbol]:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()
            
            df = pd.DataFrame([{
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume,
                'vwap': bar.vwap if hasattr(bar, 'vwap') else None
            } for bar in bars.data[symbol]])
            
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_latest_bar(self, symbol: str) -> Optional[Dict]:
        """Get the most recent bar for a symbol."""
        try:
            request = StockLatestBarRequest(symbol_or_symbols=symbol)
            bar = self.data_client.get_stock_latest_bar(request)
            
            if symbol not in bar:
                return None
            
            b = bar[symbol]
            return {
                'timestamp': b.timestamp,
                'open': b.open,
                'high': b.high,
                'low': b.low,
                'close': b.close,
                'volume': b.volume
            }
        except Exception as e:
            logger.error(f"Error fetching latest bar for {symbol}: {e}")
            return None
    
    def get_multi_symbol_bars(
        self,
        symbols: List[str],
        timeframe: str,
        lookback_days: int = 100
    ) -> Dict[str, pd.DataFrame]:
        """Fetch bars for multiple symbols."""
        result = {}
        for symbol in symbols:
            df = self.get_bars(symbol, timeframe, lookback_days)
            if not df.empty:
                result[symbol] = df
        return result
    
    def check_data_freshness(self, bar_timestamp: datetime, max_age_minutes: int = 3) -> bool:
        """Check if bar data is fresh enough."""
        if bar_timestamp is None:
            return False
        now = datetime.now(bar_timestamp.tzinfo)
        age = (now - bar_timestamp).total_seconds() / 60
        return age <= max_age_minutes
    
    def get_vix(self) -> Optional[float]:
        """Get current VIX value (using proxy ETF if needed)."""
        try:
            # Use VIXY as proxy since Alpaca doesn't provide VIX directly
            bars = self.get_bars("VIXY", "1Day", lookback_days=5)
            if not bars.empty:
                return bars['close'].iloc[-1]
            return None
        except Exception as e:
            logger.error(f"Error fetching VIX proxy: {e}")
            return None
    
    def get_spy_data(self, timeframe: str = "5Min", lookback_days: int = 30) -> pd.DataFrame:
        """Get SPY data for market breadth filter."""
        return self.get_bars(config.SPY_SYMBOL, timeframe, lookback_days)
    
    def calculate_adv_dollars(self, symbol: str, lookback_days: int = 20) -> float:
        """Calculate average daily volume in dollars."""
        try:
            bars = self.get_bars(symbol, "1Day", lookback_days)
            if bars.empty:
                return 0
            
            dollar_volume = bars['close'] * bars['volume']
            return dollar_volume.mean()
        except Exception as e:
            logger.error(f"Error calculating ADV$ for {symbol}: {e}")
            return 0
    
    def get_spread_estimate(self, symbol: str) -> float:
        """
        Estimate bid-ask spread as basis points.
        Uses high-low range as proxy when quotes unavailable.
        """
        try:
            bars = self.get_bars(symbol, "1Min", lookback_days=1)
            if bars.empty:
                return float('inf')
            
            # Use intraday high-low range as spread proxy
            recent_bars = bars.tail(30)
            spread_proxy = ((recent_bars['high'] - recent_bars['low']) / recent_bars['close']).median()
            return spread_proxy * 10000  # Convert to basis points
        except Exception as e:
            logger.error(f"Error estimating spread for {symbol}: {e}")
            return float('inf')
    
    def filter_universe_by_liquidity(
        self,
        symbols: List[str],
        min_adv_dollars: float,
        max_spread_bps: float,
        min_price: float
    ) -> List[str]:
        """Filter symbols by liquidity criteria."""
        filtered = []
        
        for symbol in symbols:
            try:
                # Check price
                latest = self.get_latest_bar(symbol)
                if latest is None or latest['close'] < min_price:
                    continue
                
                # Check ADV$
                adv = self.calculate_adv_dollars(symbol)
                if adv < min_adv_dollars:
                    continue
                
                # Check spread
                spread = self.get_spread_estimate(symbol)
                if spread > max_spread_bps:
                    continue
                
                filtered.append(symbol)
                
            except Exception as e:
                logger.warning(f"Error filtering {symbol}: {e}")
                continue
        
        return filtered
    
    def get_tradable_assets(self) -> List[str]:
        """Get list of all tradable US equities."""
        try:
            request = GetAssetsRequest(
                asset_class=AssetClass.US_EQUITY,
                status=AssetStatus.ACTIVE
            )
            assets = self.trading_client.get_all_assets(request)
            return [a.symbol for a in assets if a.tradable and a.fractionable]
        except Exception as e:
            logger.error(f"Error fetching tradable assets: {e}")
            return []
    
    def build_universe(self, top_n: int = 20) -> List[str]:
        """
        Build trading universe based on liquidity criteria.
        Returns top N symbols by ADV$.
        """
        logger.info("Building trading universe...")
        
        # Start with configured universe
        candidates = config.TRADING_UNIVERSE.copy()
        
        # Calculate ADV$ for ranking
        adv_data = []
        for symbol in candidates:
            adv = self.calculate_adv_dollars(symbol)
            price_bar = self.get_latest_bar(symbol)
            price = price_bar['close'] if price_bar else 0
            spread = self.get_spread_estimate(symbol)
            
            if (adv >= config.UNIVERSE_MIN_ADV and 
                price >= config.UNIVERSE_MIN_PRICE and
                spread <= config.UNIVERSE_MAX_SPREAD_BPS):
                adv_data.append((symbol, adv))
        
        # Sort by ADV$ descending
        adv_data.sort(key=lambda x: x[1], reverse=True)
        
        # Return top N
        universe = [s[0] for s in adv_data[:top_n]]
        logger.info(f"Universe built with {len(universe)} symbols: {universe}")
        
        return universe
    
    def is_symbol_halted(self, symbol: str) -> bool:
        """Check if a symbol is halted."""
        try:
            asset = self.trading_client.get_asset(symbol)
            return not asset.tradable
        except Exception as e:
            logger.error(f"Error checking halt status for {symbol}: {e}")
            return True  # Assume halted if we can't check
    
    def get_previous_close(self, symbol: str) -> Optional[float]:
        """Get previous day's closing price."""
        try:
            bars = self.get_bars(symbol, "1Day", lookback_days=5)
            if len(bars) >= 2:
                return bars['close'].iloc[-2]
            return None
        except Exception as e:
            logger.error(f"Error getting previous close for {symbol}: {e}")
            return None
