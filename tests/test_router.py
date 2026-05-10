"""
Integration tests for router.py, middleware, and audit logging.

Uses TestClient with a mocked provider so no real HTTP calls are made.

Covers:
- POST /proxy/execute: all four operations (happy path)
- 400 on unknown operationType
- 400 on missing payload fields (single and multiple)
- 502 on upstream RuntimeError
- X-Request-ID header: propagated from request, generated if absent
- Malformed JSON body → 422
- Middleware: sensitive headers masked in logs
- Middleware: body preview truncated at configured limit
- Audit: JSON log lines emitted to stdout for success and error paths
"""

import json
import logging
import pytest
from unittest.mock import AsyncMock


# ---------------------------------------------------------------------------
# Happy path: all four operations
# ---------------------------------------------------------------------------

class TestOperationsHappyPath:
    def test_list_leagues_returns_200_with_normalized_data(self, client):
        c, mock = client
        mock.list_leagues.return_value = (
            200,
            [{"leagueId": 1, "leagueName": "BL", "leagueShortcut": "bl1", "leagueSeason": "2023"}],
            "https://api.openligadb.de/getavailableleagues",
        )

        r = c.post("/proxy/execute", json={"operationType": "ListLeagues", "payload": {}})

        assert r.status_code == 200
        body = r.json()
        assert body["operationType"] == "ListLeagues"
        assert isinstance(body["data"], list)
        assert body["data"][0]["leagueId"] == 1

    def test_get_league_matches_returns_200(self, client):
        c, mock = client
        raw_match = {
            "matchID": 100, "matchDateTimeUTC": "2023-08-18T18:30:00Z",
            "leagueName": "BL", "team1": {"teamName": "Bayern"},
            "team2": {"teamName": "Bremen"}, "matchIsFinished": True, "goals": [],
        }
        mock.get_league_matches.return_value = (200, [raw_match], "https://api.openligadb.de/getmatchdata/bl1/2023")

        r = c.post("/proxy/execute", json={
            "operationType": "GetLeagueMatches",
            "payload": {"leagueShortcut": "bl1", "leagueSeason": "2023"},
        })

        assert r.status_code == 200
        data = r.json()["data"]
        assert data[0]["matchId"] == 100
        assert data[0]["team1"] == "Bayern"

    def test_get_team_returns_200(self, client):
        c, mock = client
        mock.get_team.return_value = (
            200,
            {"teamId": 40, "teamName": "FC Bayern München", "shortName": "Bayern", "teamIconUrl": "http://icon"},
            "https://api.openligadb.de/getteamby/40",
        )

        r = c.post("/proxy/execute", json={"operationType": "GetTeam", "payload": {"teamId": 40}})

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["teamId"] == 40
        assert data["teamName"] == "FC Bayern München"

    def test_get_match_returns_200(self, client):
        c, mock = client
        raw = {
            "matchID": 61588, "matchDateTimeUTC": "2023-08-18T18:30:00Z",
            "leagueName": "BL", "team1": {"teamName": "Bayern"},
            "team2": {"teamName": "Bremen"}, "matchIsFinished": True,
            "goals": [{"scoreTeam1": 4, "scoreTeam2": 0}],
            "location": {"locationCity": "München"},
        }
        mock.get_match.return_value = (200, raw, "https://api.openligadb.de/getmatchbyid/61588")

        r = c.post("/proxy/execute", json={"operationType": "GetMatch", "payload": {"matchId": 61588}})

        assert r.status_code == 200
        data = r.json()["data"]
        assert data["matchId"] == 61588
        assert data["scoreTeam1"] == 4
        assert data["location"] == "München"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_unknown_operation_type_returns_400(self, client):
        c, _ = client
        r = c.post("/proxy/execute", json={"operationType": "DoSomethingWeird", "payload": {}})
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "Unknown operationType"
        assert "DoSomethingWeird" in body["detail"]

    def test_missing_single_required_field_returns_400(self, client):
        c, _ = client
        r = c.post("/proxy/execute", json={
            "operationType": "GetLeagueMatches",
            "payload": {"leagueShortcut": "bl1"},  # missing leagueSeason
        })
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "Validation failed"
        assert "leagueSeason" in body["detail"]

    def test_missing_multiple_required_fields_returns_400(self, client):
        c, _ = client
        r = c.post("/proxy/execute", json={
            "operationType": "GetLeagueMatches",
            "payload": {},
        })
        assert r.status_code == 400
        assert "leagueShortcut" in r.json()["detail"] or "leagueSeason" in r.json()["detail"]

    def test_missing_team_id_returns_400(self, client):
        c, _ = client
        r = c.post("/proxy/execute", json={"operationType": "GetTeam", "payload": {}})
        assert r.status_code == 400

    def test_missing_match_id_returns_400(self, client):
        c, _ = client
        r = c.post("/proxy/execute", json={"operationType": "GetMatch", "payload": {}})
        assert r.status_code == 400

    def test_upstream_runtime_error_returns_502(self, client):
        c, mock = client
        mock.list_leagues.side_effect = RuntimeError("Upstream failed after 4 attempts: HTTP 503")

        r = c.post("/proxy/execute", json={"operationType": "ListLeagues", "payload": {}})

        assert r.status_code == 502
        body = r.json()
        assert body["error"] == "Upstream API failed"

    def test_malformed_json_returns_422(self, client):
        c, _ = client
        r = c.post("/proxy/execute", content=b"not json", headers={"Content-Type": "application/json"})
        assert r.status_code == 422

    def test_missing_operation_type_returns_422(self, client):
        c, _ = client
        r = c.post("/proxy/execute", json={"payload": {}})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Request ID handling
