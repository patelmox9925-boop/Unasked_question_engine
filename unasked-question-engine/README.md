# The Unasked Question Engine

Upload project documents (PDF, DOCX, TXT, Markdown, CSV) or describe a project, and the engine looks for what
is **assumed but never stated**: missing assumptions, overlooked constraints, risks, dependencies,
contradictions, missing information, unasked questions and opportunities. Every finding is ranked by impact,
likelihood and urgency, tied to evidence from your own material, and comes with a recommended action and the
question nobody has answered. You can ask follow-up questions and export a Markdown or PDF report.

It works with **no API keys** in demo mode (clearly labelled sample results), and with up to three
configurable LLM providers for real analysis.

## Quick start (demo mode, no keys)

Requirements: Python 3.11+ (developed on 3.13). Node 20+ is only needed to rebuild the UI or run its tests,
because the built UI is already included in `frontend/dist`.

```bash
python run.py             # Windows: run.bat or `py run.py`. macOS/Linux: ./run.sh (creates .venv, installs, starts the app)
# open http://localhost:8000 and press "Try the sample project"
```

Manual equivalent:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --port 8000
```

The sample project ("Harvest Box", a meal-kit launch plan plus an orders CSV) runs through the real file
reader. Its findings are **written in advance, not produced by an AI**, and every screen and report says so.
Nothing is sent anywhere.

## Real analysis: configure models

```bash
cp .env.example .env     # then edit .env (backend/.env also works)
```

The easiest way is the **Models** button in the app: paste a key for Gemini, Groq or DeepSeek, test it, pick which model plays each role and save (it writes `.env` for you). Or edit `.env` by hand: pick a provider (`gemini`, `groq` or `deepseek`), a model ID your account can use, and the matching key.
Model IDs are deliberately blank in `.env.example` because they change over time.

| Role | Job | Required |
|------|-----|----------|
| **A** | Initial analysis and finding extraction | **Yes** for live analysis |
| **B** | Independent critique, missed findings, extra questions | Optional |
| **C** | Evidence validation, de-duplication, final synthesis; also answers follow-up questions | Optional |

```env
LLM_A_PROVIDER=gemini
LLM_A_MODEL=<model id>
GEMINI_API_KEY=...
LLM_B_PROVIDER=groq
LLM_B_MODEL=<model id>
GROQ_API_KEY=...
LLM_C_PROVIDER=deepseek
LLM_C_MODEL=<model id>
DEEPSEEK_API_KEY=...
# optional per-role fallback if the primary provider fails:
# LLM_A_FALLBACK_PROVIDER=groq
# LLM_A_FALLBACK_MODEL=<model id>
```

The same provider can serve several roles. Keys are read only by the backend, are never sent to the browser,
and are redacted from logs and error messages. `GET /api/config/status` shows which roles are ready, never
key material. Other settings (upload limits, timeouts, retries, CORS) are documented in `.env.example`.

## What happens during an analysis

1. **Extract**: files are parsed on the server into passages with source locations (page, heading, line or
   CSV row range). CSVs also get a statistical profile (empty cells, ranges, distinct values).
2. **Perspectives**: relevant lenses are chosen from the material (cost, security, operations, data quality...).
3. **Model A** produces findings. **Model B** critiques them independently. **Model C** merges duplicates,
   checks evidence and writes the summary. Missing or failing B/C are reported on the results page, and the
   engine falls back to deterministic de-duplication. If A fails, no analysis is shown, and nothing is invented.
4. **Prioritise**: `score = impact x likelihood x (0.80 + 0.02 x urgency)`. Critical >= 60, high >= 36,
   medium >= 16, otherwise low. The inputs are model judgements and are labelled as such.

### Why you can trust the evidence

- Models cite passages by id only. The backend resolves the real location, drops ids that do not exist, and
  marks a quote **verified** only if it appears word for word in that passage.
- A finding that claims to be a "verified fact" without a verified quote is downgraded to an inference.
  Non-absence findings without evidence become "unverified hypothesis". Gaps ("X is not mentioned") are
  labelled as potential gaps.
- Uploaded text is treated as data. Text that looks like instructions to an AI is flagged, wrapped in
  randomly delimited blocks, and never followed. Model output must match a strict schema (one repair attempt).
- Chat answers cite passages and findings, with the same verification. Unverifiable "grounded" claims are
  downgraded to "partly grounded".

## Architecture

```
backend/app
  config.py, security.py      settings (SecretStr keys), secret redaction
  extraction/                 parsers, chunking, BM25 retrieval, prompt-injection flags
  providers/                  gemini / groq / deepseek behind one interface + router (retry, fallback, repair)
  analysis/                   perspectives, prompts, pipeline, merge, prioritisation, jobs, chat
  reports/                    Markdown and PDF (reportlab) builders
  demo/                       sample project + predefined, labelled results
  api/                        FastAPI routes
