from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class TestRunSignalsCronAuth:
    def test_requires_authentication(self, test_client, monkeypatch):
        monkeypatch.setattr("app.api.cron.settings.cron_secret", "secret123")

        resp = test_client.get("/api/cron/run-signals")

        assert resp.status_code == 401

    def test_accepts_bearer_authentication(self, test_client, mock_session, monkeypatch):
        monkeypatch.setattr("app.api.cron.settings.cron_secret", "secret123")

        result = MagicMock()
        result.scalar.return_value = 0
        result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result)
        mock_session.commit = AsyncMock()

        monkeypatch.setattr(
            "app.api.cron.SignalEngine.process_batch",
            AsyncMock(return_value={"processed": 0}),
        )
        monkeypatch.setattr(
            "app.api.cron.ScoringEngine.score_batch",
            AsyncMock(return_value={"processed": 0}),
        )

        resp = test_client.get(
            "/api/cron/run-signals",
            headers={"Authorization": "Bearer secret123"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_accepts_query_secret(self, test_client, mock_session, monkeypatch):
        monkeypatch.setattr("app.api.cron.settings.cron_secret", "secret123")

        result = MagicMock()
        result.scalar.return_value = 0
        result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result)
        mock_session.commit = AsyncMock()

        monkeypatch.setattr(
            "app.api.cron.SignalEngine.process_batch",
            AsyncMock(return_value={"processed": 0}),
        )
        monkeypatch.setattr(
            "app.api.cron.ScoringEngine.score_batch",
            AsyncMock(return_value={"processed": 0}),
        )

        resp = test_client.get("/api/cron/run-signals?cron_secret=secret123")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_returns_json_error_on_signal_failure(self, test_client, mock_session, monkeypatch):
        """Cron endpoint must return JSON {status: error} not a bare 500 when processing fails."""
        monkeypatch.setattr("app.api.cron.settings.cron_secret", "secret123")

        result = MagicMock()
        result.scalar.return_value = 5
        result.scalars.return_value.all.return_value = [MagicMock()]
        mock_session.execute = AsyncMock(return_value=result)
        mock_session.rollback = AsyncMock()

        monkeypatch.setattr(
            "app.api.cron.SignalEngine.process_batch",
            AsyncMock(side_effect=RuntimeError("deadlock detected")),
        )

        resp = test_client.get(
            "/api/cron/run-signals",
            headers={"x-cron-secret": "secret123"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert "deadlock" in body["error"].lower()

    def test_returns_pagination_fields(self, test_client, mock_session, monkeypatch):
        """Response must include has_more and next_offset for rescore pagination."""
        monkeypatch.setattr("app.api.cron.settings.cron_secret", "secret123")

        result = MagicMock()
        result.scalar.return_value = 1000
        result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result)
        mock_session.commit = AsyncMock()

        monkeypatch.setattr(
            "app.api.cron.SignalEngine.process_batch",
            AsyncMock(return_value={"processed": 0}),
        )
        monkeypatch.setattr(
            "app.api.cron.ScoringEngine.score_batch",
            AsyncMock(return_value={"processed": 0}),
        )

        resp = test_client.get(
            "/api/cron/run-signals?offset=0&limit=500",
            headers={"x-cron-secret": "secret123"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "has_more" in body
        assert "next_offset" in body
        assert "total_properties" in body