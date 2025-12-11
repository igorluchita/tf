import datetime as dt
from typing import List, Optional

import requests
from django.utils import timezone

from . import TokenExpiredError


class TelegramClient:
    api_url = "https://api.telegram.org"

    def __init__(self, bot_token: str, chat_id: Optional[str] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str, chat_id: Optional[str] = None):
        chat = chat_id or self.chat_id
        if not chat:
            raise ValueError("Telegram chat id is required")
        endpoint = f"{self.api_url}/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": chat, "text": text}
        response = requests.post(endpoint, json=payload, timeout=10)
        if response.status_code in (401, 403):
            raise TokenExpiredError("Telegram token expired or invalid")
        response.raise_for_status()
        return response.json()

    @staticmethod
    def parse_webhook_payload(payload: dict) -> List[dict]:
        events: List[dict] = []
        message = payload.get("message")
        if not message:
            return events
        chat = message.get("chat", {})
        from_user = message.get("from", {})
        events.append(
            {
                "external_customer_id": chat.get("id"),
                "customer_name": from_user.get("username") or from_user.get("first_name", ""),
                "content": message.get("text") or "",
                "timestamp": dt.datetime.fromtimestamp(
                    message.get("date", timezone.now().timestamp()), tz=dt.timezone.utc
                ),
                "external_message_id": message.get("message_id"),
                "is_incoming": True,
            }
        )
        return events
