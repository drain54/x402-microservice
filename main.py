import time
from typing import Dict, Any
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from config import settings
from security import is_safe_url
from service import ExtractRequest, ExtractResponse, html_to_clean_markdown
from x402_mw import verify_and_settle_payment, create_402_response
from mock_facilitator import mock_router
from telemetry import telemetry

app = FastAPI(
    title="x402 Web2Markdown Sanitizer API",
    description="Clean, deterministic Markdown extraction micro-service with HTTP 402 pay-per-call micropayments on Base network.",
    version="1.0.0"
)

# Mount mock facilitator if enabled
if settings.MOCK_FACILITATOR_ENABLED:
    app.include_router(mock_router)

# -------------------------------------------------------------
# Free Discovery & Health Handshake Endpoints (Scanner friendly)
# -------------------------------------------------------------

@app.get("/health")
async def health():
    """Standard health check endpoint."""
    telemetry.log_event("/health", "GET", "client", "free_handshake")
    return {
        "status": "healthy",
        "service": "x402-web2markdown-microservice",
        "network": settings.NETWORK,
        "asset": settings.USDC_ASSET,
        "price_atomic": settings.PRICE_ATOMIC,
        "facilitator": settings.FACILITATOR_URL,
        "mock_facilitator": settings.MOCK_FACILITATOR_ENABLED
    }

@app.get("/telemetry")
async def telemetry_metrics():
    """
    Returns empirical machine-verifiable telemetry metrics for autonomous agent routing.
    No synthetic or hallucinated metrics.
    """
    summary = telemetry.get_summary()
    return {
        "metrics": summary,
        "sla": {
            "max_timeout_seconds": 60,
            "deterministic_parser": "BeautifulSoup4 + DOM sanitization",
            "settlement_gas": "Sponsored by Facilitator (Multicall3)"
        }
    }

@app.get("/.well-known/mcp/server-card.json")
async def mcp_server_card(request: Request):
    """
    Standard MCP discovery server card.
    Free discovery for platforms like PayAI Bazaar, Smithery, Glama, and MCP Registry.
    """
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    telemetry.log_event("/.well-known/mcp/server-card.json", "GET", request.client.host if request.client else "unknown", "free_handshake")
    return {
        "name": "io.x402.web2markdown",
        "title": "Web2Markdown Sanitizer API",
        "description": "Extracts clean, sanitized, LLM-optimized Markdown from external URLs or HTML snippets.",
        "version": "1.0.0",
        "remotes": [
            {
                "type": "streamable-http",
                "url": f"{base_url}/v1/extract"
            }
        ],
        "pricing": {
            "model": "pay-per-call",
            "currency": "USDC",
            "network": "Base",
            "atomic_units": settings.PRICE_ATOMIC,
            "cost_usd": float(settings.PRICE_ATOMIC) / 1_000_000
        },
        "tools": [
            {
                "name": "extract_clean_markdown",
                "description": "Takes a target web URL or raw HTML, strips noise/scripts/ads, and returns pure Markdown text with table & link telemetry.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Target public web URL to fetch and convert to Markdown"
                        },
                        "html": {
                            "type": "string",
                            "description": "Direct raw HTML content to sanitize"
                        },
                        "include_links": {
                            "type": "boolean",
                            "description": "Whether to retain inline markdown links [text](url)"
                        }
                    }
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "markdown": {"type": "string"},
                        "content_length": {"type": "integer"},
                        "source_url": {"type": "string"},
                        "tables_found": {"type": "integer"},
                        "links_found": {"type": "integer"}
                    }
                }
            }
        ]
    }

# -------------------------------------------------------------
# Monetized x402 Paid Endpoint
# -------------------------------------------------------------

@app.post("/v1/extract", response_model=ExtractResponse)
async def extract_markdown(req: ExtractRequest, request: Request):
    """
    Pay-per-call Markdown extraction endpoint.
    Protected by HTTP 402 with PayAI / x402 EIP-3009 payment standard.
    """
    resource_url = str(request.url)
    remote_host = request.client.host if request.client else "unknown"

    # Step 1: Payment Verification & Settlement Gate
    payment_error_response = await verify_and_settle_payment(request, resource_url)
    if payment_error_response is not None:
        if payment_error_response.status_code == 402:
            telemetry.log_event("/v1/extract", "POST", remote_host, "402_no_payment" if not request.headers.get("X-PAYMENT") else "402_invalid_payment")
        elif payment_error_response.status_code == 502:
            telemetry.log_event("/v1/extract", "POST", remote_host, "502_settle_failed")
        return payment_error_response

    # Step 2: Validate Input
    if not req.url and not req.html:
        return JSONResponse(
            status_code=400,
            content={
                "error": "missing_input",
                "retryable": False,
                "reason": "Either 'url' or 'html' parameter must be provided in request body.",
                "action": "provide_url_or_html"
            }
        )

    raw_html = ""
    source_url = None

    if req.html:
        raw_html = req.html
    elif req.url:
        source_url = req.url
        # SSRF Security Gate
        safe, reason = is_safe_url(req.url)
        if not safe:
            telemetry.log_event("/v1/extract", "POST", remote_host, "ssrf_blocked", {"url": req.url})
            return JSONResponse(
                status_code=400,
                content={
                    "error": "ssrf_protection_triggered",
                    "retryable": False,
                    "reason": reason,
                    "action": "use_public_http_url"
                }
            )

        # Bounded streaming download (Max 5MB)
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(req.url)
                if resp.status_code >= 400:
                    return JSONResponse(
                        status_code=422,
                        content={
                            "error": "upstream_fetch_failed",
                            "retryable": True,
                            "reason": f"Target server returned HTTP {resp.status_code}",
                            "upstream_status": resp.status_code
                        }
                    )
                if len(resp.content) > 5 * 1024 * 1024:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "payload_too_large",
                            "retryable": False,
                            "reason": "Target page exceeds maximum allowed payload size of 5MB.",
                            "action": "target_smaller_page"
                        }
                    )
                raw_html = resp.text
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={
                    "error": "target_unreachable",
                    "retryable": True,
                    "reason": f"Connection failed to target URL: {str(e)}"
                }
            )

    # Step 3: Parse and sanitize HTML
    try:
        title, md, tables_count, links_count = html_to_clean_markdown(
            raw_html,
            base_url=source_url,
            include_links=req.include_links
        )

        telemetry.log_event("/v1/extract", "POST", remote_host, "paid_ok", {
            "source_url": source_url,
            "markdown_len": len(md),
            "tables": tables_count,
            "links": links_count
        })

        return ExtractResponse(
            title=title,
            markdown=md,
            content_length=len(md),
            source_url=source_url,
            tables_found=tables_count,
            links_found=links_count
        )
    except Exception as e:
        telemetry.log_event("/v1/extract", "POST", remote_host, "500_paid_crash", {"error": str(e)})
        return JSONResponse(
            status_code=500,
            content={
                "error": "markdown_conversion_failed",
                "retryable": True,
                "reason": f"Error parsing HTML DOM: {str(e)}"
            }
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False)
