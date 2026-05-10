import uuid
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models import ProxyRequest
from app.decision_mapper import mapper
from app.audit import AuditLogger

router = APIRouter()


@router.post("/proxy/execute")
async def proxy_execute(request: Request, body: ProxyRequest):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    audit = AuditLogger(request_id=request_id, operation_type=body.operationType)

    if not mapper.is_known(body.operationType):
        audit.error("UNKNOWN_OPERATION", f"'{body.operationType}' is not supported")
        return JSONResponse(
            status_code=400,
            content={"error": "Unknown operationType", "detail": f"'{body.operationType}' is not a supported operation"},
        )

    missing = mapper.missing_fields(body.operationType, body.payload)
    if missing:
        audit.validation_failed(missing)
        audit.error("VALIDATION_FAILED", missing)
        return JSONResponse(
            status_code=400,
            content={"error": "Validation failed", "detail": f"Missing required fields: {missing}"},
        )
    audit.validation_passed()

    provider = request.app.state.provider
    provider_name = request.app.state.provider_name

    try:
        audit.upstream_call(provider_name, "(resolving)")
        data, upstream_status, url = await mapper.dispatch(body.operationType, body.payload, provider)
        audit.upstream_response(provider_name, url, upstream_status)
    except RuntimeError as exc:
        audit.error("UPSTREAM_FAILED", str(exc))
        return JSONResponse(
            status_code=502,
            content={"error": "Upstream API failed", "detail": str(exc)},
        )

    audit.success()
    return JSONResponse(
        status_code=200,
        content={"requestId": request_id, "operationType": body.operationType, "data": data},
        headers={"X-Request-ID": request_id},
    )
