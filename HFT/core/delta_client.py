"""C:\\Users\\SIGMA\\Documents\\Trading-Strategies\\HFT\\core\\delta_client.py
High-performance asynchronous client for Delta Exchange India.
Supports REST requests, batch order operations, time synchronization, and WebSocket streaming.
"""

import asyncio
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional
from pathlib import Path
import aiohttp
import email.utils

def _load_env_credentials():
    api_key = os.getenv("DELTA_API_KEY")
    api_secret = os.getenv("DELTA_API_SECRET")
    if api_key and api_secret:
        return api_key, api_secret
    
    # Try local .env or parent .env
    candidates = [
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / "CG-Terminal" / ".env",
    ]
    for cp in candidates:
        if cp.exists():
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DELTA_API_KEY="):
                            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("DELTA_API_SECRET="):
                            api_secret = line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    # Fallback to defaults
    if not api_key:
        api_key = "RrPSJVABou8UAT4BIl5ExCctYWV6dp"
    if not api_secret:
        api_secret = "1a0HWlsQfoeyv7J0rPx5mXWP0rEoL85RCWxUQmsI06aMS65cuQOhcUwjAiks"
    return api_key, api_secret

_DEF_KEY, _DEF_SEC = _load_env_credentials()
API_KEY_DEFAULT = _DEF_KEY
API_SECRET_DEFAULT = _DEF_SEC
BASE_URL_DEFAULT = "https://api.india.delta.exchange"
WS_URL_DEFAULT = "wss://socket.india.delta.exchange"


class DeltaClient:
    def __init__(
        self,
        api_key: str = API_KEY_DEFAULT,
        api_secret: str = API_SECRET_DEFAULT,
        base_url: str = BASE_URL_DEFAULT,
        ws_url: str = WS_URL_DEFAULT,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.ws_url = ws_url
        self._server_time_offset: float = 0.0
        self._session: Optional[aiohttp.ClientSession] = None
        self._product_ids: Dict[str, int] = {}

    async def get_product_id(self, symbol: str) -> Optional[int]:
        if symbol in self._product_ids:
            return self._product_ids[symbol]
        products = await self.get_products()
        for p in products:
            sym = p.get("symbol")
            pid = p.get("id")
            if sym and pid:
                self._product_ids[sym] = pid
        return self._product_ids.get(symbol)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=8.0, connect=3.0)
            connector = aiohttp.TCPConnector(limit=50, keepalive_timeout=60.0)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def sync_server_time(self) -> float:
        """Sync local system clock with Delta Exchange server timestamp."""
        session = await self._get_session()
        try:
            url = f"{self.base_url}/v2/products"
            async with session.get(url, headers={"User-Agent": "Antigravity-HFT"}) as resp:
                date_hdr = resp.headers.get("Date")
                if date_hdr:
                    server_ts = email.utils.parsedate_to_datetime(date_hdr).timestamp()
                    self._server_time_offset = server_ts - time.time()
                    return self._server_time_offset
        except Exception as e:
            pass
        return self._server_time_offset

    def _sign(self, method: str, timestamp: str, path: str, query: str = "", body: str = "") -> str:
        payload = f"{method}{timestamp}{path}{query}{body}"
        return hmac.new(
            self.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    async def request(
        self,
        method: str,
        path: str,
        query: str = "",
        body: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Dict[str, Any]:
        session = await self._get_session()
        body_str = json.dumps(body) if body is not None else ""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Antigravity-HFT/1.0",
        }

        for attempt in range(2):
            if auth:
                if self._server_time_offset == 0.0:
                    await self.sync_server_time()
                ts = str(int(time.time() + self._server_time_offset))
                sig = self._sign(method, ts, path, query, body_str)
                headers.update({
                    "api-key": self.api_key,
                    "signature": sig,
                    "timestamp": ts,
                })

            url = f"{self.base_url}{path}{query}"
            async with session.request(method, url, data=body_str if body_str else None, headers=headers) as resp:
                data = await resp.json()
                if not resp.ok:
                    err_code = data.get("error", {}).get("code")
                    if err_code == "expired_signature" and attempt == 0:
                        ctx = data.get("error", {}).get("context", {})
                        server_time = ctx.get("server_time")
                        if server_time:
                            self._server_time_offset = float(server_time) - time.time()
                            continue
                    raise ValueError(f"Delta API error HTTP {resp.status}: {data}")
                return data

    # ----------------- Market Data APIs -----------------

    async def get_products(self) -> List[Dict[str, Any]]:
        res = await self.request("GET", "/v2/products", auth=False)
        return res.get("result", [])

    async def get_tickers(self) -> List[Dict[str, Any]]:
        res = await self.request("GET", "/v2/tickers", auth=False)
        return res.get("result", [])

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        res = await self.request("GET", f"/v2/tickers/{symbol}", auth=False)
        return res.get("result", {})

    async def get_l2_orderbook(self, symbol: str, depth: int = 20) -> Dict[str, Any]:
        query = f"?depth={depth}"
        res = await self.request("GET", f"/v2/l2orderbook/{symbol}", query=query, auth=False)
        return res.get("result", {})

    # ----------------- Order Execution APIs -----------------

    async def get_positions(self) -> List[Dict[str, Any]]:
        res = await self.request("GET", "/v2/positions/margined", auth=True)
        return res.get("result", [])

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        query = f"?state=open"
        if symbol:
            query += f"&product_symbol={symbol}"
        res = await self.request("GET", "/v2/orders", query=query, auth=True)
        return res.get("result", [])

    async def place_order(
        self,
        symbol: str,
        size: int,
        side: str,
        limit_price: float,
        post_only: bool = True,
        time_in_force: str = "gtc",
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "product_symbol": symbol,
            "size": size,
            "side": side.lower(),
            "order_type": "limit_order",
            "limit_price": str(limit_price),
            "post_only": post_only,
            "time_in_force": time_in_force,
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id
        res = await self.request("POST", "/v2/orders", body=payload, auth=True)
        return res.get("result", {})

    async def place_batch_orders(self, symbol: str, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = {
            "product_symbol": symbol,
            "orders": orders,
        }
        res = await self.request("POST", "/v2/orders/batch", body=payload, auth=True)
        return res.get("result", [])

    async def cancel_order(
        self,
        order_id: int,
        product_id: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"id": order_id}
        if product_id is not None:
            payload["product_id"] = product_id
        elif symbol is not None:
            pid = await self.get_product_id(symbol)
            if pid is not None:
                payload["product_id"] = pid
        res = await self.request("DELETE", "/v2/orders", body=payload, auth=True)
        return res.get("result", {})

    async def cancel_batch_orders(self, symbol: str, order_ids: List[int]) -> List[Dict[str, Any]]:
        payload = {
            "product_symbol": symbol,
            "orders": [{"id": oid} for oid in order_ids],
        }
        res = await self.request("DELETE", "/v2/orders/batch", body=payload, auth=True)
        return res.get("result", [])

    async def cancel_all(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if symbol:
            payload["product_symbol"] = symbol
        res = await self.request("DELETE", "/v2/orders/all", body=payload, auth=True)
        return res.get("result", {})

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            await asyncio.sleep(0.05)
