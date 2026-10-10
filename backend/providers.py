"""Provider-agnostic call layer for System One style decision APIs (Jev, Microsoft-Decision-1)."""
import asyncio
import re
from urllib.parse import quote, urlparse

import httpx

JEV_BASE = "https://api.typesafe.ai"
# Only Azure resource hosts are accepted for Microsoft calls, so the hosted backend cannot be used to reach arbitrary URLs
AZURE_HOST_SUFFIXES = (
    ".services.ai.azure.com",
    ".cognitiveservices.azure.com",
    ".openai.azure.com",
)


class DecisionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


_FRIENDLY = {
    400: "The request shape was rejected (check question types, criteria and state).",
    401: "Invalid, missing or expired API key / credential.",
    402: "Insufficient balance for this account.",
    403: "This credential has no access to the deployment.",
    404: "Endpoint or API path not found (check the resource endpoint).",
    422: "Request not supported (check the model/deployment name and question definitions).",
    429: "Rate limit reached; retry shortly.",
}


def validate_azure_endpoint(endpoint: str) -> str:
    """Return the normalized https://<host> origin or raise ValueError."""
    p = urlparse(endpoint.strip())
    host = (p.hostname or "").lower()
    if p.scheme != "https" or not host or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Endpoint must be an https URL such as https://<resource>.services.ai.azure.com")
    if not any(host.endswith(s) and len(host) > len(s) for s in AZURE_HOST_SUFFIXES):
        raise ValueError("Endpoint host must be an Azure resource (*.services.ai.azure.com, *.cognitiveservices.azure.com or *.openai.azure.com)")
    return f"https://{host}"


async def _post(url: str, headers: dict, body: dict, retries: int = 2) -> dict:
    last: DecisionError | None = None
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(retries + 1):
            try:
                resp = await client.post(url, json=body, headers=headers)
            except httpx.HTTPError as e:
                last = DecisionError(502, f"Could not reach the model endpoint: {type(e).__name__}")
            else:
                if resp.status_code == 200:
                    return resp.json()
                try:
                    j = resp.json()
                    detail = j.get("error") or j.get("detail") or resp.text[:300]
                except Exception:
                    detail = resp.text[:300]
                msg = _FRIENDLY.get(resp.status_code, f"Model endpoint error {resp.status_code}")
                if "DeploymentNotFound" in resp.text:
                    msg = "Deployment not found: the model field must be your Foundry deployment name (Foundry portal > Deployments), not the model name."
                last = DecisionError(resp.status_code, f"{msg} {detail}".strip())
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise last
            if attempt < retries:
                await asyncio.sleep(0.5 * (2**attempt))
    assert last is not None
    raise last


async def call_jev(api_key: str, body: dict) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    return await _post(f"{JEV_BASE}/v1/systemone", headers, body)


async def call_azure_chat(credential: str, endpoint: str, deployment: str, body: dict) -> dict:
    """Azure OpenAI-style chat completions (api-key auth only)."""
    origin = validate_azure_endpoint(endpoint)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", deployment or ""):
        raise ValueError("Chat deployment name may only contain letters, digits, '.', '_' and '-'")
    url = f"{origin}/openai/deployments/{quote(deployment, safe='')}/chat/completions?api-version=2024-10-21"
    return await _post(url, {"api-key": credential, "Content-Type": "application/json"}, body, retries=1)


async def call_microsoft(credential: str, body: dict, endpoint: str, auth: str = "api_key") -> dict:
    origin = validate_azure_endpoint(endpoint)
    headers = {"Content-Type": "application/json"}
    if auth == "bearer":
        headers["Authorization"] = f"Bearer {credential}"
    else:
        headers["api-key"] = credential
    return await _post(f"{origin}/providers/microsoft/v1/systemone", headers, body)
