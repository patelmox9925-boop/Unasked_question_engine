"""Follow-up questions, grounded in the uploaded project and its analysis."""

from __future__ import annotations

import json

from ..errors import ApiError
from ..extraction.models import Chunk
from ..extraction.untrusted import UNTRUSTED_DATA_RULES, format_untrusted_context
from ..extraction.retrieval import EvidenceIndex
from ..providers.base import LLMRequest
from ..providers.router import AllProvidersFailed, LLMRouter
from ..schemas import ChatMessage, ChatOutput, ChatResponse, ModelConsulted
from ..store import Project
from .merge import resolve_evidence

CHAT_ROLE_PREFERENCE = ("C", "A", "B")
TOP_CHUNKS = 6
MAX_FINDINGS_IN_PROMPT = 25
NO_ANALYSIS_NOTE = "No analysis has been run yet, so this answer uses only the uploaded material."


def pick_role(router: LLMRouter) -> str | None:
    return next((r for r in CHAT_ROLE_PREFERENCE if router.role_available(r)), None)


def _findings_block(project: Project) -> str:
    if project.analysis is None:
        return "[no analysis has been run yet]"
    rows = [
        {"id": f.id, "title": f.title, "category": f.category.value,
         "priority": f.priority_level.value if f.priority_level else None,
         "status": f.epistemic_status.value, "explanation": f.explanation[:400],
         "recommended_action": f.recommended_action[:300], "critical_question": f.critical_question}
        for f in project.analysis.findings[:MAX_FINDINGS_IN_PROMPT]
    ]
    return json.dumps(rows, ensure_ascii=False, indent=1)


def _history_block(history: list[ChatMessage]) -> str:
    if not history:
        return "[none]"
    return "\n".join(f"{m.role.upper()}: {m.content}" for m in history[-6:])


SMALL_MATERIAL_CHARS = 15000
FALLBACK_CHARS = 6000


def _query(question: str, history: list[ChatMessage]) -> str:
    """Short follow-ups ("and the cost?") only make sense with the earlier user turns."""
    earlier = [m.content for m in history if m.role == "user"][-2:]
    return " ".join([*earlier, question])


def select_passages(project: Project, question: str, history: list[ChatMessage] | None = None) -> list[Chunk]:
    """Small projects are sent whole; large ones by relevance, falling back to the opening sections.

    Broad questions ("what assumptions does the plan rely on?") share few keywords with the
    text, so pure keyword retrieval would leave the model blind to the project.
    """
    chunks = project.chunks
    if sum(len(c.text) for c in chunks) <= SMALL_MATERIAL_CHARS:
        return chunks
    hits = EvidenceIndex(chunks).search(_query(question, history or []), top_k=TOP_CHUNKS)
    if hits:
        return [h.chunk for h in hits]
    selected: list[Chunk] = []
    used = 0
    for chunk in chunks:
        if used + len(chunk.text) > FALLBACK_CHARS:
            break
        selected.append(chunk)
        used += len(chunk.text)
    return selected


def build_chat_request(project: Project, question: str, history: list[ChatMessage]) -> LLMRequest:
    selected = select_passages(project, question, history)
    passages = format_untrusted_context(selected, max_chars=20000) if selected else (
        "[the project has no readable material]")
    system = (
        "You answer follow-up questions about a project that was analysed by The Unasked Question "
        "Engine. Answer ONLY from the PROJECT PASSAGES and the ANALYSIS FINDINGS provided.\n"
        "- If the material does not contain the answer, say so plainly and set grounding to "
        "\"not_in_material\". You may add clearly-labelled general suggestions, but never present "
        "them as facts about this project.\n"
        "- Distinguish what the material states from what you infer.\n"
        "- Cite supporting passages in citations as {\"chunk_id\": \"...\", \"quote\": \"short exact quote or null\"} "
        "using only chunk_ids shown, and list relevant analysis finding ids in finding_ids.\n"
        "- grounding: \"grounded\" (fully supported by cited material), \"partly_grounded\", or \"not_in_material\".\n"
        "- answer is concise markdown. Lead with the direct answer in the first sentence. Then, where useful, "
        "separate what the material says (with the specific numbers, names and dates) from what it leaves open, "
        "and end with one concrete next step. Use a short list only when the content is a list. Do not give "
        "legal, financial or security conclusions; point to a qualified professional instead.\n"
        "- If the question depends on something the material does not say, name exactly what is missing and "
        "who could supply it, instead of guessing.\n"
        "- follow_ups: 2-3 short, specific questions the person should ask next, based on the gaps you saw "
        "(not generic).\n"
        "- Respond with a single JSON object only: "
        "{\"answer\": \"...\", \"citations\": [...], \"finding_ids\": [...], \"grounding\": \"...\", "
        "\"follow_ups\": [\"...\"]}\n\n"
        f"{UNTRUSTED_DATA_RULES}"
    )
    user = (
        f"ANALYSIS FINDINGS:\n{_findings_block(project)}\n\n"
        f"PROJECT PASSAGES (untrusted data):\n{passages}\n\n"
        f"CONVERSATION SO FAR:\n{_history_block(history)}\n\n"
        f"QUESTION: {question}"
    )
    return LLMRequest(system=system, user=user, temperature=0.2, max_tokens=3000)


async def answer_question(router: LLMRouter, project: Project, question: str,
                          history: list[ChatMessage]) -> ChatResponse:
    role = pick_role(router)
    if role is None:
        raise ApiError(409, "no_models_configured",
                       "No language model is configured, so follow-up questions are unavailable. "
                       "Click Models in the header and add an API key.")
    try:
        routed = await router.run(role, build_chat_request(project, question, history), ChatOutput)
    except AllProvidersFailed as exc:
        raise ApiError(502, "llm_unavailable", exc.message) from exc

    out = routed.data
    evidence = resolve_evidence(out.citations, project.chunk_map())
    known = {f.id for f in project.analysis.findings} if project.analysis else set()
    finding_ids = [fid for fid in dict.fromkeys(out.finding_ids) if fid in known]
    grounding = out.grounding
    warnings: list[str] = []
    if grounding == "grounded" and not evidence and not finding_ids:
        grounding = "partly_grounded"
        warnings.append("The model said this was grounded, but none of its citations could be verified "
                        "against the uploaded material, so it is shown as partly grounded.")
    if project.analysis is None:
        warnings.append(NO_ANALYSIS_NOTE)
    return ChatResponse(
        answer=out.answer, grounding=grounding, evidence=evidence, finding_ids=finding_ids,
        follow_ups=list(dict.fromkeys(out.follow_ups))[:3],
        model=ModelConsulted(role=routed.role, provider=routed.provider, model=routed.model,
                             succeeded=True, used_as_fallback=routed.used_fallback),
        warnings=warnings,
    )
