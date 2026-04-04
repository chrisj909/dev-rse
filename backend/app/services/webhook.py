"""
RSE Webhook Service — Sprint 6, Task 17
app/services/webhook.py

Fires CRM-formatted lead payloads to a configured external endpoint when a
property's score meets or exceeds the configured threshold.

Usage:
    service = WebhookService(url="https://crm.example.com/webhook", threshold=25)

    # Single lead
    ok = service.send(lead)          # → True | False

    # Batch
    stats = service.send_batch(leads)  # → {"sent": N, "failed": N, "skipped": N}

Configuration (via environment / config.py):
    WEBHOOK_URL             — POST target (required; leave blank to disable)
    WEBHOOK_SCORE_THRESHOLD — minimum score to trigger (default 25)

Retry policy:
    3 attempts with exponential backoff (1 s, 2 s, 4 s) on network errors or
    5xx responses. A 4xx from the remote is treated as a permanent failure —
    no retry.

All HTTP I/O is done synchronously via httpx so the service can be used both
from async FastAPI handlers (run in a thread pool) and from CLI scripts.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from app.models.crm import CRMLeadExport

logger = logging.getLogger(__name__)

# Retry configuration
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0   # seconds; delay = _BACKOFF_BASE * 2^(attempt)


class WebhookService:
    """
    Sends CRM lead payloads to an external webhook URL.

    Parameters
    ----------
    url:
        The HTTP(S) endpoint to POST to.
    threshold:
        Minimum score a lead must have to be sent. Leads below this value
        are counted as *skipped* in batch operations.
    secret:
        Optional shared secret sent as the `X-RSE-Secret` header for
        lightweight authentication.
    timeout:
        Per-request timeout in seconds (default 10).
    """

    def __init__(
        self,
        url: str,
        threshold: int = 25,
        secret: str = "",
        timeout: float = 10.0,
    ) -> None:
        self.url = url
        self.threshold = threshold
        self.secret = secret
        self.timeout = timeout

    # ── Public API ────────────────────────────────────────────────────────────

    def send(self, lead: CRMLeadExport) -> bool:
        """
        POST a single CRM lead to the webhook URL.

        Returns True if the delivery succeeded, False otherwise.
        Retries up to _MAX_RETRIES times on transient errors or 5xx responses.
        4xx responses are treated as permanent failures (no retry).

        Does NOT filter by score — call `send_batch` if you want threshold
        filtering, or check `lead.score.value >= self.threshold` yourself.
        """
        if not self.url:
            logger.warning("WebhookService: no URL configured — skipping send.")
            return False

        payload = lead.model_dump(mode="json")
        headers = self._build_headers()

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = httpx.post(
                    self.url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    "WebhookService: attempt %d/%d — network error: %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES:
                    self._backoff(attempt)
                continue

            if response.is_success:
                logger.info(
                    "WebhookService: delivered lead %s (score=%d) — HTTP %d",
                    lead.property.parcel_id,
                    lead.score.value,
                    response.status_code,
                )
                return True

            # 4xx → permanent failure, don't retry
            if 400 <= response.status_code < 500:
                logger.error(
                    "WebhookService: permanent failure for lead %s — HTTP %d: %s",
                    lead.property.parcel_id,
                    response.status_code,
                    response.text[:200],
                )
                return False

            # 5xx → transient, retry
            logger.warning(
                "WebhookService: attempt %d/%d — HTTP %d for lead %s",
                attempt,
                _MAX_RETRIES,
                response.status_code,
                lead.property.parcel_id,
            )
            if attempt < _MAX_RETRIES:
                self._backoff(attempt)

        logger.error(
            "WebhookService: all %d attempts exhausted for lead %s.",
            _MAX_RETRIES,
            lead.property.parcel_id,
        )
        return False

    def send_batch(self, leads: list[CRMLeadExport]) -> dict[str, int]:
        """
        Send a list of CRM leads, filtering by score threshold.

        Returns a stats dict:
            {
                "sent":    N,  # successfully delivered
                "failed":  N,  # delivery attempted but failed after retries
                "skipped": N,  # below threshold — not attempted
            }

        Logs a summary at INFO level on completion.
        """
        sent = 0
        failed = 0
        skipped = 0

        for lead in leads:
            if lead.score.value < self.threshold:
                skipped += 1
                logger.debug(
                    "WebhookService: skipping lead %s (score=%d < threshold=%d)",
                    lead.property.parcel_id,
                    lead.score.value,
                    self.threshold,
                )
                continue

            ok = self.send(lead)
            if ok:
                sent += 1
            else:
                failed += 1

        stats = {"sent": sent, "failed": failed, "skipped": skipped}
        logger.info(
            "WebhookService batch complete — sent=%d failed=%d skipped=%d",
            sent,
            failed,
            skipped,
        )
        return stats

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_headers(self) -> dict[str, str]:
        """Return HTTP headers for the webhook request."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "RSE-WebhookService/1.0",
        }
        if self.secret:
            headers["X-RSE-Secret"] = self.secret
        return headers

    @staticmethod
    def _backoff(attempt: int) -> None:
        """Sleep for exponential backoff: 1s, 2s, 4s, ..."""
        delay = _BACKOFF_BASE * (2 ** (attempt - 1))
        logger.debug("WebhookService: backing off %.1fs before retry.", delay)
        time.sleep(delay)


def build_webhook_service(
    url: Optional[str] = None,
    threshold: Optional[int] = None,
    secret: Optional[str] = None,
) -> WebhookService:
    """
    Factory that builds a WebhookService from config, with optional overrides.

    Pulls defaults from `app.core.config.settings` so callers don't need to
    import settings directly — especially useful in CLI scripts.
    """
    from app.core.config import settings

    return WebhookService(
        url=url if url is not None else settings.webhook_url,
        threshold=threshold if threshold is not None else settings.webhook_score_threshold,
        secret=secret if secret is not None else settings.webhook_secret,
    )
