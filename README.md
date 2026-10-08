# Post-call analytics (Jev / TypeSafe)

Paste an STT transcript JSON, define analytics fields, and get structured results from Jev in one API call.

## Run
```powershell
# backend (http://127.0.0.1:8000)
cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn main:app --port 8000

# frontend (http://localhost:5173, proxies /api to the backend)
cd frontend; npm install; npm run dev
```
Paste your TypeSafe API key in the header (kept in memory, sent per request, never stored or logged). Tests: `cd backend; .\.venv\Scripts\python -m pytest`.

## Field types
- **noul** – yes/no probability; flagged if inside the uncertain band.
- **choice** – one option from a set; flagged if confidence is below threshold.
- **score** – ordered rubric levels; flagged if confidence is below threshold.
- **entity** (email, phone, amount, date) – a regex finds candidates in the transcript, Jev picks one with a Choice question (plus `none`), and code normalizes the verbatim value. Jev never generates text, so values cannot be invented.

## Transcript formats
`{turns|segments|messages:[{speaker,text,start}]}`, AssemblyAI `utterances`, Deepgram `results.utterances`/`channels`, Azure `recognizedPhrases`, or plain `{text}`. Same-speaker segments are merged and turns are numbered. Label speakers `agent`/`customer` for best results.

## Deploy (GitHub Pages frontend + hosted backend)
Pages is static, and Jev's API doesn't allow direct browser calls, so the backend must be hosted.
1. Push this folder to a GitHub repo (branch `main`).
2. Backend: create a Render web service from the repo (uses `render.yaml`/`backend/Dockerfile`). Set `ALLOWED_ORIGINS=https://<user>.github.io`. Note the service URL.
3. Repo → Settings → Secrets and variables → Actions → Variables: add `API_BASE` = the Render URL.
4. Repo → Settings → Pages → Source: GitHub Actions. Push to `main` to deploy at `https://<user>.github.io/<repo>/`.
Users paste their own TypeSafe key; the backend only forwards it. Free Render instances sleep when idle, so the first request is slow.

## Notes
- Prebuilt sales template: "Load sales template". Presets live in browser localStorage.
- Phones without a country code are returned as digits only (no E.164 `+`).
- Calls over ~64k tokens are warned about, not chunked.
