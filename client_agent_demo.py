#!/usr/bin/env python3
"""
client_agent_demo.py
Demonstration script showing how an autonomous AI agent discovers, handles HTTP 402,
constructs an EIP-3009 payment authorization, settles via facilitator, and purchases
the service.
"""

import os
import json
import time
import httpx
from eth_account import Account
from eth_utils import to_bytes

def run_agent_workflow():
    service_base = os.getenv("TARGET_SERVICE_URL", "http://127.0.0.1:8024")
    print("=" * 65)
    print("🤖 Autonomous Agent x402 Discovery & Purchase Simulation")
    print("=" * 65)

    # 1. Agent Discovery: Fetch MCP Server Card
    print(f"\n[Step 1] Autonomous Discovery: Querying {service_base}/.well-known/mcp/server-card.json")
    with httpx.Client(timeout=10) as client:
        card_resp = client.get(f"{service_base}/.well-known/mcp/server-card.json")
        card = card_resp.json()
        print(f"  ✓ Discovered Tool: '{card['tools'][0]['name']}'")
        print(f"  ✓ Tool Description: {card['tools'][0]['description'][:70]}...")
        print(f"  ✓ Declared Pricing: {card['pricing']['cost_usd']} USD ({card['pricing']['atomic_units']} atomic USDC on {card['pricing']['network']})")
        endpoint_url = card["remotes"][0]["url"]

    # 2. Agent Requests Paid Resource Without Payment -> Expects HTTP 402
    test_html = """
    <html>
      <head><title>Agent Economy Research Memo</title></head>
      <body>
        <nav><a href="/home">Home</a></nav>
        <main>
          <h1>Autonomous Agent Micropayments with x402</h1>
          <p>Machine-to-Machine commerce enables agents to purchase specialized micro-services per call.</p>
          <table>
            <tr><th>Metric</th><th>Target</th></tr>
            <tr><td>Pricing</td><td>$0.005 USDC</td></tr>
            <tr><td>Settlement Time</td><td>< 2.5s</td></tr>
          </table>
          <p>Read more at <a href="https://payai.network">PayAI Network</a>.</p>
        </main>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    sample_request_body = {
        "html": test_html,
        "include_links": True
    }

    print(f"\n[Step 2] Probe Endpoint: POST {endpoint_url} (No Payment Header)")
    with httpx.Client(timeout=10) as client:
        probe_resp = client.post(endpoint_url, json=sample_request_body)
        print(f"  HTTP Status Code: {probe_resp.status_code} (Expected 402)")
        assert probe_resp.status_code == 402, f"Expected 402, got {probe_resp.status_code}"
        
        reqs = probe_resp.json()
        print(f"  ✓ Parsed x402 Requirements:")
        print(f"    - Network: {reqs['network']}")
        print(f"    - Scheme: {reqs['scheme']}")
        print(f"    - Amount: {reqs['maxAmountRequired']} units")
        print(f"    - PayTo: {reqs['payTo']}")
        print(f"    - Asset: {reqs['asset']}")

    # 3. Agent Signs EIP-3009 TransferWithAuthorization
    print("\n[Step 3] Authorizing Micropayment via EIP-3009 Typed Signature")
    # Ephemeral or configured test wallet
    # Generate ephemeral key if none provided
    raw_key = os.getenv("AGENT_WALLET_KEY")
    if not raw_key:
        import secrets
        raw_key = "0x" + secrets.token_hex(32)
    private_key = raw_key
    agent_acct = Account.from_key(private_key)
    print(f"  Agent Wallet Address: {agent_acct.address}")

    nonce = "0x" + os.urandom(32).hex()
    now = int(time.time())
    extra = reqs.get("extra", {})

    domain = {
        "name": extra.get("name", "USD Coin"),
        "version": extra.get("version", "2"),
        "chainId": 8453 if reqs.get("network") == "base" else 84532,
        "verifyingContract": reqs["asset"]
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
        "from": agent_acct.address,
        "to": reqs["payTo"],
        "value": int(reqs["maxAmountRequired"]),
        "validAfter": now - 60,
        "validBefore": now + 3600,
        "nonce": to_bytes(hexstr=nonce)
    }

    signed = Account.sign_typed_data(agent_acct.key, domain, types, message)
    sig_hex = f"0x{signed.signature.hex()}"
    print(f"  ✓ Signature generated: {sig_hex[:20]}...{sig_hex[-10:]}")

    payment_payload = {
        "x402Version": 1,
        "scheme": reqs.get("scheme", "exact"),
        "network": reqs.get("network", "base"),
        "payload": {
            "signature": sig_hex,
            "authorization": {
                "from": agent_acct.address,
                "to": reqs["payTo"],
                "value": str(reqs["maxAmountRequired"]),
                "validAfter": str(now - 60),
                "validBefore": str(now + 3600),
                "nonce": nonce
            }
        }
    }

    # 4. Agent Retries Request with X-PAYMENT Header
    print(f"\n[Step 4] Executing Paid Request with 'X-PAYMENT' Header")
    headers = {
        "Content-Type": "application/json",
        "X-PAYMENT": json.dumps(payment_payload)
    }

    with httpx.Client(timeout=15) as client:
        paid_resp = client.post(endpoint_url, json=sample_request_body, headers=headers)
        print(f"  HTTP Status Code: {paid_resp.status_code}")
        assert paid_resp.status_code == 200, f"Expected 200, got {paid_resp.status_code}: {paid_resp.text}"
        
        result = paid_resp.json()
        print(f"  ✓ Extraction Succeeded!")
        print(f"  ✓ Document Title: '{result['title']}'")
        print(f"  ✓ Content Length: {result['content_length']} characters")
        print(f"  ✓ Tables Extracted: {result['tables_found']}")
        print(f"  ✓ Links Extracted: {result['links_found']}")
        print("\n  --- Rendered Markdown Output Preview ---")
        for line in result["markdown"].splitlines()[:12]:
            print(f"  | {line}")
        print("  ----------------------------------------")

    # 5. Agent inspects telemetry endpoint
    print(f"\n[Step 5] Checking Micro-service Empirical Telemetry")
    with httpx.Client(timeout=5) as client:
        telem_resp = client.get(f"{service_base}/telemetry")
        print(f"  Telemetry Response: {json.dumps(telem_resp.json(), indent=2)}")

    print("\n✅ End-to-end x402 workflow verified successfully!\n")

if __name__ == "__main__":
    run_agent_workflow()
