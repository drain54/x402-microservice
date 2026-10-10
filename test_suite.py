import os
import json
import time
import pytest
from fastapi.testclient import TestClient
from eth_account import Account
from eth_utils import to_bytes

# Ensure mock facilitator is enabled for tests
os.environ["MOCK_FACILITATOR_ENABLED"] = "true"
os.environ["X402_FACILITATOR_URL"] = "http://testserver/facilitator"

from main import app
from config import settings

client = TestClient(app)

def create_valid_payment_header(pay_to: str, amount: str, network: str = "base", asset: str = None, token_name: str = "USD Coin"):
    acct = Account.create()
    nonce = "0x" + os.urandom(32).hex()
    now = int(time.time())
    asset_addr = asset or settings.USDC_ASSET

    domain = {
        "name": token_name,
        "version": "2",
        "chainId": 8453 if network == "base" else 84532,
        "verifyingContract": asset_addr
    }
    types = {
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ]
    }
    message = {
        "from": acct.address,
        "to": pay_to,
        "value": int(amount),
        "validAfter": now - 60,
        "validBefore": now + 3600,
        "nonce": to_bytes(hexstr=nonce)
    }
    signed = Account.sign_typed_data(acct.key, domain, types, message)
    sig_hex = f"0x{signed.signature.hex()}"

    payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": network,
        "payload": {
            "signature": sig_hex,
            "authorization": {
                "from": acct.address,
                "to": pay_to,
                "value": str(amount),
                "validAfter": str(now - 60),
                "validBefore": str(now + 3600),
                "nonce": nonce
            }
        }
    }
    return json.dumps(payload)

def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["network"] == "base"

def test_mcp_server_card_discovery():
    resp = client.get("/.well-known/mcp/server-card.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "io.x402.web2markdown"
    assert "tools" in card
    assert len(card["tools"]) == 1
    assert card["pricing"]["currency"] == "USDC"

def test_extract_without_payment_returns_402():
    req_body = {"html": "<h1>Test Header</h1><p>Sample paragraph</p>"}
    resp = client.post("/v1/extract", json=req_body)
    assert resp.status_code == 402
    assert resp.headers.get("Paywall") == "x402"
    assert "application/x402-payment-v1+json" in resp.headers.get("Accept")
    reqs = resp.json()
    assert reqs["x402Version"] == 1
    assert reqs["scheme"] == "exact"
    assert reqs["network"] == "base"
    assert reqs["maxAmountRequired"] == settings.PRICE_ATOMIC
    assert reqs["asset"] == settings.USDC_ASSET
    assert "extensions" in reqs
    assert "bazaar" in reqs["extensions"]

def test_extract_with_invalid_payment_returns_402():
    bad_payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "payload": {
            "signature": "0x1234badsignature",
            "authorization": {
                "from": "0x1111111111111111111111111111111111111111",
                "to": settings.PAY_TO,
                "value": settings.PRICE_ATOMIC,
                "validAfter": str(int(time.time()) - 10),
                "validBefore": str(int(time.time()) + 1000),
                "nonce": "0x" + "00"*32
            }
        }
    }
    headers = {"X-PAYMENT": json.dumps(bad_payload)}
    resp = client.post("/v1/extract", json={"html": "<p>Hello</p>"}, headers=headers)
    assert resp.status_code == 402
    data = resp.json()
    assert data["error"] == "invalid_payment"

def test_extract_with_valid_payment_succeeds():
    header_val = create_valid_payment_header(
        pay_to=settings.PAY_TO,
        amount=settings.PRICE_ATOMIC,
        network=settings.NETWORK
    )
    headers = {"X-PAYMENT": header_val}
    html = """
    <html>
      <head><title>Page One</title></head>
      <body>
        <article>
          <h1>Hello World</h1>
          <p>This is a paragraph with a <a href="https://example.com">link</a>.</p>
          <table>
            <tr><th>Col A</th><th>Col B</th></tr>
            <tr><td>Val 1</td><td>Val 2</td></tr>
          </table>
        </article>
      </body>
    </html>
    """
    resp = client.post("/v1/extract", json={"html": html}, headers=headers)
    assert resp.status_code == 200
    res = resp.json()
    assert res["title"] == "Page One"
    assert "# Hello World" in res["markdown"]
    assert "[link](https://example.com)" in res["markdown"]
    assert "| Col A | Col B |" in res["markdown"]
    assert res["tables_found"] == 1
    assert res["links_found"] == 1

def test_ssrf_blocked():
    header_val = create_valid_payment_header(
        pay_to=settings.PAY_TO,
        amount=settings.PRICE_ATOMIC,
        network=settings.NETWORK
    )
    headers = {"X-PAYMENT": header_val}
    resp = client.post("/v1/extract", json={"url": "http://127.0.0.1:8080/admin"}, headers=headers)
    assert resp.status_code == 400
    res = resp.json()
    assert res["error"] == "ssrf_protection_triggered"
    assert res["retryable"] is False

def test_telemetry_endpoint():
    resp = client.get("/telemetry")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    assert "sample_size" in metrics
    assert "results_breakdown" in metrics
