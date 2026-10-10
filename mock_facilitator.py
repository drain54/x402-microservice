import time
import uuid
from typing import Dict, Any
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from config import settings

mock_router = APIRouter(prefix="/facilitator", tags=["Mock Facilitator"])

# In-memory store for settled nonces to prevent double spending
SETTLED_NONCES: Dict[str, float] = {}

class VerifyRequest(BaseModel):
    paymentPayload: Dict[str, Any]
    paymentRequirements: Dict[str, Any]

class SettleRequest(BaseModel):
    paymentPayload: Dict[str, Any]
    paymentRequirements: Dict[str, Any]

@mock_router.get("/supported")
async def mock_supported():
    """Returns supported networks and tokens like PayAI facilitator."""
    return {
        "x402Version": 1,
        "kinds": [
            {
                "scheme": "exact",
                "network": settings.NETWORK,
                "asset": settings.USDC_ASSET,
                "extra": {"name": settings.USDC_NAME, "version": "2"}
            }
        ]
    }

@mock_router.post("/verify")
async def mock_verify(req: VerifyRequest):
    """
    Simulates facilitator /verify endpoint.
    Checks payload structure, authorization fields, signature format, and network match.
    """
    payload = req.paymentPayload
    requirements = req.paymentRequirements

    # Validate top-level scheme & network
    if payload.get("scheme") != "exact":
        return {"isValid": False, "invalidReason": "unsupported_scheme"}
    if payload.get("network") != requirements.get("network"):
        return {"isValid": False, "invalidReason": "network_mismatch"}

    sub_payload = payload.get("payload", {})
    sig = sub_payload.get("signature", "")
    auth = sub_payload.get("authorization", {})

    if not sig or not sig.startswith("0x") or len(sig) < 130:
        return {"isValid": False, "invalidReason": "invalid_exact_evm_signature"}

    # Check recipient matches payTo
    if auth.get("to", "").lower() != requirements.get("payTo", "").lower():
        return {"isValid": False, "invalidReason": "payTo_address_mismatch"}

    # Check value meets maxAmountRequired
    auth_val = int(auth.get("value", 0))
    req_val = int(requirements.get("maxAmountRequired", 0))
    if auth_val < req_val:
        return {"isValid": False, "invalidReason": "insufficient_authorized_amount"}

    # Check valid time bounds
    now = int(time.time())
    valid_after = int(auth.get("validAfter", 0))
    valid_before = int(auth.get("validBefore", 0))
    if now < valid_after:
        return {"isValid": False, "invalidReason": "authorization_not_yet_valid"}
    if now > valid_before:
        return {"isValid": False, "invalidReason": "authorization_expired"}

    nonce = auth.get("nonce")
    if nonce in SETTLED_NONCES:
        return {"isValid": False, "invalidReason": "authorization_nonce_already_settled"}

    return {
        "isValid": True,
        "validReason": "signature_and_authorization_valid"
    }

@mock_router.post("/settle")
async def mock_settle(req: SettleRequest):
    """
    Simulates facilitator /settle endpoint.
    Returns transaction hash and records nonce.
    """
    verify_result = await mock_verify(VerifyRequest(paymentPayload=req.paymentPayload, paymentRequirements=req.paymentRequirements))
    if not verify_result["isValid"]:
        return {
            "success": False,
            "errorReason": verify_result["invalidReason"]
        }

    nonce = req.paymentPayload.get("payload", {}).get("authorization", {}).get("nonce")
    if nonce:
        SETTLED_NONCES[nonce] = time.time()

    fake_tx = f"0x{uuid.uuid4().hex}{uuid.uuid4().hex}"
    return {
        "success": True,
        "transactionHash": fake_tx,
        "network": req.paymentRequirements.get("network"),
        "settledAt": int(time.time())
    }
