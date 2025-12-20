"""
Email Notifier Module
=====================
Handles email notifications and daily reports.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, Optional
import logging

import config

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Sends email notifications and reports."""
    
    def __init__(self):
        self.enabled = bool(config.SMTP_USERNAME and config.SMTP_PASSWORD)
        if not self.enabled:
            logger.warning("Email notifications disabled - SMTP credentials not configured")
    
    def _send_email(self, subject: str, body: str, html: bool = False) -> bool:
        """Send an email."""
        if not self.enabled:
            logger.info(f"Email not sent (disabled): {subject}")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = config.SMTP_USERNAME
            msg['To'] = config.EMAIL_ADDRESS
            
            if html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
                server.starttls()
                server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                server.sendmail(config.SMTP_USERNAME, config.EMAIL_ADDRESS, msg.as_string())
            
            logger.info(f"Email sent: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def send_error_alert(self, error_type: str, details: str, symbol: Optional[str] = None):
        """Send an error alert notification."""
        subject = f"[TRADING BOT ALERT] {error_type}"
        
        body = f"""
Trading Bot Error Alert
=======================
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Type: {error_type}
Symbol: {symbol or 'N/A'}

Details:
{details}

Please check the bot status and logs.
        """
        
        self._send_email(subject, body)
    
    def send_kill_switch_alert(self, reason: str):
        """Send kill-switch triggered alert."""
        subject = "[TRADING BOT CRITICAL] Kill Switch Activated"
        
        body = f"""
KILL SWITCH ACTIVATED
===========================
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Reason: {reason}

All positions have been flattened.
Manual restart is required.

Please investigate immediately.
        """
        
        self._send_email(subject, body)
    
    def send_daily_report(
        self,
        date_str: str,
        stats: Dict[str, Any],
        risk_summary: Dict[str, Any],
        errors: int
    ):
        """Send end-of-day summary report."""
        subject = f"[TRADING BOT] Daily Report - {date_str}"
        
        win_rate = stats.get('win_rate', 0) * 100
        pnl = stats.get('daily_pnl', 0)
        pnl_pct = stats.get('daily_pnl_percent', 0) * 100
        
        pnl_color = '#28a745' if pnl >= 0 else '#dc3545'
        
        body = f"""
Daily Trading Report - {date_str}
================================

PERFORMANCE SUMMARY
-------------------
Daily P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)
Win Rate: {win_rate:.1f}%

TRADE STATISTICS
----------------
Total Trades: {stats.get('trades', 0)}
Winners: {stats.get('winners', 0)}
Losers: {stats.get('losers', 0)}
Avg Win: ${stats.get('avg_win', 0):,.2f}
Avg Loss: ${stats.get('avg_loss', 0):,.2f}
Profit Factor: {stats.get('profit_factor', 0):.2f}
Total Slippage: {stats.get('total_slippage', 0):.1f} bps

RISK METRICS
------------
Current Drawdown: {risk_summary.get('current_drawdown', 0)*100:.2f}%
Peak Equity: ${risk_summary.get('peak_equity', 0):,.2f}
Positions Open: {risk_summary.get('positions_at_risk', 0)}
Total Risk: {risk_summary.get('total_risk_percent', 0)*100:.2f}%

SYSTEM STATUS
-------------
Errors Today: {errors}
Circuit Breaker: {'ACTIVE' if risk_summary.get('circuit_breaker', False) else 'Normal'}
Paused: {'Yes' if risk_summary.get('paused', False) else 'No'}
Equity Curve Slope: {stats.get('equity_slope', 0):.4f}% per day

---
This is an automated report from the EMA Crossover Trading Bot.
        """
        
        self._send_email(subject, body)
    
    def send_trade_notification(
        self,
        action: str,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        pnl: Optional[float] = None
    ):
        """Send trade execution notification (optional, for important trades)."""
        subject = f"[TRADE] {action}: {side.upper()} {symbol}"
        
        body = f"""
Trade {action}
=============
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Symbol: {symbol}
Side: {side.upper()}
Quantity: {qty}
Price: ${price:.2f}
"""
        if pnl is not None:
            body += f"P&L: ${pnl:,.2f}\n"
        
        self._send_email(subject, body)
    
    def send_circuit_breaker_alert(self, reason: str, vix: Optional[float] = None):
        """Send circuit breaker activation alert."""
        subject = "[TRADING BOT] Circuit Breaker Activated"
        
        body = f"""
Circuit Breaker Activated
=========================
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Reason: {reason}
"""
        if vix:
            body += f"VIX Level: {vix:.1f}\n"
        
        body += """
New entries are paused. Exit management continues.
Bot will resume normal operation next session if conditions improve.
        """
        
        self._send_email(subject, body)
    
    def send_daily_loss_alert(self, daily_pnl: float, daily_pct: float):
        """Send daily loss limit alert."""
        subject = "[TRADING BOT] Daily Loss Limit Hit"
        
        body = f"""
Daily Loss Limit Reached
========================
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Daily P&L: ${daily_pnl:,.2f} ({daily_pct*100:.2f}%)
Limit: -{config.MAX_DAILY_LOSS*100:.1f}%

All positions have been closed.
No new entries until next trading session.
        """
        
        self._send_email(subject, body)