frontend/src                  React + Vite + TypeScript (plain CSS, no external fonts or CDNs)
```

API summary: `POST /api/projects` (multipart upload), `POST /api/demo`, `POST /api/projects/{id}/analyze`,
`GET /api/projects/{id}/analysis` (polled for progress), `POST /api/projects/{id}/chat`,
`GET /api/projects/{id}/export.md|pdf`, `GET /api/projects/{id}/chunks/{chunk_id}`, `GET /api/health`.
Interactive docs at `/docs` while the server runs.

## Development and tests

```bash
cd backend && . ../.venv/bin/activate && python -m pytest -q      # 219 tests
cd frontend && npm install && npm test                            # 35 tests
cd frontend && npm run build                                      # type-check + build into frontend/dist
# dev mode with hot reload: backend on :8000, then `npm run dev` (Vite on :5173 proxies /api)
```

Tests use a scripted mock provider, so they need no keys and no network.

## Assumptions

- A project is a small to medium set of documents (default limits: 10 files, 10 MB each, 20,000-character
  description). Larger inputs are rejected with a clear message rather than silently truncated.
- Material beyond the model context budget (about 60,000 characters) is not all sent; the results page says so.
- Projects live in server memory only (the latest 50) and disappear on restart. Nothing is written to disk.
- Scores and findings are judgements by AI models. The product gives risk flags for review, not legal,
  financial or security advice.

## Known limitations

- **The three provider integrations have not been tested against live APIs** (no keys were available while
  building). They are covered by unit tests against scripted responses and a fake OpenAI-compatible server. Expect
  to adjust model names for your account on first use (the Models page can list the models your key can see).
- No OCR: scanned PDFs without a text layer are rejected with an explanation.
- Spreadsheet files (XLSX) are not supported; export to CSV.
- The PDF report uses a bundled font. Characters outside it (for example CJK) print as `?`; the Markdown
  report keeps them.
- No accounts or persistence; one running analysis per project. Accessibility was built in (labels, focus
  states, keyboard use, reduced motion) but not audited with assistive technology.

## Troubleshooting start-up

| Symptom | Fix |
|---|---|
| `run.sh` does nothing / not found on Windows | Use `run.bat` or `py run.py` (Windows cannot run `.sh` files). |
| "Python 3.11 or newer is required" | Install a newer Python from python.org (tick "Add to PATH" on Windows). |
| "Port 8000 is already in use" | Close the other program, or start with `PORT=8001` (Windows: `set PORT=8001` first). |
| Dependency install fails | Check your internet connection, then run `python run.py --reinstall`. The full pip error is shown. |
| Page looks old after an update | Run `cd frontend && npm install && npm run build`, then hard-refresh (Ctrl+Shift+R). |
| "Could not reach the server" | The backend is not running. Start it (`python run.py` / `run.bat` / `./run.sh`), keep that window open and open **http://127.0.0.1:8000**. Do not open `index.html` as a file. With `npm run dev` (port 5173) the UI also tries the backend on port 8000 directly; for another port run `BACKEND_URL=http://127.0.0.1:8001 npm run dev`. |
| Models say "not configured" | Click **Models** in the app and add a key, or edit `.env` and restart. |

Manual start, if the launcher misbehaves: `python -m venv .venv`, activate it, `pip install -r backend/requirements.txt`, then `cd backend && python -m uvicorn app.main:app --port 8000`.
