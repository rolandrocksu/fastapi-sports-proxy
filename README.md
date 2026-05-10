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

The `app/decision_mapper` package handles routing and normalization.

Instead of a single large dictionary, it uses a class-based approach where each operation inherits from a base `Operation` class:

```python
class Operation(ABC):
    required_fields: tuple[str, ...] = ()
    provider_method: str

    @abstractmethod
    def normalize(self, raw: Any) -> Any: ...
```

Each specific operation (e.g., `GetMatchOperation` in `app/decision_mapper/get_match.py`) defines its required payload fields, the provider method to call, and how to normalize the response data.

On each request, the `DecisionMapper` (instantiated in `app/decision_mapper/__init__.py`):
1. Checks `operationType` exists → 400 if not.
2. Validates all `required_fields` are present in `payload` → 400 with missing field list if not.
3. Calls `getattr(provider, op.provider_method)(payload)` to dispatch to the adapter.
4. Runs `op.normalize(raw_response)` to produce a stable output shape.

Adding a new operation = Create a new subclass of `Operation` and add it to the `DecisionMapper` dictionary in `app/decision_mapper/__init__.py`.

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

Every log line uses a **unified structured format**:

```
[timestamp] [thread] [file:line] [level] [requestId=...]: {JSON payload}
```

Uvicorn's default access log is disabled — the middleware records richer request/response data in the same format.

### requestId Correlation

The middleware generates (or reuses) a `requestId` and shares it via a **ContextVar** so the router and audit logger use the exact same value. The ID appears in the `[requestId=...]` envelope of every log line and is also injected into every response as `X-Request-ID`.

### Sample: full request lifecycle (GetTeam)

```
[2026-05-10T14:03:09.602Z] [MainThread] [middleware.py:62] [INFO] [requestId=demo-abc-123]: {"event": "request", "method": "POST", "path": "/proxy/execute", "headers": {"content-type": "application/json", "authorization": "***"}, "bodySizeBytes": 56, "bodyPreview": "{\"operationType\": \"GetTeam\", \"payload\": {\"teamId\": 40}}"}
[2026-05-10T14:03:09.603Z] [MainThread] [audit.py:42] [INFO] [requestId=demo-abc-123]: {"event": "validation", "outcome": "pass", "operationType": "GetTeam"}
[2026-05-10T14:03:09.603Z] [MainThread] [audit.py:42] [INFO] [requestId=demo-abc-123]: {"event": "upstream_call", "provider": "openliga", "targetUrl": "(resolving)", "operationType": "GetTeam"}
[2026-05-10T14:03:10.469Z] [MainThread] [audit.py:42] [INFO] [requestId=demo-abc-123]: {"event": "upstream_response", "provider": "openliga", "targetUrl": "https://api.openligadb.de/getmatchesbyteamid/40/100/100", "upstreamStatus": 200, "latencyMs": 866.86, "operationType": "GetTeam"}
[2026-05-10T14:03:10.469Z] [MainThread] [audit.py:42] [INFO] [requestId=demo-abc-123]: {"event": "outcome", "result": "success", "totalLatencyMs": 866.94, "operationType": "GetTeam"}
[2026-05-10T14:03:10.470Z] [MainThread] [middleware.py:89] [INFO] [requestId=demo-abc-123]: {"event": "response", "statusCode": 200, "bodySizeBytes": 257, "bodyPreview": "{\"requestId\":\"demo-abc-123\",...}", "latencyMs": 868.01}
```

### Sample: validation failure

```
[2026-05-10T14:03:09.602Z] [MainThread] [audit.py:42] [INFO] [requestId=a1b2c3]: {"event": "validation", "outcome": "fail", "missingFields": ["leagueSeason"], "operationType": "GetLeagueMatches"}
[2026-05-10T14:03:09.602Z] [MainThread] [audit.py:42] [INFO] [requestId=a1b2c3]: {"event": "outcome", "result": "error", "errorCode": "VALIDATION_FAILED", "detail": "['leagueSeason']", "totalLatencyMs": 0.3, "operationType": "GetLeagueMatches"}
```

Body previews are truncated to `LOG_BODY_MAX_CHARS` (default: 200) for both request and response.
