"""
Tests for WebhookService — Sprint 6, Task 17.
app/services/webhook.py

Strategy:
  - httpx.post is mocked via unittest.mock.patch so no real HTTP calls are made.
  - time.sleep is mocked to avoid actual delays during backoff tests.
  - WebhookService is instantiated directly with explicit URL/threshold values
    (no environment variables required).

Covers:
  WebhookService.send()
    - Returns True on 2xx response
    - Returns False when url is empty/not configured
    - Returns False on 4xx response (no retry)
    - Returns False when all retries exhausted (5xx)
    - Returns False when all retries exhausted (network error)
    - Returns True on success after one transient failure (retry works)
    - Returns True on success after two transient failures
    - Retries at most 3 times on 5xx
    - Retries at most 3 times on network error
    - Does NOT retry on 4xx
    - Sends correct Content-Type header
    - Sends X-RSE-Secret header when secret is set
    - Does NOT send X-RSE-Secret when secret is empty
    - Payload is JSON-serialisable CRMLeadExport
    - Posts to correct URL
    - Exponential backoff: delays are called with correct values
    - 201 Created treated as success
    - 204 No Content treated as success
    - 500 triggers retry
    - 503 triggers retry

  WebhookService.send_batch()
    - Returns {sent, failed, skipped} keys
    - Leads below threshold are skipped
    - Leads at threshold are sent
    - Leads above threshold are sent
    - skipped count correct when mix of above/below threshold
    - sent count reflects successful deliveries
    - failed count reflects failed deliveries
    - All skipped → sent=0, failed=0, skipped=N
    - All sent → sent=N, failed=0, skipped=0
    - All failed → sent=0, failed=N, skipped=0
    - Empty list → {sent:0, failed:0, skipped:0}
    - Mixed batch: some sent, some failed, some skipped

  build_webhook_service()
    - Returns a WebhookService instance
    - Picks up threshold override
    - Picks up url override
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest
import httpx

from app.models.crm import (
    CRMLeadExport,
    PropertyExport,
    ScoreExport,
    SignalsExport,
)
from app.services.webhook import WebhookService, build_webhook_service


# ── Factories ─────────────────────────────────────────────────────────────────

def make_lead(score: int = 35, rank: str = "A", parcel_id: str = "SC-0001") -> CRMLeadExport:
    """Build a minimal CRMLeadExport for testing."""
    return CRMLeadExport(
        property=PropertyExport(
            property_id=str(uuid.uuid4()),
            parcel_id=parcel_id,
            address="123 MAIN ST",
            city="HOOVER",
            state="AL",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        ),
        signals=SignalsExport(absentee_owner=True, long_term_owner=True),
        score=ScoreExport(value=score, rank=rank, version="v1"),
        tags=["absentee_owner", "long_term_owner"],
        exported_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
    )


def _ok_response(status_code: int = 200) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.is_success = True
    return r


def _error_response(status_code: int) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.is_success = False
    r.text = "error body"
    return r


# ── WebhookService.send ───────────────────────────────────────────────────────

class TestWebhookServiceSend:

    @patch("app.services.webhook.httpx.post")
    def test_returns_true_on_200(self, mock_post):
        mock_post.return_value = _ok_response(200)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is True

    @patch("app.services.webhook.httpx.post")
    def test_returns_true_on_201(self, mock_post):
        mock_post.return_value = _ok_response(201)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is True

    @patch("app.services.webhook.httpx.post")
    def test_returns_true_on_204(self, mock_post):
        mock_post.return_value = _ok_response(204)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is True

    def test_returns_false_when_url_empty(self):
        svc = WebhookService(url="", threshold=25)
        assert svc.send(make_lead()) is False

    @patch("app.services.webhook.httpx.post")
    def test_returns_false_on_400(self, mock_post):
        mock_post.return_value = _error_response(400)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is False

    @patch("app.services.webhook.httpx.post")
    def test_returns_false_on_401(self, mock_post):
        mock_post.return_value = _error_response(401)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is False

    @patch("app.services.webhook.httpx.post")
    def test_returns_false_on_404(self, mock_post):
        mock_post.return_value = _error_response(404)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is False

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_returns_false_when_all_retries_exhausted_5xx(self, mock_post, mock_sleep):
        mock_post.return_value = _error_response(500)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is False
        assert mock_post.call_count == 3

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_returns_false_when_all_retries_exhausted_503(self, mock_post, mock_sleep):
        mock_post.return_value = _error_response(503)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is False
        assert mock_post.call_count == 3

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_returns_false_on_network_error_all_retries(self, mock_post, mock_sleep):
        mock_post.side_effect = httpx.NetworkError("connection refused")
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is False
        assert mock_post.call_count == 3

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_returns_false_on_timeout_all_retries(self, mock_post, mock_sleep):
        mock_post.side_effect = httpx.TimeoutException("timed out")
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is False
        assert mock_post.call_count == 3

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_succeeds_after_one_5xx(self, mock_post, mock_sleep):
        mock_post.side_effect = [_error_response(500), _ok_response(200)]
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is True
        assert mock_post.call_count == 2

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_succeeds_after_two_5xx(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            _error_response(500),
            _error_response(503),
            _ok_response(200),
        ]
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is True
        assert mock_post.call_count == 3

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_does_not_retry_on_4xx(self, mock_post, mock_sleep):
        mock_post.return_value = _error_response(422)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        svc.send(make_lead())
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()

    @patch("app.services.webhook.httpx.post")
    def test_sends_to_correct_url(self, mock_post):
        mock_post.return_value = _ok_response()
        url = "https://crm.acme.com/webhook/rse"
        svc = WebhookService(url=url, threshold=25)
        svc.send(make_lead())
        assert mock_post.call_args[0][0] == url

    @patch("app.services.webhook.httpx.post")
    def test_sends_content_type_json(self, mock_post):
        mock_post.return_value = _ok_response()
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        svc.send(make_lead())
        headers = mock_post.call_args[1]["headers"]
        assert headers["Content-Type"] == "application/json"

    @patch("app.services.webhook.httpx.post")
    def test_sends_secret_header_when_set(self, mock_post):
        mock_post.return_value = _ok_response()
        svc = WebhookService(url="https://example.com/hook", threshold=25, secret="abc123")
        svc.send(make_lead())
        headers = mock_post.call_args[1]["headers"]
        assert headers["X-RSE-Secret"] == "abc123"

    @patch("app.services.webhook.httpx.post")
    def test_no_secret_header_when_empty(self, mock_post):
        mock_post.return_value = _ok_response()
        svc = WebhookService(url="https://example.com/hook", threshold=25, secret="")
        svc.send(make_lead())
        headers = mock_post.call_args[1]["headers"]
        assert "X-RSE-Secret" not in headers

    @patch("app.services.webhook.httpx.post")
    def test_payload_is_json_serialisable(self, mock_post):
        mock_post.return_value = _ok_response()
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        lead = make_lead(score=42)
        svc.send(lead)
        payload = mock_post.call_args[1]["json"]
        assert isinstance(payload, dict)
        assert "property" in payload
        assert "signals" in payload
        assert "score" in payload
        assert payload["score"]["value"] == 42

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_backoff_delays_on_5xx(self, mock_post, mock_sleep):
        """Backoff: 1s after attempt 1, 2s after attempt 2 (no sleep after final attempt)."""
        mock_post.return_value = _error_response(500)
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        svc.send(make_lead())
        # Should sleep twice (after attempt 1 and attempt 2, not after attempt 3)
        assert mock_sleep.call_count == 2
        sleep_args = [c[0][0] for c in mock_sleep.call_args_list]
        assert sleep_args[0] == 1.0  # 1 * 2^0
        assert sleep_args[1] == 2.0  # 1 * 2^1

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_network_error_then_success(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            httpx.NetworkError("refused"),
            _ok_response(200),
        ]
        svc = WebhookService(url="https://example.com/hook", threshold=25)
        assert svc.send(make_lead()) is True


# ── WebhookService.send_batch ─────────────────────────────────────────────────

class TestWebhookServiceSendBatch:

    def _service(self, threshold: int = 25) -> WebhookService:
        return WebhookService(url="https://example.com/hook", threshold=threshold)

    @patch("app.services.webhook.httpx.post")
    def test_returns_stats_dict_keys(self, mock_post):
        mock_post.return_value = _ok_response()
        svc = self._service()
        stats = svc.send_batch([make_lead(35)])
        assert set(stats.keys()) == {"sent", "failed", "skipped"}

    @patch("app.services.webhook.httpx.post")
    def test_leads_above_threshold_are_sent(self, mock_post):
        mock_post.return_value = _ok_response()
        svc = self._service(threshold=25)
        stats = svc.send_batch([make_lead(score=30)])
        assert stats["sent"] == 1
        assert stats["skipped"] == 0

    @patch("app.services.webhook.httpx.post")
    def test_leads_at_threshold_are_sent(self, mock_post):
        mock_post.return_value = _ok_response()
        svc = self._service(threshold=25)
        stats = svc.send_batch([make_lead(score=25)])
        assert stats["sent"] == 1
        assert stats["skipped"] == 0

    def test_leads_below_threshold_are_skipped(self):
        svc = self._service(threshold=25)
        stats = svc.send_batch([make_lead(score=24)])
        assert stats["skipped"] == 1
        assert stats["sent"] == 0
        assert stats["failed"] == 0

    def test_empty_batch_returns_zeros(self):
        svc = self._service()
        stats = svc.send_batch([])
        assert stats == {"sent": 0, "failed": 0, "skipped": 0}

    @patch("app.services.webhook.httpx.post")
    def test_all_sent_when_all_above_threshold(self, mock_post):
        mock_post.return_value = _ok_response()
        svc = self._service(threshold=10)
        leads = [make_lead(score=30) for _ in range(5)]
        stats = svc.send_batch(leads)
        assert stats["sent"] == 5
        assert stats["failed"] == 0
        assert stats["skipped"] == 0

    def test_all_skipped_when_all_below_threshold(self):
        svc = self._service(threshold=50)
        leads = [make_lead(score=20) for _ in range(4)]
        stats = svc.send_batch(leads)
        assert stats["skipped"] == 4
        assert stats["sent"] == 0
        assert stats["failed"] == 0

    @patch("app.services.webhook.time.sleep")
    @patch("app.services.webhook.httpx.post")
    def test_failed_count_reflects_failed_deliveries(self, mock_post, mock_sleep):
        mock_post.return_value = _error_response(500)
        svc = self._service(threshold=25)
        stats = svc.send_batch([make_lead(score=30)])
        assert stats["failed"] == 1
        assert stats["sent"] == 0

    @patch("app.services.webhook.httpx.post")
    def test_mixed_batch_stats(self, mock_post):
        """3 above threshold (2 sent, 1 failed), 2 below (skipped)."""
        mock_post.side_effect = [
            _ok_response(200),      # lead 1 — sent
            _error_response(400),   # lead 2 — failed (4xx, permanent)
            _ok_response(200),      # lead 3 — sent
        ]
        svc = self._service(threshold=25)
        leads = [
            make_lead(score=30),  # above, attempt → ok
            make_lead(score=35),  # above, attempt → 4xx fail
            make_lead(score=28),  # above, attempt → ok
            make_lead(score=20),  # below → skipped
            make_lead(score=10),  # below → skipped
        ]
        stats = svc.send_batch(leads)
        assert stats["sent"] == 2
        assert stats["failed"] == 1
        assert stats["skipped"] == 2

    @patch("app.services.webhook.httpx.post")
    def test_skipped_count_correct_mixed(self, mock_post):
        mock_post.return_value = _ok_response()
        svc = self._service(threshold=25)
        leads = [make_lead(score=30), make_lead(score=20), make_lead(score=15)]
        stats = svc.send_batch(leads)
        assert stats["skipped"] == 2
        assert stats["sent"] == 1


# ── build_webhook_service ─────────────────────────────────────────────────────

class TestBuildWebhookService:

    def test_returns_webhook_service_instance(self):
        svc = build_webhook_service(url="https://test.example.com/hook", threshold=30)
        assert isinstance(svc, WebhookService)

    def test_threshold_override_applied(self):
        svc = build_webhook_service(url="https://test.example.com/hook", threshold=42)
        assert svc.threshold == 42

    def test_url_override_applied(self):
        svc = build_webhook_service(url="https://custom.example.com/hook")
        assert svc.url == "https://custom.example.com/hook"

    def test_secret_override_applied(self):
        svc = build_webhook_service(
            url="https://test.example.com/hook",
            threshold=25,
            secret="mysecret",
        )
        assert svc.secret == "mysecret"

    def test_uses_config_defaults_when_no_overrides(self):
        from app.core.config import settings
        svc = build_webhook_service()
        assert svc.threshold == settings.webhook_score_threshold
        assert svc.url == settings.webhook_url
