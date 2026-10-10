# x402 Pay-Per-Call Micro-service Scaffold
*Autonomous Agent Micropayment Micro-service on Base Network (USDC)*

This repository contains a production-ready, modular micro-service scaffold compliant with the **x402 HTTP Payment Standard**, **PayAI Facilitator (V1)**, **PayAI Bazaar Discovery**, and **MCP Server Specification**.

---

## 📌 Architecture Overview

```
                          [ Autonomous AI Agent ]
                                     |
               1. Discover /.well-known/mcp/server-card.json
                                     |
               2. Probe POST /v1/extract (No Payment)
                                     |
                                < HTTP 402 >
                   (Returns x402 V1 Payment Requirements)
                                     |
               3. Agent Signs EIP-3009 Authorization
                                     |
               4. Retry POST /v1/extract with X-PAYMENT header
                                     |
                       [ x402 Middleware ]
                      /                   \\
            5. Verify Payment       6. Settle On-Chain
                   \\                     /
                [ Facilitator (PayAI / Mock) ]
                                     |
               7. Deliver Sanitized Markdown to Agent
```

### Key Highlights
- **Target Use-Case**: Deterministic Webpage HTML to Markdown Sanitization API for Autonomous Agents.
- **Micro-pricing**: $0.005 USDC per call (`5000` atomic units, 6 decimals).
- **Network Defaults**: Base Mainnet (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, EIP-712 domain name: `USD Coin`).
- **Free Discovery**: Non-monetized `/health`, `/telemetry`, and `/.well-known/mcp/server-card.json` endpoints allow automated AI marketplace scanners (Smithery, Glama, MCP Registry, PayAI) to index the tool without 402 handshake failures.
- **Security Guardrails**: Strict SSRF guard blocking all loopback, RFC 1918 private IP, link-local, and reserved network resolutions. Bounded streaming (5MB max).
- **Built-in Mock Facilitator**: Ships with an in-app facilitator router (`/facilitator/verify`, `/facilitator/settle`) for 100% offline local testing and CI/CD before switching to PayAI mainnet.

---

## 📁 Project Structure

```
x402-microservice/
├── config.py              # Configuration & environment parser (.env fallback)
├── security.py            # SSRF protection validator (DNS resolution + IP bounds)
├── service.py             # HTML to clean Markdown extraction core & schemas
├── x402_mw.py             # HTTP 402 verification & settlement middleware
├── mock_facilitator.py    # Local facilitator simulator (EIP-3009 verification & settlement)
├── telemetry.py           # Machine-verifiable usage.jsonl telemetry store
├── main.py                # FastAPI entry point & route registration
├── client_agent_demo.py   # Complete end-to-end autonomous buyer agent demo
├── test_suite.py          # Pytest test suite (health, 402, paid ok, ssrf block)
├── requirements.txt       # Dependencies
├── .env.example           # Environment template
└── README.md              # Documentation
```

---

## 🚀 Quick Start

### 1. Requirements & Installation

```bash
cd /home/aether/projects/x402-microservice
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Key environment variables:
| Variable | Description | Default |
|---|---|---|
| `PORT` | Service listening port | `8024` |
| `X402_NETWORK` | x402 V1 network string | `base` |
| `X402_USDC` | Base USDC contract address | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| `X402_USDC_NAME` | EIP-712 token domain name | `USD Coin` |
| `X402_WALLET` | Seller recipient address (`payTo`) | `0xd477...` |
| `X402_PRICE_ATOMIC` | Atomic units per call ($0.005 = 5000) | `5000` |
| `X402_FACILITATOR_URL` | Facilitator endpoint | `https://facilitator.payai.network` |
| `MOCK_FACILITATOR_ENABLED` | Mount local facilitator for tests | `true` |

### 3. Run Test Suite

```bash
python3 -m pytest test_suite.py
```

### 4. Run the Service

```bash
python3 main.py
```

The server will start at `http://0.0.0.0:8024`.

---

## 🤖 Autonomous Agent Integration

### Discovery
Autonomous agents probe the standard MCP server card:
```bash
curl -s http://127.0.0.1:8024/.well-known/mcp/server-card.json | jq .
```

### Request Flow
1. **Unpaid Request:**
```bash
curl -i -X POST http://127.0.0.1:8024/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"html": "<h1>Test Document</h1><p>Sample text</p>"}'
```
Response: `HTTP/1.1 402 Payment Required` with headers:
- `Paywall: x402`
- `Accept: application/x402-payment-v1+json`

And body:
```json
{
  "x402Version": 1,
  "scheme": "exact",
  "network": "base",
  "maxAmountRequired": "5000",
  "resource": {
    "url": "http://127.0.0.1:8024/v1/extract",
    "description": "Clean Webpage Markdown Sanitization API for Autonomous Agents",
    "serviceName": "Web2Markdown Sanitizer"
  },
  "payTo": "0xd477295C0Fe6Be96CaDd3d5B6B3eB82B16eADa98",
  "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  "extra": {
    "name": "USD Coin",
    "version": "2"
  }
}
```

2. **Run the Autonomous Buyer Agent Demo:**
```bash
python3 client_agent_demo.py
```
This script executes the complete cycle:
- Fetches discovery card
- Probes `/v1/extract` to receive 402
- Signs EIP-3009 typed data using local private key
- Retries with `X-PAYMENT` header
- Verifies successful extraction output & table telemetry
- Queries `/telemetry`

---

## 🛡️ Security & Operational Best Practices

1. **SSRF Gate**: Private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, link-local `169.254.0.0/16`) are blocked deterministically.
2. **Deterministic Errors**: No bare `HTTP 500`. Errors return actionable JSON containing `error`, `retryable` (bool), and `action` hints.
3. **Telemetry**: Empirical telemetry is stored in `usage.jsonl` and exposed at `/telemetry`.