# ---------------------------------------------------------------------------

class TestRequestId:
    def test_request_id_from_header_is_echoed_in_response_body(self, client):
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        r = c.post(
            "/proxy/execute",
            json={"operationType": "ListLeagues", "payload": {}},
            headers={"X-Request-ID": "my-custom-id-123"},
        )

        assert r.status_code == 200
        assert r.json()["requestId"] == "my-custom-id-123"

    def test_request_id_echoed_in_response_header(self, client):
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        r = c.post(
            "/proxy/execute",
            json={"operationType": "ListLeagues", "payload": {}},
            headers={"X-Request-ID": "header-id-456"},
        )

        assert r.headers.get("x-request-id") == "header-id-456"

    def test_request_id_generated_when_not_provided(self, client):
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        r = c.post("/proxy/execute", json={"operationType": "ListLeagues", "payload": {}})

        assert r.status_code == 200
        request_id = r.json().get("requestId")
        assert request_id is not None
        assert len(request_id) > 0

    def test_generated_request_ids_are_unique(self, client):
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        ids = {
            c.post("/proxy/execute", json={"operationType": "ListLeagues", "payload": {}}).json()["requestId"]
            for _ in range(5)
        }
        assert len(ids) == 5


# ---------------------------------------------------------------------------
# Helpers for log-asserting tests
# ---------------------------------------------------------------------------

def _parse_caplog(caplog_records) -> list[dict]:
    """Parse JSON from caplog records, skipping non-JSON lines."""
    result = []
    for r in caplog_records:
        try:
            result.append(json.loads(r.getMessage()))
        except (json.JSONDecodeError, TypeError):
            pass
    return result


# ---------------------------------------------------------------------------
# Middleware: sensitive header masking
# ---------------------------------------------------------------------------

class TestMiddlewareSensitiveHeaders:
    def test_authorization_header_masked_in_logs(self, client, caplog):
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        with caplog.at_level(logging.INFO, logger="app.middleware"):
            c.post(
                "/proxy/execute",
                json={"operationType": "ListLeagues", "payload": {}},
                headers={"Authorization": "Bearer secret-token"},
            )

        full_text = " ".join(r.getMessage() for r in caplog.records)
        assert "secret-token" not in full_text
        assert "***" in full_text

    def test_cookie_header_masked_in_logs(self, client, caplog):
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        with caplog.at_level(logging.INFO, logger="app.middleware"):
            c.post(
                "/proxy/execute",
                json={"operationType": "ListLeagues", "payload": {}},
                headers={"Cookie": "session=supersecret"},
            )

        full_text = " ".join(r.getMessage() for r in caplog.records)
        assert "supersecret" not in full_text

    def test_safe_headers_are_not_masked(self, client, caplog):
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        with caplog.at_level(logging.INFO, logger="app.middleware"):
            c.post(
                "/proxy/execute",
                json={"operationType": "ListLeagues", "payload": {}},
                headers={"X-Custom-Header": "visible-value"},
            )

        full_text = " ".join(r.getMessage() for r in caplog.records)
        assert "visible-value" in full_text


