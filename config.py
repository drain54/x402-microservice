import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent

# Lightweight .env loader without external python-dotenv dependency
_env_file = BASE_DIR / ".env"
if _env_file.is_file():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

class Settings(BaseModel):
    PORT: int = int(os.getenv("PORT", "8024"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    # x402 Specification & Blockchain defaults (Base Mainnet)
    NETWORK: str = os.getenv("X402_NETWORK", "base")  # V1 string: "base" or "base-sepolia"
    USDC_ASSET: str = os.getenv("X402_USDC", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
    USDC_NAME: str = os.getenv("X402_USDC_NAME", "USD Coin")  # On-chain token name: "USD Coin" on mainnet, "USDC" on testnet
    PAY_TO: str = os.getenv("X402_WALLET", "0xd477295C0Fe6Be96CaDd3d5B6B3eB82B16eADa98")
    
    # Pricing: $0.005 USDC per call = 5,000 atomic units (USDC has 6 decimals)
    PRICE_ATOMIC: str = os.getenv("X402_PRICE_ATOMIC", "5000")
    
    # Facilitator URL (e.g. PayAI production or local mock)
    FACILITATOR_URL: str = os.getenv("X402_FACILITATOR_URL", "https://facilitator.payai.network")
    MOCK_FACILITATOR_ENABLED: bool = os.getenv("MOCK_FACILITATOR_ENABLED", "true").lower() in ("true", "1", "yes")

settings = Settings()
