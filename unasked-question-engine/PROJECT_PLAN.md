# PROJECT PLAN — The Unasked Question Engine

> Source of truth for progress. Read this file first in every session instead of re-reading the chat.
> Update the checkboxes and the Status Log immediately after finishing any task.

## Goal
Working, demo-ready web app that analyzes project documents/descriptions and surfaces missing assumptions, overlooked constraints, risks, dependencies, contradictions and unasked questions. Findings are ranked by impact, likelihood and urgency, backed by real evidence from the inputs, with follow-up chat and Markdown/PDF export.

## Current State (read this first)
- **Completed: all phases 0–11 (v1).** v2 requested (2026-10-17): providers Gemini + Groq + DeepSeek (OpenAI and Anthropic removed), more interactive UI, better answers. **v2 Phases 12–17 are planned below, awaiting the go-ahead. No v2 code written yet.**
- Project root: `/home/claude/unasked-question-engine/` (`backend/`, `frontend/`, venv in `.venv/`, `README.md`, `run.sh`).
- Backend tests: `cd backend && . ../.venv/bin/activate && python -m pytest -q` → **170 passing**.
- Frontend tests: `cd frontend && npm test` → **33 passing**. Type-check + build: `npm run build` (output in `frontend/dist`).
- Run everything on one port: `./run.sh` (or build the frontend, then `cd backend && uvicorn app.main:app --port 8000`; FastAPI serves `frontend/dist` at `/`). Dev mode: backend on 8000 plus `cd frontend && npm run dev` (Vite on 5173 proxies `/api`).
- Demo mode: `POST /api/demo` (button "Try the sample project" on the landing page and in the workspace when no model is configured) creates a project from `backend/app/demo/sample/` with predefined results (`origin="demo"`), no keys needed.
- Export: `GET /api/projects/{id}/export.md|pdf` (409 `no_analysis` if nothing analysed yet). Demo reports carry a DEMO DATA banner and say no model was consulted.

## Key Decisions (update as they change)
- Stack (confirmed in Phase 0, repo was empty/greenfield): Python 3.13 + FastAPI backend, React 19 + Vite + TypeScript frontend (plain CSS, no UI framework), in-memory project store (no DB).
- LLM providers: 3 pluggable modules behind one interface, configured via env vars (provider + model per role).
  - Model A: initial analysis and finding extraction (**required** for live analysis)
  - Model B: independent critique, missing-question discovery, counterarguments (optional)
  - Model C: evidence validation, dedup, prioritization, final synthesis (optional)
- Providers implemented: `openai` (Chat Completions, also OpenAI-compatible gateways), `anthropic` (Messages API), `gemini` (generateContent). Any of the three can be assigned to any role. Model IDs are never hardcoded; they come from `LLM_{A,B,C}_MODEL`.
- Pipeline call budget: A once; B once if configured; C once if configured and there is something to synthesise. Plus at most one schema-repair call per role. If B/C are unconfigured or fail, the result says so in `warnings` and falls back to deterministic merge/evidence checks (never silently).
- Evidence design: models cite only `chunk_id` (+ optional quote). Backend resolves the real source location from its own chunk records (`extraction/evidence.py`). Unknown chunk ids are dropped; quotes not found verbatim in the chunk are not shown as quotes (`quote_verified=False`).
- Status reconciliation (`analysis/merge.py`): a finding can never claim more certainty than its evidence. `verified_fact` without a verified quote is downgraded to `reasonable_inference`; non-absence findings with no evidence become `unverified_hypothesis`; absence-type findings (missing assumption/information/dependency, unasked question) with no evidence stay inferences and are labelled "potential gap, not a confirmed mistake".
- Prioritization (`analysis/prioritization.py`): `score = impact × likelihood × (0.80 + 0.02 × urgency)` (≈1–100); levels critical ≥ 60, high ≥ 36, medium ≥ 16, else low; overall risk = highest level present. The formula and "scores are model judgements" disclaimer are shown in the UI and in every finding's `score_explanation`.
- Chat: role preference C → A → B (first configured). Small projects (≤ 15k chars) are sent whole; larger ones use BM25 top-6 chunks, falling back to the opening sections when nothing matches. Citations are verified; ungrounded "grounded" claims are downgraded to "partly_grounded".
- UI design: restrained SaaS look; serif (system stack) for headings and the "unasked question" callouts, system sans for UI; navy primary, amber marker colour reserved for the unanswered questions; severity shown with a coloured spine plus text (never colour alone). No external fonts or CDNs.
- Demo mode (Phase 9) uses clearly labeled predefined sample results (`origin="demo"`), never presented as live analysis.
- Never invent evidence, quotes, metrics or source locations. Never claim a model was consulted if its call failed (router only returns a result after a schema-valid response; every attempt is recorded; failed models appear as "failed, not consulted").