# ---------------------------------------------------------------------------
# Middleware: body truncation
# ---------------------------------------------------------------------------

class TestMiddlewareBodyTruncation:
    def test_large_body_preview_is_truncated(self, client, caplog):
        from app.config import settings
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        large_value = "x" * (settings.log_body_max_chars + 500)
        with caplog.at_level(logging.INFO, logger="app.middleware"):
            c.post(
                "/proxy/execute",
                json={"operationType": "ListLeagues", "payload": {"ignored": large_value}},
            )

        records = _parse_caplog(caplog.records)
        request_log = next((r for r in records if r.get("event") == "request"), None)
        assert request_log is not None
        assert len(request_log["bodyPreview"]) <= settings.log_body_max_chars


# ---------------------------------------------------------------------------
# Audit log content
# ---------------------------------------------------------------------------

class TestAuditLogs:
    def test_success_path_emits_all_lifecycle_events(self, client, caplog):
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        with caplog.at_level(logging.INFO, logger="app.audit"):
            c.post("/proxy/execute", json={"operationType": "ListLeagues", "payload": {}})

        records = _parse_caplog(caplog.records)
        events = {r["event"] for r in records}
        assert {"validation", "upstream_call", "upstream_response", "outcome"}.issubset(events)

        outcome = next(r for r in records if r.get("event") == "outcome")
        assert outcome["result"] == "success"

    def test_validation_failure_emits_fail_event(self, client, caplog):
        c, _ = client

        with caplog.at_level(logging.INFO, logger="app.audit"):
            c.post("/proxy/execute", json={"operationType": "GetTeam", "payload": {}})

        records = _parse_caplog(caplog.records)
        validation_log = next((r for r in records if r.get("event") == "validation"), None)
        assert validation_log is not None
        assert validation_log["outcome"] == "fail"
        assert "teamId" in validation_log["missingFields"]

    def test_unknown_op_emits_error_outcome(self, client, caplog):
        c, _ = client

        with caplog.at_level(logging.INFO, logger="app.audit"):
            c.post("/proxy/execute", json={"operationType": "Unknown", "payload": {}})

        records = _parse_caplog(caplog.records)
        outcome = next((r for r in records if r.get("event") == "outcome"), None)
        assert outcome is not None
        assert outcome["result"] == "error"
        assert outcome["errorCode"] == "UNKNOWN_OPERATION"

    def test_upstream_failure_emits_error_outcome(self, client, caplog):
        c, mock = client
        mock.list_leagues.side_effect = RuntimeError("upstream down")

        with caplog.at_level(logging.INFO, logger="app.audit"):
            c.post("/proxy/execute", json={"operationType": "ListLeagues", "payload": {}})

        records = _parse_caplog(caplog.records)
        outcome = next((r for r in records if r.get("event") == "outcome"), None)
        assert outcome["result"] == "error"
        assert outcome["errorCode"] == "UPSTREAM_FAILED"

    def test_all_audit_logs_contain_request_id_and_timestamp(self, client, caplog):
        c, mock = client
        mock.list_leagues.return_value = (200, [], "url")

        with caplog.at_level(logging.INFO, logger="app.audit"):
            c.post(
                "/proxy/execute",
                json={"operationType": "ListLeagues", "payload": {}},
                headers={"X-Request-ID": "trace-abc"},
            )

        records = _parse_caplog(caplog.records)
        audit_logs = [r for r in records if r.get("operationType") == "ListLeagues"]
        assert audit_logs, "Expected at least one audit record for ListLeagues"
        for log in audit_logs:
            assert "requestId" in log
            assert "timestamp" in log

    def test_upstream_response_log_contains_latency_and_status(self, client, caplog):
        c, mock = client
        mock.get_team.return_value = (
            200,
            {"teamId": 1, "teamName": "T", "shortName": "t", "teamIconUrl": "u"},
            "https://api.openligadb.de/getteamby/1",
        )

        with caplog.at_level(logging.INFO, logger="app.audit"):
            c.post("/proxy/execute", json={"operationType": "GetTeam", "payload": {"teamId": 1}})

        records = _parse_caplog(caplog.records)
        resp_log = next((r for r in records if r.get("event") == "upstream_response"), None)
        assert resp_log is not None
        assert resp_log["upstreamStatus"] == 200
        assert "latencyMs" in resp_log
        assert resp_log["targetUrl"] == "https://api.openligadb.de/getteamby/1"
