"""Payment aggregator adapter (§3, §18).

§3: "Payment aggregator adapter behind an interface (**vendor TBD**)". §25 lists aggregator
selection as a launch blocker, so the interface is the deliverable and the vendor plugs in later.

§18 constrains every implementation: "**No card data touches Sincère servers** — aggregator-
hosted flows (also narrows PCI-DSS scope)." Every provider below returns a hosted checkout URL;
none accepts a card number, and none ever will.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sincere.shared.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    """A hosted checkout the client opens. Sincère never sees the payment instrument."""

    order_id: str
    checkout_url: str
    amount_paise: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    """A verified aggregator callback."""

    event_type: str
    order_id: str
    amount_paise: int
    aggregator_ref: str
    raw: dict[str, Any]


class PaymentProvider(Protocol):
    name: str

    async def create_checkout(
        self, *, order_id: str, amount_paise: int, description: str, user_id: str
    ) -> CheckoutSession: ...

    async def refund(self, *, aggregator_ref: str, amount_paise: int) -> str: ...

    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent | None:
        """Return the event, or ``None`` when the signature fails.

        §18: "Webhook signature verification (payments)". An unverified webhook is how a
        forged "payment succeeded" would grant free queue entry, so failure returns ``None``
        rather than raising — the route replies 400 without revealing why.
        """
        ...


class SandboxProvider:
    """Fully working provider with no external dependency.

    Not a mock: it creates real orders, produces real webhook payloads with real HMAC
    signatures, and exercises every code path the live provider will. The only thing it does
    not do is move money. §25 permits exactly this — Phase 1 is "internal alpha … incl.
    auction with **test payments**".
    """

    name = "sandbox"

    def __init__(self, secret: str) -> None:
        self._secret = (secret or "sandbox-secret").encode()

    async def create_checkout(
        self, *, order_id: str, amount_paise: int, description: str, user_id: str
    ) -> CheckoutSession:
        token = secrets.token_urlsafe(16)
        logger.info(
            "payment.sandbox_checkout",
            extra={"order_id": order_id, "amount_paise": amount_paise},
        )
        return CheckoutSession(
            order_id=order_id,
            # A dev-only page that posts a signed webhook back, so the whole flow is
            # walkable end to end without an aggregator account.
            checkout_url=f"/v1/dev/checkout/{order_id}?token={token}",
            amount_paise=amount_paise,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def refund(self, *, aggregator_ref: str, amount_paise: int) -> str:
        logger.info(
            "payment.sandbox_refund",
            extra={"aggregator_ref": aggregator_ref, "amount_paise": amount_paise},
        )
        return f"rfnd_{secrets.token_hex(8)}"

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent | None:
        expected = self.sign(payload)
        if not hmac.compare_digest(expected, signature or ""):
            logger.warning("payment.webhook_signature_invalid")
            return None
        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return WebhookEvent(
            event_type=body.get("event", "payment.succeeded"),
            order_id=body["order_id"],
            amount_paise=int(body["amount_paise"]),
            aggregator_ref=body.get("aggregator_ref", f"sbx_{body['order_id']}"),
            raw=body,
        )


class RazorpayProvider:
    """Razorpay hosted checkout — the India-market default the docs' *(assumed)* stack implies.

    Kept deliberately thin: order creation, refund, and signature verification. Everything
    else stays on Razorpay's side, which is what keeps PCI-DSS scope narrow (§18).
    """

    name = "razorpay"

    def __init__(self, key: str, secret: str, webhook_secret: str) -> None:
        self._key = key
        self._secret = secret
        self._webhook_secret = (webhook_secret or "").encode()

    async def create_checkout(
        self, *, order_id: str, amount_paise: int, description: str, user_id: str
    ) -> CheckoutSession:
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.razorpay.com/v1/orders",
                auth=(self._key, self._secret),
                json={
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": order_id,
                    "notes": {"description": description, "user_id": user_id},
                },
            )
            response.raise_for_status()
            order = response.json()

        return CheckoutSession(
            order_id=order_id,
            checkout_url=f"https://checkout.razorpay.com/v1/checkout.js?order_id={order['id']}",
            amount_paise=amount_paise,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def refund(self, *, aggregator_ref: str, amount_paise: int) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.razorpay.com/v1/payments/{aggregator_ref}/refund",
                auth=(self._key, self._secret),
                json={"amount": amount_paise},
            )
            response.raise_for_status()
            return str(response.json()["id"])

    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent | None:
        expected = hmac.new(self._webhook_secret, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            logger.warning("payment.webhook_signature_invalid")
            return None
        try:
            body = json.loads(payload)
            entity = body["payload"]["payment"]["entity"]
        except (json.JSONDecodeError, KeyError):
            return None
        return WebhookEvent(
            event_type=body.get("event", ""),
            order_id=entity.get("notes", {}).get("order_id") or entity.get("order_id", ""),
            amount_paise=int(entity["amount"]),
            aggregator_ref=entity["id"],
            raw=body,
        )


_provider: PaymentProvider | None = None


def get_provider() -> PaymentProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        if settings.payment_provider == "razorpay":
            _provider = RazorpayProvider(
                settings.payment_aggregator_key,
                settings.payment_aggregator_secret,
                settings.payment_webhook_secret,
            )
        else:
            _provider = SandboxProvider(settings.payment_webhook_secret)
        logger.info("payment.provider_selected", extra={"provider": _provider.name})
    return _provider


def set_provider(provider: PaymentProvider | None) -> None:
    """Test seam."""
    global _provider
    _provider = provider
