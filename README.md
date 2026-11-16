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
- **entity** (email, phone, amount, date, id, name, text) – candidate discovery finds literal values in the transcript, the model picks one with a Choice question (plus `none`), and code normalizes the verbatim value. Text entities use transcript phrases by default, or an optional regex whose first capture group is the value. The model never generates entity text.

## Transcript formats
`{turns|segments|messages:[{speaker,text,start}]}`, AssemblyAI `utterances`, Deepgram `results.utterances`/`channels`, Azure batch `recognizedPhrases`, Azure fast transcription `phrases` (with `offsetMilliseconds`, `durationMilliseconds` and optional `speaker`), or plain `{text}`. Azure `combinedPhrases` is supported as a fallback when individual phrases are absent. Same-speaker segments are merged and turns are numbered. Numeric speaker IDs are preserved, not assumed to identify the agent or customer; label speakers `agent`/`customer` for best results.

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

## v2: Microsoft Decision-1 (Foundry)

Pick **Microsoft Decision-1** in the header, then enter your Foundry resource endpoint (`https://<resource>.services.ai.azure.com`), the **deployment name** (used as `model`) and the resource API key (sent as the `api-key` header). Only Azure resource hosts are accepted. Calls go to `<endpoint>/providers/microsoft/v1/systemone`. Confidence falls back to the top option probability when the model returns none. Decision support only: do not use as the sole basis for credit or other consequential decisions about people.

### Generate fields from a use case

Click **Generate from use case** in the Fields panel and describe your scenario. With an Azure chat deployment (e.g. gpt-4o on the same Foundry resource, entered as *Chat deployment*; API-key auth only) fields are generated with a strict JSON schema, validated server-side, and shown for review before you Replace or Append. Invalid fields are skipped with reasons. Without a chat deployment (or on Jev), the closest curated starter templates (`backend/templates/library.json`) are suggested. The generator avoids eligibility, fraud, hiring-suitability and triage style fields.

### Example scenarios

The gallery above the workspace offers ready-made voice scenarios (retail banking, insurance claims, patient access, health-plan member services, airline and travel, travel concierge, AI tutor, recruiting, and loan entity extraction). Click one to load its fields and a sample call, then edit. Definitions live in `backend/templates/scenarios.json` and `backend/templates/loan_extraction.json`; each field is explicit-evidence based and satisfaction is captured as a choice of what the customer explicitly said. Scenarios in sensitive domains are operational analytics only.

### Loan entity extraction

Select **Loan call entity extraction**, replace the sample transcript with your transcript JSON, and click **Run analysis**. Results include the existing field cards and downloadable nested JSON with greeting checks, customer details, current/permanent addresses and loan terms. No chat deployment is required. The sample uses fictional data.

Fields carry an `output_path` (one or two JSON keys) and optional `output_type: "number"` so the schema survives saved presets and field imports. Missing values become empty strings; loan amount, EMI, installment count and processing fee are JSON numbers when found. DOB and other string fields retain the selected transcript wording. The model selects among at most 50 literal candidates per field; unfamiliar wording, spoken-out numbers and long transcripts can leave values missing. Inspect candidates and review flags before using the output. This is extraction of stated facts, not financial advice or a credit decision.

Hindi transcripts retain their original script. Candidate discovery recognizes Hindi sentence boundaries, common name cues and loan durations such as `36 महीने`; currency amounts written with digits and `₹` are supported. It does not translate or repair noisy STT, infer missing identity details, or guarantee recognition of numbers spelled out as words.

### Bharosa Bank Loan Sales

Select **Bharosa Bank Loan Sales** for the full outbound-sales schema: greetings,
identity checks, customer details, both residences, loan terms, customer questions,
expressed sentiment, insurance and repayment options, bureau consent, documents and
manager appointment. The scenario loads a fictional English call and exposes
**Sample expected JSON** beneath its description. This is a reference example,
not a recorded model result or actual bank product terms.

The sample uses `{"language": "en-IN", "direction": "outbound", "turns": [{"speaker": "Speaker 2", "text": "..."}, {"speaker": "Speaker 1", "text": "..."}]}`.
Each speaker segment is a separate turn for readability. Input also supports a
`text` field with one `Speaker N: text` segment per line. Speaker numbers are preserved;
the questions instruct the model to infer roles from the conversation, with the
existing role-label warning retained. Speaker 1 is the customer in this example.

`source_field` derives a field from an earlier selected entity without asking the
model to extract it again. `output_transform` handles day-first DOB formatting,
last-four-character PAN output (`APKPP6076L` becomes `076L`), numeric scaling,
tenure in months and percent formatting. Numeric fields use `output_default: null`;
string fields default to `""`. `Loan.Rate` remains a percent string such as `"18%"`.
Salary and turnover retain the stated period; the requested output schema has no
separate period field. Numeric characters mean decimal digits `0-9`, not Roman
numerals. Insurance and repayment details preserve the selected wording.
Blank choice values are sent as non-empty API labels such as `not_mentioned` and
mapped back to `""` in results, preserving the output schema without invalid API
option names. Existing saved field definitions with blank options are supported.

This scenario is English-first: already-English/Roman text is reused for the
corresponding normalized fields. Non-ASCII translation or transliteration is not
implemented; original extracted text is preserved, the derived field is empty and
explicitly flagged for review. Digit-written Unicode numbers are supported by
output conversion; spelling out numbers or IDs is not guaranteed to match a
candidate. This is extraction of stated information, not financial advice, truth
verification or a credit decision.
