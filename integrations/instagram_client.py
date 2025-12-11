import datetime as dt
import time
from typing import List, Optional

import requests
from django.utils import timezone

from . import TokenExpiredError


class InstagramClient:
    base_url = "https://graph.facebook.com/v19.0"

    def __init__(self, access_token: str, app_secret: str, ig_business_id: Optional[str] = None):
        self.access_token = access_token
        self.app_secret = app_secret
        self.ig_business_id = ig_business_id

    def _request(self, url: str, data: dict):
        response = requests.post(url, data=data, timeout=10)
        if response.status_code in (401, 403):
            raise TokenExpiredError("Instagram token expired or invalid")
        response.raise_for_status()
        return response.json()

    def create_media_container(self, caption: str, media_url: str):
        if not self.ig_business_id:
            raise ValueError("Instagram business id is required for publishing")
        endpoint = f"{self.base_url}/{self.ig_business_id}/media"
        payload = {
            "caption": caption,
            "image_url": media_url,
            "access_token": self.access_token,
        }
        return self._request(endpoint, payload)

    def publish_media(self, creation_id: str):
        endpoint = f"{self.base_url}/{self.ig_business_id}/media_publish"
        payload = {"creation_id": creation_id, "access_token": self.access_token}
        return self._request(endpoint, payload)

    @staticmethod
    def parse_webhook_payload(payload: dict) -> List[dict]:
        events: List[dict] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                customer_id = value.get("from", {}).get("id")
                message = value.get("text") or value.get("message") or ""
                timestamp = value.get("created_time", int(time.time()))
                events.append(
                    {
                        "external_customer_id": customer_id,
                        "customer_name": value.get("from", {}).get("username", ""),
                        "content": message,
                        "timestamp": dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc),
                        "external_message_id": value.get("id"),
                        "is_incoming": True,
                    }
                )
        return events
