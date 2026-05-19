"""Thin wrapper around the Modulr Payments API.

The agency is the Modulr customer; Onvya is a Technical Service Provider
calling the API on the agency's behalf with scoped credentials. We never
custody funds — every call references the agency's own Modulr account.

Two implementations:
  - ``LiveModulrClient`` talks to https://api-sandbox.modulrfinance.com /
    api-live.modulrfinance.com using HMAC-signed requests.
  - ``StubModulrClient`` returns deterministic fake responses for dev and
    test environments. Toggled by ``MODULR_USE_STUB`` setting.

Reference: https://modulr.readme.io/reference
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

import requests
from django.conf import settings


@dataclass(frozen=True)
class PaymentInstruction:
    """Single Faster Payment instruction inside a batch."""

    reference: str           # 18 char max, shown on driver's statement
    amount: Decimal
    destination_sort_code: str
    destination_account_number: str
    destination_account_name: str
    external_reference: str  # our PayRunItem idempotency key


@dataclass(frozen=True)
class BatchSubmissionResult:
    provider_batch_id: str
    accepted_count: int
    rejected_count: int
    raw: dict


@dataclass(frozen=True)
class AccountBalance:
    account_id: str
    available: Decimal
    currency: str


class ModulrError(RuntimeError):
    """Raised for any non-2xx response or auth failure."""


# --------------------------------------------------------------------------- #
# Live client                                                                  #
# --------------------------------------------------------------------------- #


class LiveModulrClient:
    """Production / sandbox client.

    Auth uses Modulr's HMAC signature scheme: every request carries
    ``Date``, ``x-mod-nonce`` and an ``Authorization: Signature ...``
    header signed with the partner's HMAC secret.
    """

    def __init__(self, api_key: str, hmac_secret: str, base_url: str, timeout: int = 30):
        self.api_key = api_key
        self.hmac_secret = hmac_secret.encode("utf-8")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ----- auth helpers ---------------------------------------------------- #

    def _signature_headers(self) -> dict:
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        nonce = uuid.uuid4().hex
        signing_string = f"date: {date}\nx-mod-nonce: {nonce}"
        digest = hmac.new(self.hmac_secret, signing_string.encode("utf-8"), hashlib.sha1).digest()
        signature = base64.b64encode(digest).decode("ascii")
        auth = (
            f'Signature keyId="{self.api_key}",algorithm="hmac-sha1",'
            f'headers="date x-mod-nonce",signature="{signature}"'
        )
        return {
            "Date": date,
            "x-mod-nonce": nonce,
            "Authorization": auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, *, json: dict | None = None,
                 idempotency_key: str | None = None) -> dict:
        headers = self._signature_headers()
        if idempotency_key:
            headers["x-mod-idempotency-key"] = idempotency_key
        url = f"{self.base_url}{path}"
        resp = requests.request(
            method, url, headers=headers, json=json, timeout=self.timeout,
        )
        if resp.status_code >= 300:
            raise ModulrError(f"Modulr {method} {path} -> {resp.status_code}: {resp.text}")
        return resp.json() if resp.content else {}

    # ----- public surface -------------------------------------------------- #

    def get_account_balance(self, provider_account_id: str) -> AccountBalance:
        data = self._request("GET", f"/accounts/{provider_account_id}")
        return AccountBalance(
            account_id=provider_account_id,
            available=Decimal(str(data.get("balance", "0"))),
            currency=data.get("currency", "GBP"),
        )

    def submit_batch(
        self,
        *,
        provider_account_id: str,
        instructions: Iterable[PaymentInstruction],
        batch_idempotency_key: str,
    ) -> BatchSubmissionResult:
        payload = {
            "sourceAccountId": provider_account_id,
            "payments": [
                {
                    "currency": "GBP",
                    "amount": str(i.amount),
                    "reference": i.reference,
                    "externalReference": i.external_reference,
                    "destination": {
                        "type": "BENEFICIARY",
                        "sortCode": i.destination_sort_code,
                        "accountNumber": i.destination_account_number,
                        "name": i.destination_account_name,
                    },
                }
                for i in instructions
            ],
        }
        data = self._request(
            "POST", "/payments/batch", json=payload,
            idempotency_key=batch_idempotency_key,
        )
        return BatchSubmissionResult(
            provider_batch_id=str(data.get("id", "")),
            accepted_count=int(data.get("acceptedCount", 0)),
            rejected_count=int(data.get("rejectedCount", 0)),
            raw=data,
        )

    def confirmation_of_payee(self, *, sort_code: str, account_number: str,
                              account_name: str) -> str:
        """Returns one of: ``MATCH``, ``CLOSE_MATCH``, ``NO_MATCH``, ``UNAVAILABLE``."""
        data = self._request(
            "POST", "/account-name-check",
            json={
                "sortCode": sort_code,
                "accountNumber": account_number,
                "name": account_name,
            },
        )
        return str(data.get("result", "UNAVAILABLE"))


# --------------------------------------------------------------------------- #
# Stub client                                                                  #
# --------------------------------------------------------------------------- #


class StubModulrClient:
    """Deterministic fake used in dev and tests so the rest of the stack
    can run without sandbox credentials."""

    def __init__(self):
        self._balances: dict[str, Decimal] = {}

    def get_account_balance(self, provider_account_id: str) -> AccountBalance:
        return AccountBalance(
            account_id=provider_account_id,
            available=self._balances.get(provider_account_id, Decimal("1000000.00")),
            currency="GBP",
        )

    def submit_batch(self, *, provider_account_id, instructions, batch_idempotency_key):
        items = list(instructions)
        return BatchSubmissionResult(
            provider_batch_id=f"stub-batch-{batch_idempotency_key[:12]}",
            accepted_count=len(items),
            rejected_count=0,
            raw={"stub": True, "count": len(items)},
        )

    def confirmation_of_payee(self, *, sort_code, account_number, account_name):
        return "MATCH"


# --------------------------------------------------------------------------- #
# Factory                                                                      #
# --------------------------------------------------------------------------- #


def get_modulr_client():
    if getattr(settings, "MODULR_USE_STUB", True):
        return StubModulrClient()
    return LiveModulrClient(
        api_key=settings.MODULR_API_KEY,
        hmac_secret=settings.MODULR_HMAC_SECRET,
        base_url=settings.MODULR_BASE_URL,
    )


def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """Validate the HMAC-SHA512 signature Modulr puts on every webhook.

    Returns ``False`` for empty/malformed signatures rather than raising,
    so the view can return 401 cleanly.
    """
    if not signature_header:
        return False
    secret = getattr(settings, "MODULR_WEBHOOK_SECRET", "")
    if not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header.strip())
