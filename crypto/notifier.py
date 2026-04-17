"""
Notifier — prints trade events to the console and optionally sends Telegram messages.

To enable Telegram alerts:
  1. Create a bot via @BotFather on Telegram
  2. Get your chat ID by messaging @userinfobot
  3. Fill in telegram_token and telegram_chat_id in config.json
"""

import asyncio
from datetime import datetime


class Notifier:
    def __init__(self, telegram_token: str = "", telegram_chat_id: str = ""):
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self._tg_bot = None

        if telegram_token and telegram_chat_id:
            try:
                from telegram import Bot
                self._tg_bot = Bot(token=telegram_token)
                print("  Telegram notifications enabled.")
            except ImportError:
                print("  python-telegram-bot not installed. Skipping Telegram setup.")

    def _ts(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _send_telegram(self, message: str):
        if not self._tg_bot:
            return
        try:
            asyncio.run(
                self._tg_bot.send_message(chat_id=self.telegram_chat_id, text=message)
            )
        except Exception as e:
            print(f"  Telegram send failed: {e}")

    def trade(self, trade_info: dict, status_line: str):
        action = trade_info.get("action", "?")
        price = trade_info.get("price", 0)
        amount_usd = trade_info.get("amount_usd", 0)
        fee = trade_info.get("fee", 0)
        pnl = trade_info.get("pnl", None)

        pnl_str = ""
        if pnl is not None:
            sign = "+" if pnl >= 0 else ""
            pnl_str = f"  P&L this trade: {sign}${pnl:.4f}"

        msg = (
            f"\n[{self._ts()}] *** {action} ***\n"
            f"  Price : ${price:,.4f}\n"
            f"  Amount: ${amount_usd:.4f} USD\n"
            f"  Fee   : ${fee:.6f}"
            + (f"\n{pnl_str}" if pnl_str else "") +
            f"\n  {status_line}"
        )
        print(msg)

        tg_msg = f"🤖 {action} @ ${price:,.2f}\n${amount_usd:.4f} USD | fee ${fee:.4f}"
        if pnl is not None:
            sign = "+" if pnl >= 0 else ""
            tg_msg += f"\nP&L: {sign}${pnl:.4f}"
        self._send_telegram(tg_msg)

    def hold(self, price: float, indicator_info: str, status_line: str):
        print(f"[{self._ts()}] HOLD  price=${price:,.4f}  {indicator_info}  |  {status_line}")

    def info(self, message: str):
        print(f"[{self._ts()}] {message}")

    def error(self, message: str):
        print(f"[{self._ts()}] ERROR: {message}")
        self._send_telegram(f"⚠️ Bot error: {message}")
