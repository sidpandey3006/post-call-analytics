import asyncio

import httpx


class JevError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


_FRIENDLY = {
    401: "Invalid or missing TypeSafe API key.",
    402: "TypeSafe account has insufficient balance.",
    403: "TypeSafe API key is not permitted to call this endpoint.",
    422: "TypeSafe rejected the request (invalid state or questions).",
    429: "TypeSafe rate limit reached; retry shortly.",
}


async def call_jev(api_key: str, body: dict, base_url: str = "https://api.typesafe.ai", retries: int = 2) -> dict:
    url = base_url.rstrip("/") + "/v1/systemone"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last: JevError | None = None
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(retries + 1):
            try:
                resp = await client.post(url, json=body, headers=headers)
            except httpx.HTTPError as e:
                last = JevError(502, f"Could not reach TypeSafe: {type(e).__name__}")
            else:
                if resp.status_code == 200:
                    return resp.json()
                detail = ""
                try:
                    detail = resp.json().get("error") or resp.text[:300]
                except Exception:
                    detail = resp.text[:300]
                msg = _FRIENDLY.get(resp.status_code, f"TypeSafe error {resp.status_code}")
                last = JevError(resp.status_code, f"{msg} {detail}".strip())
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise last
            if attempt < retries:
                await asyncio.sleep(0.5 * (2**attempt))
    assert last is not None
    raise last
