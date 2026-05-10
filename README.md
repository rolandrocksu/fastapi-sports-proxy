# Generic Reverse Proxy

A FastAPI service that acts as a generic reverse proxy to external sports APIs via an adapter pattern.

---

## How to Run

### Docker Compose (recommended)

```bash
docker compose up --build
```

Service runs on **http://localhost:8010**.  
Postgres is available on host port **5433** (maps to container 5432) — named separately to avoid clashing with a local Postgres.

### Local (without Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Optional env vars (all have defaults):

```bash
PROVIDER=openliga          # which adapter to use
RATE_LIMIT_RPS=5           # max upstream calls per second
MAX_RETRIES=3              # retry attempts on transient errors
BACKOFF_BASE_DELAY=0.5     # seconds (doubles each attempt)
BACKOFF_MAX_DELAY=10.0     # seconds (cap)
LOG_BODY_MAX_CHARS=200     # body preview truncation
```

---

## Endpoint

```
POST /proxy/execute
Content-Type: application/json
```

Request body:
```json
{
  "operationType": "<string>",
  "payload": { ... }
}
```

---

## Operations, Payload Schemas & Normalized Responses

### 1. ListLeagues

**Payload:** _(no required fields)_
```json
{ "operationType": "ListLeagues", "payload": {} }
```

**Normalized response fields:**
```json
{
  "requestId": "...",
  "operationType": "ListLeagues",
  "data": [
    {
      "leagueId": 4442,
      "leagueName": "1. Fussball-Bundesliga 2023/2024",
      "leagueShortcut": "bl1",
      "leagueSeason": "2023"
    }
  ]
}
```

**Example curl:**
```bash
curl -s -X POST http://localhost:8010/proxy/execute \
  -H "Content-Type: application/json" \
  -d '{"operationType": "ListLeagues", "payload": {}}'
```

---

### 2. GetLeagueMatches

**Required payload fields:** `leagueShortcut` (string), `leagueSeason` (string)
```json
{
  "operationType": "GetLeagueMatches",
  "payload": { "leagueShortcut": "bl1", "leagueSeason": "2023" }
}
```

**Normalized response fields (per match):**
```json
{
  "matchId": 61588,
  "matchDateTime": "2023-08-18T18:30:00Z",
  "leagueName": "1. Fussball-Bundesliga 2023/2024",
  "team1": "FC Bayern München",
  "team2": "Werder Bremen",
  "scoreTeam1": 4,
  "scoreTeam2": 0,
  "isFinished": true
}
```

**Example curl:**
```bash
curl -s -X POST http://localhost:8010/proxy/execute \
  -H "Content-Type: application/json" \
  -d '{"operationType": "GetLeagueMatches", "payload": {"leagueShortcut": "bl1", "leagueSeason": "2023"}}'
```

---

### 3. GetTeam

**Required payload fields:** `teamId` (integer)
```json
{
  "operationType": "GetTeam",
  "payload": { "teamId": 40 }
}
```

**Normalized response fields:**
```json
{
  "teamId": 40,
  "teamName": "FC Bayern München",
  "shortName": "Bayern",
  "teamIconUrl": "https://..."
}
```

**Example curl:**
```bash
curl -s -X POST http://localhost:8010/proxy/execute \
  -H "Content-Type: application/json" \
  -d '{"operationType": "GetTeam", "payload": {"teamId": 40}}'
```

---

### 4. GetMatch

**Required payload fields:** `matchId` (integer)
```json
{
  "operationType": "GetMatch",
  "payload": { "matchId": 61588 }
}
```

**Normalized response fields:**
```json
{
  "matchId": 61588,
  "matchDateTime": "2023-08-18T18:30:00Z",
  "leagueName": "1. Fussball-Bundesliga 2023/2024",
  "team1": "FC Bayern München",
  "team2": "Werder Bremen",
  "scoreTeam1": 4,
  "scoreTeam2": 0,
  "isFinished": true,
  "location": "München"
}
```

**Example curl:**
```bash
curl -s -X POST http://localhost:8010/proxy/execute \
  -H "Content-Type: application/json" \
  -d '{"operationType": "GetMatch", "payload": {"matchId": 61588}}'
```

---

## How the Decision Mapper Works

`app/decision_mapper.py` holds a single `OPERATIONS` dict keyed by `operationType`:

```python
OPERATIONS = {
    "ListLeagues": {
        "required": [],                    # fields validated from payload
        "method": "list_leagues",          # provider method to call
        "normalizer": _normalize_leagues,  # transforms raw response
    },
    ...
}
```