## Code Map
### backend/app
| Module | Purpose |
|---|---|
| `config.py` | Settings from env/.env; role routing config; `public_status()` never exposes keys |
| `security.py`, `logging_setup.py` | Secret redaction for logs/errors |
| `schemas.py` | LLM output models (strict, `extra=forbid`): `RawFinding`, `AnalysisOutput` (A), `CritiqueOutput` (B), `SynthesisOutput` (C), `ChatOutput`; domain models `Finding`, `Evidence`, `AnalysisResult`, `RiskSummary`, `AnalysisStatus`; API models |
| `extraction/parsers.py` | TXT, MD (heading paths + line numbers), CSV (profile chunk + row ranges), PDF (pages), DOCX (headings, tables) |
| `extraction/chunking.py`, `retrieval.py` | Paragraph-aware chunking; BM25 `EvidenceIndex`; `verify_excerpt` |
| `extraction/evidence.py` | `resolve_citation` → real `Evidence` |
| `extraction/untrusted.py` | Injection flagging, `format_untrusted_context`, `UNTRUSTED_DATA_RULES` |
| `providers/base.py` | `LLMProvider` interface, retries, 429/Retry-After, timeouts, error mapping |
| `providers/{openai,anthropic,gemini}_provider.py` | Provider-specific request/response code only |
| `providers/router.py` | `LLMRouter.run(role, request, OutputModel)`: fallback + one schema-repair attempt; `AllProvidersFailed` |
| `providers/validation.py` | `parse_model_output` strict JSON + schema validation |
| `providers/mock.py` | Scripted provider for tests only (not registered; cannot be chosen via env) |
| `analysis/perspectives.py` | Adaptive perspective selection from keyword evidence (technical + requirements always; others only if the material mentions them; data quality if a CSV is present) |
| `analysis/context.py` | Size-bounded, relevance-ranked chunk selection (60k chars) |
| `analysis/prompts.py` | Role A/B/C prompts (documents only inside delimited untrusted blocks) |
| `analysis/merge.py` | Citation resolution, status reconciliation, dedupe, disagreement notes |
| `analysis/prioritization.py` | Scoring, levels, `build_risk_summary` |
| `analysis/pipeline.py` | `AnalysisPipeline.run` (A → B → C → prioritize), `AnalysisFailed` |
| `analysis/jobs.py` | Background `JobManager` with per-step progress for the UI |
| `analysis/chat.py` | Grounded follow-up Q&A |
| `api/routes.py` | `GET /api/health`, `GET /api/config/status`, `POST /api/projects` (multipart `description`, `files`), `GET /api/projects/{id}`, `GET /api/projects/{id}/chunks/{chunk_id}` |
| `api/analysis_routes.py` | `POST /api/projects/{id}/analyze` (202), `GET /api/projects/{id}/analysis`, `POST /api/projects/{id}/chat` |
| `api/routes.py` (also) | `POST /api/demo` creates the sample project with demo results |
| `api/analysis_routes.py` (also) | `GET /api/projects/{id}/export.md` and `export.pdf` |
| `reports/` | `markdown_report.py` (HTML/images neutralised), `pdf_report.py` (reportlab + bundled Vera font; unsupported glyphs become `?`), `common.py` (labels, demo notice) |
| `demo/` | `data.py` (sample loader + hand-written findings whose quotes are resolved and verified by the real evidence code), `sample/harvest_box_plan.md`, `sample/harvest_box_orders.csv` |
| `store.py` | In-memory `ProjectStore` (`Project.chunks`, `.chunk_map()`, `.analysis`) |
| `main.py` | `create_app(settings, llm_router, serve_frontend)`; serves `frontend/dist` if built |

