from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

import httpx

SEOUL_TZ = datetime.now().astimezone().tzinfo or UTC


@dataclass(slots=True)
class ConnectorContext:
    timeout_sec: float
    default_headers: dict[str, str]
    max_retries: int = 2
    transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None


class ConnectorError(RuntimeError):
    """Base error for connector failures."""


class ConnectorUnavailableError(ConnectorError):
    """Raised when an official connector cannot return a trusted payload."""


class OfficialConnector(ABC):
    source_name: str
    source_url: str

    def __init__(self, context: ConnectorContext, service_key: str | None = None) -> None:
        self.context = context
        self.service_key = service_key

    def make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.context.timeout_sec,
            headers=self.context.default_headers,
            transport=self.context.transport,
            follow_redirects=True,
        )

    def require_service_key(self) -> str:
        if not self.service_key:
            raise ConnectorUnavailableError(
                f"{self.source_name} is unavailable because service_key is not configured."
            )
        return self.service_key

    async def get_payload(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(1, self.context.max_retries + 1):
            try:
                async with self.make_client() as client:
                    response = await client.get(url, params=params)
                response.raise_for_status()
                return decode_payload(response)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == self.context.max_retries:
                    break

        raise ConnectorUnavailableError(
            f"{self.source_name} request failed for {url}: {last_error}"
        ) from last_error


def decode_payload(response: httpx.Response) -> dict[str, Any]:
    text = response.text.strip()
    content_type = response.headers.get("content-type", "").lower()

    if "json" in content_type or text.startswith("{") or text.startswith("["):
        payload = response.json()
        return payload if isinstance(payload, dict) else {"data": payload}

    if text.startswith("<"):
        return xml_to_dict(ElementTree.fromstring(text))

    raise ValueError("Unsupported payload type")


def xml_to_dict(element: ElementTree.Element) -> dict[str, Any]:
    children = list(element)
    if not children:
        return {element.tag: (element.text or "").strip()}

    grouped: dict[str, list[Any]] = {}
    for child in children:
        child_payload = xml_to_dict(child)[child.tag]
        grouped.setdefault(child.tag, []).append(child_payload)

    normalized: dict[str, Any] = {}
    for key, values in grouped.items():
        normalized[key] = values[0] if len(values) == 1 else values
    return {element.tag: normalized}


def extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data_items = payload.get("data")
    if isinstance(data_items, list):
        return [item for item in data_items if isinstance(item, dict)]
    if isinstance(data_items, dict):
        return [data_items]

    current: Any = payload
    for key in ("response", "body", "items", "item"):
        if isinstance(current, dict) and key in current:
            current = current[key]

    if current is None:
        return []
    if isinstance(current, list):
        return [item for item in current if isinstance(item, dict)]
    if isinstance(current, dict):
        return [current]
    return []


def parse_datetime(*values: str | None, fmt: str) -> datetime | None:
    parts = [value.strip() for value in values if value and value.strip()]
    if not parts:
        return None
    parsed = datetime.strptime("".join(parts), fmt)
    return parsed.replace(tzinfo=SEOUL_TZ)


def parse_datetime_multi(raw: str | None, *formats: str) -> datetime | None:
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=SEOUL_TZ)
        except ValueError:
            continue
    return None


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
