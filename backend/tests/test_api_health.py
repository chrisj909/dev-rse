from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class TestHealthEndpoints:
    def test_health_stats_reports_all_score_modes_and_schema_status(self, test_client, mock_session):
        properties_result = MagicMock()
        properties_result.scalar.return_value = 144961

        signals_result = MagicMock()
        signals_result.scalar.return_value = 144961

        scores_result = MagicMock()
        scores_result.all.return_value = [("broad", 144961), ("owner_occupant", 120000)]

        schema_result = MagicMock()
        schema_result.scalar.return_value = True

        mock_session.execute = AsyncMock(
            side_effect=[properties_result, signals_result, scores_result, schema_result]
        )

        resp = test_client.get("/api/health/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["properties"] == 144961
        assert body["signals"] == 144961
        assert body["scores"]["broad"] == 144961
        assert body["scores"]["owner_occupant"] == 120000
        assert body["scores"]["investor"] == 0
        assert body["score_schema"]["property_mode_unique_constraint"] is True