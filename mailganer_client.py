"""Minimal HTTP client for Mailganer REST API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from config import api_key, base_url


class MailganerAPIError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"Mailganer API error {status}: {body}")
        self.status = status
        self.body = body


class MailganerClient:
    def __init__(self, key: str | None = None, api_base: str | None = None):
        self.key = key or api_key()
        self.api_base = (api_base or base_url()).rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        use_v2_auth: bool = True,
    ) -> Any:
        if not self.key:
            raise MailganerAPIError(401, "MAILGANER_API_KEY is not configured")

        url = f"{self.api_base}{path}"
        headers = {"Accept": "application/json"}
        data = None

        if use_v2_auth:
            headers["Authorization"] = f"CodeRequest {self.key}"
            if json_body is not None:
                headers["Content-Type"] = "application/json"
                data = json.dumps(json_body).encode("utf-8")
        else:
            body = dict(json_body or {})
            body["api_key"] = self.key
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise MailganerAPIError(exc.code, body) from exc

    def get(self, path: str, *, use_v2_auth: bool = True) -> Any:
        return self._request("GET", path, use_v2_auth=use_v2_auth)

    def post(self, path: str, body: dict[str, Any] | None = None, *, use_v2_auth: bool = True) -> Any:
        return self._request("POST", path, json_body=body, use_v2_auth=use_v2_auth)