### frontend/src
| Path | Purpose |
|---|---|
| `App.tsx` | View state machine (landing → workspace → analyzing → results), polling |
| `api.ts`, `types.ts` | Typed API client (incl. `downloadReport`), shared types |
| `components/Landing, Workspace, ProgressView, ResultsView` | Pages. `ResultsView` holds summary band, tabs (Findings / Unanswered questions / Ask a follow-up), export bar |
| `components/FindingCard, EvidenceList, Filters, ChatPanel, ExportBar, Markdown, Header` | Building blocks. `Markdown` = react-markdown + rehype-sanitize, no raw HTML, no images |
| `lib/filters.ts`, `lib/format.ts` | Pure filter/sort logic, labels, client-side file validation |
| `test/*` | Vitest + Testing Library (logic, components, full app flow with mocked fetch) |

---

## Status Legend
`[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked

---

## Phase 0 — Repository Inspection and Setup  ✅
- [x] Inspect existing repo: framework, structure, existing functionality (empty workspace; greenfield)
- [x] Confirm/adjust stack decision (FastAPI + React/Vite confirmed)
- [x] Create folder structure, `.gitignore`, `.env.example` (placeholders only)
- [x] Record assumptions in this file

## Phase 1 — Backend Foundation  ✅
- [x] App skeleton, config loader (env vars), logging without secrets
- [x] Pydantic schemas: Finding, Evidence, AnalysisResult, requests/responses
- [x] File upload endpoint: size limits, type validation, safe temp-file handling
- [x] Health and config-status endpoints (never expose keys)

## Phase 2 — Document Extraction and Evidence Store  ✅
- [x] Parsers: TXT, Markdown, CSV, PDF (page numbers), DOCX (headings)
- [x] Preserve source refs: filename, page, heading, row number
- [x] Chunking for large docs/datasets with source metadata
- [x] Clear errors for extraction failures and unsupported types
- [x] Prompt-injection guard: documents treated as untrusted data
- [x] Evidence retrieval (relevant chunks per finding)

## Phase 3 — Multi-LLM Provider Layer  ✅
- [x] Shared provider interface + three separate provider modules
- [x] Per-task provider/model config (A, B, C) with fallbacks
- [x] Timeouts, retry limits, rate-limit handling, clear errors
- [x] Strict schema validation of all model outputs
- [x] Track which models were actually consulted (no false claims)
- [x] Mock providers for tests

## Phase 4 — Analysis Pipeline  ✅
- [x] Input → Extraction → Context Building
- [x] Adaptive perspective selection (technical, cost, security, scalability, dependencies, UX, operations, requirements, data quality)
- [x] Model A analysis, Model B critique, Model C validation/dedup/synthesis
- [x] Label each item: verified fact / reasonable inference / unverified hypothesis (reconciled against real evidence)
- [x] Merge duplicates, preserve model disagreements
- [x] Graceful failure when providers fail (no fabricated analysis)
- [x] Background job + progress steps API (`/analyze`, `/analysis`)

## Phase 5 — Prioritization Engine  ✅
- [x] Transparent formula using impact, likelihood, urgency, with brief score explanation
- [x] Priority levels and overall risk summary
- [x] Unit tests for scoring

## Phase 6 — Follow-up Chat (backend)  ✅
- [x] Grounded Q&A over the analysis and retrieved evidence
- [x] Refuses to invent evidence; says when unknown (`not_in_material`; unverifiable citations dropped and grounding downgraded)

## Phase 7 — Frontend UI  ✅
- [x] Landing page (with clearly labelled illustrative example)
- [x] Project input + file upload (drag/drop, client-side validation, limits from server config)
- [x] Progress indicator (per-step, live)
- [x] Results dashboard: risk summary, filters (category/severity/support/search/sort), expandable finding cards with evidence + actions
- [x] Unanswered questions section
- [x] Follow-up chat panel
- [x] Export controls (UI done; endpoints arrive in Phase 8)
- [x] Empty/loading/success/error states
- [x] Sanitized Markdown rendering, no raw JSON/asterisks
- [x] Responsive layout, accessibility (labels, tab roles + arrow keys, focus rings, aria-live, reduced motion), keyboard navigation

## Phase 8 — Export  ✅
- [x] Markdown report (`GET /api/projects/{id}/export.md`)
- [x] PDF report (`GET /api/projects/{id}/export.pdf`, reportlab, bundled font)
- [x] Report clearly marks demo vs real LLM findings; includes score formula, warnings, models consulted (incl. failed)
- [x] Tests for report generation (empty findings, special characters, demo origin, HTML/image neutralising, HTTP)
- [x] UI export bar works for real and demo results

## Phase 9 — Demo Mode and Sample Data  ✅
- [x] Realistic sample project ("Harvest Box" meal-kit launch) with hidden assumptions/risks/contradictions
- [x] Sample document (Markdown plan) + sample CSV dataset with planted data-quality problems
- [x] Demo mode with predefined results, clearly labeled "DEMO" (works with no API keys; entry points on landing and workspace)

## Phase 10 — Testing  ✅
- [x] Tests for parsing, schema validation, provider failures, config/redaction, upload API, empty/malformed/unsupported files, missing API keys, pipeline (all failure modes), prioritization, chat, frontend logic/components/flow
- [x] Report-generation tests and demo tests (`tests/test_reports.py`, `tests/test_demo.py`)
- [x] End-to-end run in demo mode (headless Chromium, no keys): sample → results → evidence → Markdown and PDF downloads → mobile 390px without overflow, no console errors

## Phase 11 — Documentation and Final Verification  ✅
- [x] README: setup, config, architecture, run commands, assumptions, limitations; `run.sh`
- [x] Built and ran from a clean unzipped copy using the documented commands (see Status Log)
- [x] Walked through the final acceptance criteria below

## v2 — Phases 12–17 done
### Phase 12 — Providers: Gemini, Groq, DeepSeek
- [x] Remove OpenAI and Anthropic provider modules, config, tests, docs
- [x] Add Groq and DeepSeek modules (OpenAI-compatible chat APIs, JSON mode) on a shared OpenAI-compatible base
- [x] Provider-specific limits (context size, max tokens, rate limits) so smaller-context models get trimmed input
- [x] Default role suggestion: A = Gemini, B = Groq, C = DeepSeek (any provider still usable for any role)
### Phase 13 — In-app model setup
- [x] Settings panel: choose provider + model per role, paste key, "Test connection"
- [x] Saved to local `.env` on the server (local single-user use only); keys never returned to the browser
### Phase 14 — Better answers
- [x] Two-pass analysis (extract facts, then hunt gaps), domain checklists, sharper prompts with good/bad examples
- [x] Per-finding evidence retrieval and a specificity check (reject vague or generic findings)
- [x] Stronger synthesis: real merge, calibrated scores, "why nobody asked this"
- [x] Better chat: retrieval tuned per question, includes related findings, suggested follow-ups
- [x] Quality harness: sample projects with planted issues, recall measured per change
### Phase 15 — Interactive UI
- [x] Visual redesign + dark mode
- [x] Clickable risk matrix (impact × likelihood) that filters findings
- [x] Evidence side panel: open source passage with the quote highlighted
- [x] Triage findings: accept / dismiss / resolved + notes (included in export)
- [x] Live progress timeline, toasts, keyboard shortcuts, copy-question buttons, progressive-reveal chat (not true streaming)
### Phase 16 — Tests (done)
- [x] Backend + frontend tests updated for new providers, settings, triage, streaming
- [x] Browser e2e (demo + fake-model live path), mobile and keyboard checks
### Phase 17 — Docs and packaging (done)
- [x] README/.env.example for Gemini/Groq/DeepSeek, plan update, clean-copy verification, new zip

## Final Acceptance Criteria
- [x] Submit description or upload a supported document
- [x] Input extracted and analyzed (verified end to end with a local fake LLM; not with live provider APIs)
- [x] Meaningful overlooked questions and risks identified (prompt design + tests; quality with real models still to be judged on real keys)
- [x] Findings prioritized and supported by available evidence
- [x] Actionable recommendations
- [x] Three-provider architecture configurable (implemented and tested; not yet tested against live provider APIs)
- [x] Failed provider calls handled safely
- [x] UI shows readable structured results
- [x] Markdown and PDF export work
- [x] Demo mode runs without API keys
- [x] Project builds and runs with documented commands

---

## Assumptions Log
1. The workspace was empty, so this is a greenfield build in `unasked-question-engine/` (not in `/home/claude` itself, which only holds config dotfiles).
2. Python 3.13 and Node 22 are available; dependencies live in `.venv` (Python) and `frontend/node_modules`. The npm install pulled newer major versions than usual (Vite 8, Vitest 5, TypeScript 7, React 19); everything builds and tests pass with them.
3. No persistent database: projects and analyses are held in memory (max 50 projects, oldest evicted) and are lost on restart. Acceptable for a demo.
4. CSV row numbers are spreadsheet-style (header = first non-empty row).
5. OpenAI requests omit `temperature` (some models only accept the default) and use `max_completion_tokens` (override with `OPENAI_MAX_TOKENS_PARAM`).
6. The Anthropic Messages API has no JSON mode, so JSON is requested in the prompt and enforced by schema validation plus one repair retry.
7. Model A is the minimum for live analysis; B and C degrade gracefully with visible warnings.
8. Analysis is asynchronous (background task + polling every 1.2 s) so the UI can show progress. Jobs live in the server process only.
9. Perspective selection is deterministic keyword matching, not an LLM call (keeps cost down and is explainable: each perspective shows the terms that triggered it).

## Known Limitations
- Provider integrations (OpenAI, Anthropic, Gemini) are written against the public API shapes and tested with mocked transports and a local fake server, **not against the live APIs** (no keys were available). First real-key run may need small adjustments (e.g. model-specific parameters).
- The end-to-end browser run used a local fake LLM server (verification tooling, deliberately not part of the project) that returns schema-valid replies, some deliberately wrong (fabricated chunk id / quote) to exercise the evidence checks. It shows the plumbing and safeguards work; it says nothing about real model output quality.
- Scanned/image-only PDFs are rejected (no OCR). Password-protected PDFs are rejected.
- DOCX: headers/footers, text boxes and comments are not extracted.
- Prompt-injection defences are best-effort (flagging, delimiting, strict output schemas); they reduce but do not eliminate risk.
- In-memory store only; no auth or multi-user isolation (single-user demo). Restarting the server loses projects; a browser refresh returns to the landing page (no URL routing/session restore).
- Large material: only the most relevant ~60k characters go to the models; the UI warns when sections were omitted.
- Accessibility was built in (labels, roles, focus, keyboard, reduced motion) and unit-tested, but has not been audited with a dedicated tool (e.g. axe) or a screen reader.
- PDF report uses the bundled Vera font; characters it lacks (e.g. CJK) print as `?` (Markdown keeps them). XLSX input is not supported (use CSV).

## Status Log
| Date | Update |
|------|--------|
| 2026-10-17 | Plan created. No code written yet. Awaiting go-ahead to start Phase 0. |
| 2026-10-17 | Phases 0–3 implemented. 107 backend tests pass. Verified manually: server runs; `POST /api/projects` with real PDF/DOCX/CSV/TXT uploads works (injection text flagged, `.exe` rejected); provider layer verified over real HTTP against a local fake OpenAI-style server (429 retry then success; connection failure handled without leaking the key). |
| 2026-10-17 | Phases 4–7 implemented. 155 backend + 29 frontend tests pass; mutation-checked key safeguards (status downgrade, finding-id filtering, failed-model reporting, markdown image blocking, quote-verified label). Browser e2e (headless Chromium, real backend + built UI + local fake LLM): upload → live progress → results → expand evidence → questions → grounded chat → export-unavailable message; no horizontal overflow at 390px; fabricated citation was dropped and its finding downgraded to hypothesis. Found and fixed during e2e: chat retrieval gave the model no material for broad questions (now sends small projects whole, falls back to opening sections). Next: Phase 8 (export). |
| 2026-10-17 | Phases 8–10 implemented: Markdown/PDF export, demo mode with sample project, UI entry points. 170 backend + 33 frontend tests pass. Headless-Chromium demo e2e with no keys passed (downloads verified, DEMO labels present in both files, no console errors, no mobile overflow). |
| 2026-10-17 | Phase 11 done: README + `run.sh`. Final zip verified from a clean unzip: fresh venv + `pip install`, 170 backend tests, `npm ci` + 33 frontend tests + build, `./run.sh` served the app, and the no-keys demo e2e passed again (downloads, labels, no console errors). **Project complete.** Not verified: live provider APIs (no keys). |
| 2026-10-17 | v2 requested: Gemini/Groq/DeepSeek, interactive UI, better answers. Phases 12–17 planned; awaiting go-ahead. |

## Status Log (v2)
- Phases 12–15 complete: backend 218 tests, frontend 35 tests, build OK, browser e2e (demo, matrix filter, shortcuts, dark mode, Settings, mobile) clean.
- Phases 16–17 complete: clean unzipped copy installed from scratch; 219 + 35 tests pass, build OK, demo e2e OK. Final zip delivered.
- Honest limits: providers untested against live APIs; answer quality needs `python -m quality.run` with real keys.
