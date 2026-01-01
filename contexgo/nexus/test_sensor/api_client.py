"""GraphQL client utilities for UI modules."""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional

import httpx
import websockets

from contexgo.infra.config import is_test_mode
from contexgo.infra.logging_utils import get_logger

logger = get_logger("nexus.test_sensor.api_client")

@dataclass(frozen=True)
class GraphQLResponse:
    data: Dict[str, Any]
    extensions: Dict[str, Any] | None = None


class GraphQLClientError(RuntimeError):
    """Raised when a GraphQL request fails."""


class GraphQLClient:
    """HTTP + WebSocket GraphQL client wrapper.

    The client is transport-focused and does not embed any sensor logic.
    """

    def __init__(
        self,
        http_url: str,
        ws_url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
    ) -> None:
        self.http_url = http_url
        self.ws_url = ws_url
        self._headers = headers or {}
        self._client = httpx.AsyncClient(timeout=timeout, headers=self._headers)
        if is_test_mode:
            logger.info(
                "GraphQL client 初始化: http_url=%s ws_url=%s", self.http_url, self.ws_url
            )

    async def close(self) -> None:
        await self._client.aclose()

    async def query(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> GraphQLResponse:
        return await self._send(query, variables)

    async def mutate(
        self, mutation: str, variables: Optional[Dict[str, Any]] = None
    ) -> GraphQLResponse:
        return await self._send(mutation, variables)

    async def subscribe(
        self,
        subscription: str,
        variables: Optional[Dict[str, Any]] = None,
        *,
        operation_name: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Yield payloads from a GraphQL WebSocket subscription."""

        async for payload in self._subscribe_ws(
            subscription, variables=variables, operation_name=operation_name
        ):
            yield payload

    async def _send(
        self, document: str, variables: Optional[Dict[str, Any]]
    ) -> GraphQLResponse:
        payload = {"query": document, "variables": variables or {}}
        response = await self._client.post(self.http_url, json=payload)
        response.raise_for_status()
        body = response.json()
        if "errors" in body:
            raise GraphQLClientError(str(body["errors"]))
        return GraphQLResponse(data=body.get("data", {}), extensions=body.get("extensions"))

    async def _subscribe_ws(
        self,
        subscription: str,
        *,
        variables: Optional[Dict[str, Any]],
        operation_name: Optional[str],
    ) -> AsyncIterator[Dict[str, Any]]:
        subscription_id = uuid.uuid4().hex
        payload = {
            "query": subscription,
            "variables": variables or {},
            "operationName": operation_name,
        }
        
        # 修复点：添加 subprotocols 参数，显式声明支持 graphql-transport-ws
        async with websockets.connect(
            self.ws_url, 
            additional_headers=self._headers,
            subprotocols=["graphql-transport-ws"]
        ) as websocket:
            await websocket.send(json.dumps({"type": "connection_init", "payload": {}}))
            await self._await_connection_ack(websocket)
            await websocket.send(
                json.dumps(
                    {"id": subscription_id, "type": "subscribe", "payload": payload}
                )
            )

            try:
                async for message in websocket:
                    data = json.loads(message)
                    message_type = data.get("type")
                    
                    # 兼容 graphql-transport-ws 的 ping/pong 机制
                    if message_type == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                        continue
                    
                    if message_type == "next":
                        yield data.get("payload", {})
                    elif message_type == "error":
                        raise GraphQLClientError(str(data.get("payload")))
                    elif message_type == "complete":
                        break
            finally:
                await self._safe_complete(websocket, subscription_id)

    async def _await_connection_ack(self, websocket: websockets.WebSocketClientProtocol) -> None:
        while True:
            raw = await websocket.recv()
            data = json.loads(raw)
            message_type = data.get("type")
            if message_type == "connection_ack":
                return
            if message_type == "connection_error":
                raise GraphQLClientError(str(data.get("payload")))

    async def _safe_complete(
        self, websocket: websockets.WebSocketClientProtocol, subscription_id: str
    ) -> None:
        if websocket.closed:
            return
        try:
            await websocket.send(
                json.dumps({"id": subscription_id, "type": "complete"})
            )
        except Exception:
            pass
        await asyncio.sleep(0)