import json
import logging
from typing import Dict, Any, Optional
import httpx
from fastapi import Request, Response
from config import settings

logger = logging.getLogger("x402_middleware")

def generate_payment_requirements(resource_url: str) -> Dict[str, Any]:
    """
    Constructs top-level V1 x402 payment requirements compliant with PayAI facilitator
    and PayAI Bazaar discovery standards.
    """
    return {
        "x402Version": 1,
        "scheme": "exact",
        "network": settings.NETWORK,
        "maxAmountRequired": settings.PRICE_ATOMIC,
        "resource": {
            "url": resource_url,
            "description": "Clean Webpage Markdown Sanitization API for Autonomous Agents",
            "mimeType": "application/json",
            "serviceName": "Web2Markdown Sanitizer",
            "tags": ["web", "markdown", "sanitization", "agent-tool", "html-cleaning"]
        },
        "payTo": settings.PAY_TO,
        "maxTimeoutSeconds": 60,
        "asset": settings.USDC_ASSET,
        "extra": {
            "name": settings.USDC_NAME,
            "version": "2"
        },
        # PayAI Bazaar Discovery metadata
        "extensions": {
            "bazaar": {
                "info": {
                    "input": {
                        "type": "http",
                        "method": "POST",
                        "bodyType": "json",
                        "body": {
                            "url": "string (optional external webpage URL)",
                            "html": "string (optional direct raw HTML)",
                            "include_links": "boolean (default: true)"
                        }
                    },
                    "output": {
                        "type": "json",
                        "example": {
                            "title": "Document Title",
                            "markdown": "# Document Content...",
                            "content_length": 1280,
                            "source_url": "https://example.com",
                            "tables_found": 1,
                            "links_found": 4
                        }
                    }
                },
                "schema": {}
            }
        }
    }

def create_402_response(resource_url: str) -> Response:
    """Creates a standard HTTP 402 Payment Required response."""
    requirements = generate_payment_requirements(resource_url)
    return Response(
        content=json.dumps(requirements, indent=2),
        status_code=402,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/x402-payment-v1+json",
            "Paywall": "x402",
            "X-Payment-Required-Network": settings.NETWORK,
            "X-Payment-Required-Amount": settings.PRICE_ATOMIC,
            "X-Payment-Required-Asset": settings.USDC_ASSET
        }
    )

def parse_x_payment_header(header_value: str) -> Dict[str, Any]:
    """
    Robust parsing of X-PAYMENT header.
    Handles raw JSON or hex-encoded 0x payloads safely without triggering
    ValueError on string prefixes.
    """
    clean_val = header_value.strip()
    if clean_val.startswith("0x"):
        raw_bytes = bytes.fromhex(clean_val[2:])
        return json.loads(raw_bytes.decode("utf-8"))
    return json.loads(clean_val)

def normalize_v1_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes V2 incoming payload to V1 structure expected by PayAI facilitator.
    """
    if payload.get("accepted") and payload.get("x402Version", 1) != 1:
        payload = {
            "x402Version": 1,
            "scheme": payload.get("scheme", "exact"),
            "network": payload["accepted"].get("network", settings.NETWORK),
            "payload": payload.get("payload", {})
        }
    if "x402Version" in payload:
        payload["x402Version"] = 1
    return payload

async def verify_and_settle_payment(request: Request, resource_url: str) -> Optional[Response]:
    """
    Validates payment via X-PAYMENT header.
    Returns None if payment is valid and settled successfully.
    Returns a FastAPI Response (402 or 502) if verification or settlement fails.
    """
    payment_header = request.headers.get("X-PAYMENT")
    if not payment_header:
        return create_402_response(resource_url)

    try:
        raw_payload = parse_x_payment_header(payment_header)
        payload = normalize_v1_payload(raw_payload)
    except Exception as e:
        logger.warning(f"Malformed X-PAYMENT header: {e}")
        return Response(
            content=json.dumps({
                "error": "malformed_payment_header",
                "retryable": True,
                "reason": f"Failed to parse X-PAYMENT header: {str(e)}",
                "action": "provide_valid_eip3009_json"
            }),
            status_code=400,
            headers={"Content-Type": "application/json"}
        )

    # Prepare V1 requirements payload for the facilitator
    v1_requirements = {
        "scheme": "exact",
        "network": settings.NETWORK,
        "maxAmountRequired": settings.PRICE_ATOMIC,
        "resource": resource_url,
        "description": "Clean Webpage Markdown Extraction API",
        "mimeType": "application/json",
        "payTo": settings.PAY_TO,
        "maxTimeoutSeconds": 60,
        "asset": settings.USDC_ASSET,
        "extra": {
            "name": settings.USDC_NAME,
            "version": "2"
        }
    }

    # Check if request is targeting internal mock facilitator directly on the same app
    facilitator_url = settings.FACILITATOR_URL
    app_instance = request.app
    transport = None

    if facilitator_url.startswith("http://testserver") or facilitator_url.startswith("http://localapp"):
        transport = httpx.ASGITransport(app=app_instance)

    async with httpx.AsyncClient(transport=transport, timeout=30.0) as client:
        # Step 1: Verify payment authorization
        try:
            vr = await client.post(
                f"{facilitator_url}/verify",
                json={
                    "paymentPayload": payload,
                    "paymentRequirements": v1_requirements
                },
                headers={"Content-Type": "application/json"}
            )
            ver = vr.json()
        except Exception as e:
            logger.error(f"Facilitator /verify connection error: {e}")
            return Response(
                content=json.dumps({
                    "error": "facilitator_unreachable",
                    "retryable": True,
                    "reason": f"Could not reach facilitator at {facilitator_url}: {str(e)}"
                }),
                status_code=502,
                headers={"Content-Type": "application/json"}
            )

        if not ver.get("isValid"):
            invalid_reason = ver.get("invalidReason", "signature_verification_failed")
            return Response(
                content=json.dumps({
                    "error": "invalid_payment",
                    "retryable": False,
                    "reason": invalid_reason,
                    "action": "re_sign_authorization_with_valid_parameters"
                }),
                status_code=402,
                headers={"Content-Type": "application/json"}
            )

        # Step 2: Settle on-chain via facilitator Multicall3
        try:
            sr = await client.post(
                f"{facilitator_url}/settle",
                json={
                    "paymentPayload": payload,
                    "paymentRequirements": v1_requirements
                },
                headers={"Content-Type": "application/json"}
            )
            settled = sr.json()
        except Exception as e:
            logger.error(f"Facilitator /settle connection error: {e}")
            return Response(
                content=json.dumps({
                    "error": "facilitator_settle_unreachable",
                    "retryable": True,
                    "reason": f"Could not complete settlement with facilitator: {str(e)}"
                }),
                status_code=502,
                headers={"Content-Type": "application/json"}
            )

        if not settled.get("success"):
            error_reason = settled.get("errorReason", "settlement_execution_failed")
            return Response(
                content=json.dumps({
                    "error": "settlement_failed",
                    "retryable": False,
                    "reason": error_reason
                }),
                status_code=502,
                headers={"Content-Type": "application/json"}
            )

    # Succeeded
    return None