On each request the mapper:
1. Checks `operationType` exists in `OPERATIONS` → 400 if not.
2. Validates all `required` fields are present in `payload` → 400 with missing field list if not.
3. Calls `getattr(provider, spec["method"])(payload)` to dispatch to the adapter.
4. Runs `spec["normalizer"](raw_response)` to produce a stable output shape.

Adding a new operation = one dict entry + one normalizer function.

---

## Adapter Interface & OpenLiga Implementation

**`app/providers/base.py`** defines the abstract interface:
```python
class SportsProvider(ABC):
    async def list_leagues(self, payload: dict) -> tuple[int, list, str]: ...
    async def get_league_matches(self, payload: dict) -> tuple[int, list, str]: ...
    async def get_team(self, payload: dict) -> tuple[int, dict, str]: ...
    async def get_match(self, payload: dict) -> tuple[int, dict, str]: ...
```

Each method returns `(upstream_status_code, raw_data, target_url)`.

**`app/providers/openliga.py`** implements `SportsProvider` against `https://api.openligadb.de`.  
All OpenLiga-specific URLs and parameters are confined to this file.  
Provider selection happens at startup in `app/main.py` based on the `PROVIDER` env var:

```python
if settings.provider == "openliga":
    app.state.provider = OpenLigaProvider()
```

To swap providers: implement `SportsProvider`, then set `PROVIDER=yourprovider` and add the branch in `startup()`.

---

## Rate Limiting & Exponential Backoff

Configured via env vars (see top). Implemented inside `OpenLigaProvider`:

| Setting | Env var | Default |
|---|---|---|
| Max upstream RPS | `RATE_LIMIT_RPS` | `5` |
| Retry attempts | `MAX_RETRIES` | `3` |
| Base backoff delay | `BACKOFF_BASE_DELAY` | `0.5s` |
| Max backoff delay | `BACKOFF_MAX_DELAY` | `10.0s` |

**Rate limiter** — token bucket (`RateLimiter` class): refills tokens at `rps` per second, blocks via `asyncio.sleep` when bucket is empty.

**Backoff** — on HTTP 429/5xx or connection timeout, retries up to `MAX_RETRIES` times with:
```
delay = min(BASE_DELAY * 2^attempt + uniform(0, 0.5), MAX_DELAY)
```

---

## Log Format

All logs are JSON lines on stdout. Two log sources:

### Middleware logs (every request/response)
```json
{"event": "request", "requestId": "a1b2c3", "timestamp": "2026-05-10T12:00:00Z", "method": "POST", "path": "/proxy/execute", "headers": {"content-type": "application/json", "authorization": "***"}, "bodySizeBytes": 72, "bodyPreview": "{\"operationType\": \"GetTeam\", \"payload\": {\"teamId\": 40}}"}
{"event": "response", "requestId": "a1b2c3", "timestamp": "2026-05-10T12:00:00Z", "statusCode": 200, "bodySizeBytes": 148, "latencyMs": 213.4}
```

### Audit logs (per operation step)
```json
{"event": "validation", "requestId": "a1b2c3", "timestamp": "2026-05-10T12:00:00Z", "operationType": "GetTeam", "outcome": "pass"}
{"event": "upstream_call", "requestId": "a1b2c3", "timestamp": "2026-05-10T12:00:00Z", "operationType": "GetTeam", "provider": "openliga", "targetUrl": "(resolving)"}
{"event": "upstream_response", "requestId": "a1b2c3", "timestamp": "2026-05-10T12:00:00Z", "operationType": "GetTeam", "provider": "openliga", "targetUrl": "https://api.openligadb.de/getteamby/40", "upstreamStatus": 200, "latencyMs": 198.1}
{"event": "outcome", "requestId": "a1b2c3", "timestamp": "2026-05-10T12:00:00Z", "operationType": "GetTeam", "result": "success", "totalLatencyMs": 201.3}
```

### Error log sample (validation failure)
```json
{"event": "validation", "requestId": "a1b2c3", "timestamp": "2026-05-10T12:00:00Z", "operationType": "GetLeagueMatches", "outcome": "fail", "missingFields": ["leagueSeason"]}
{"event": "outcome", "requestId": "a1b2c3", "timestamp": "2026-05-10T12:00:00Z", "operationType": "GetLeagueMatches", "result": "error", "errorCode": "VALIDATION_FAILED", "detail": "['leagueSeason']", "totalLatencyMs": 0.3}
```
