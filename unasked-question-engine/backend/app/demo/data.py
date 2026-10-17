"""Sample project and predefined demo results.

The sample documents go through the *real* extraction code, and each demo finding's evidence is resolved
and quote-checked by the *real* evidence code. Only the findings themselves are written by hand, and every
result is stamped ``origin="demo"`` so the UI and reports label it as sample data, never as AI output.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..analysis.merge import to_finding
from ..analysis.perspectives import select_perspectives
from ..analysis.prioritization import build_risk_summary, prioritize
from ..extraction.models import Chunk, ExtractedDocument
from ..extraction.parsers import parse_file
from ..schemas import (
    AnalysisResult,
    Category,
    EpistemicStatus,
    EvidenceCitation,
    ProjectFact,
    ProjectUnderstanding,
    RawFinding,
)
from ..analysis.merge import resolve_evidence
from ..store import Project

SAMPLE_DIR = Path(__file__).parent / "sample"
SAMPLE_FILES = ("harvest_box_plan.md", "harvest_box_orders.csv")
DEMO_WARNING = (
    "Demo data: these results were written in advance for the sample project and were not produced by an AI "
    "model. Configure a model (see the README) to analyse your own material."
)

PLAN_FILE, ORDERS_FILE = SAMPLE_FILES
C = Category
S = EpistemicStatus

# (file, exact quote) pairs are resolved to chunk ids at build time.
_SPECS: list[dict] = [
    dict(title="Card details are stored in the project's own database", category=C.RISK, perspective="security",
         explanation="The plan keeps card details in the company's own database so renewals are quick. That makes "
                     "the database a high-value target and brings payment-industry obligations that a two-person "
                     "engineering team may not be able to meet.",
         why_it_matters="A breach would expose customers' payment data and could end the business before it grows. "
                        "Hosted payment providers exist so that card numbers never touch your own systems.",
         quotes=[(PLAN_FILE, "card details are stored in our database so that renewals are quick")],
         status=S.VERIFIED_FACT, impact=10, likelihood=7, urgency=9,
         action="Use a hosted payment provider's tokens for renewals and never store card numbers. Ask a qualified "
                "payments or security adviser what obligations apply before launch.",
         question="Why do card details need to be stored at all when a payment provider can handle renewals?"),
    dict(title="Nightly warehouse sync conflicts with the 24-hour delivery promise", category=C.CONTRADICTION,
         perspective="requirements",
         explanation="Orders reach the warehouse only through a nightly CSV export, yet every order is promised "
                     "delivery within 24 hours. An order placed just after the export waits almost a full day "
                     "before the warehouse even sees it.",
         why_it_matters="The promise will be broken for a large share of orders, creating refunds, complaints "
                        "and support load from the first week.",
         quotes=[(PLAN_FILE, "Orders sync with a legacy warehouse system through a nightly CSV export. "
                         "The warehouse ships nationwide. Every order is promised delivery within 24 hours.")],
         status=S.REASONABLE_INFERENCE, impact=8, likelihood=8, urgency=8,
         action="Either move to near-real-time order transfer or change the promise (for example next-day delivery "
                "for orders before a cut-off time).",
         question="What is the latest order time that can still meet a 24-hour delivery promise?"),
    dict(title="Staff share one admin password kept in a spreadsheet", category=C.RISK, perspective="security",
         explanation="The admin console is protected by a single shared password stored in a team spreadsheet. "
                     "Anyone with the spreadsheet can act as any staff member, and nobody can be removed "
                     "without changing the password for everyone.",
         why_it_matters="There is no record of who changed what, and a leaver or leaked spreadsheet gives full "
                        "access to customer and order data.",
         quotes=[(PLAN_FILE, "Staff log in to the admin console with a shared password kept in the team spreadsheet.")],
         status=S.VERIFIED_FACT, impact=8, likelihood=7, urgency=7,
         action="Give each staff member their own account with multi-factor sign-in, and remove the spreadsheet "
                "password.",
         question="Who needs admin access, and how will access be removed when someone leaves?"),
    dict(title="Order data already has gaps, duplicates and impossible values", category=C.RISK,
         perspective="data_quality",
         explanation="The sample orders contain a repeated order (1006), a missing customer and a missing "
                     "amount, a negative amount and an 18,000 order that is far above the others, and one "
                     "order with no region.",
         why_it_matters="Revenue, delivery and refund figures built on this data will be wrong, and the "
                        "nightly warehouse export will inherit the same problems.",
         quotes=[(ORDERS_FILE, "Row 8: order_id=1006; customer=Fay Moss; amount=42.50; status=shipped; region=North"),
                 (ORDERS_FILE, "Column 'amount': 1 empty of 9")],
         status=S.VERIFIED_FACT, impact=6, likelihood=9, urgency=6,
         action="Add validation at order entry (required fields, unique ids, sensible amount ranges) and clean "
                "the existing rows before reporting on them.",
         question="Is order 1004 for 18,000 a real order or a typing mistake?"),
    dict(title="Hosting cap may not cover the growth target", category=C.MISSING_ASSUMPTION, perspective="cost",
         explanation="Hosting is capped at 500 dollars a month while the plan expects 20,000 subscribers within "
                     "six months. The plan never says what usage 500 dollars supports or what happens when "
                     "the cap is reached.",
         why_it_matters="Success could push costs past the cap, forcing a choice between a service slowdown and "
                        "an unplanned spend.",
         quotes=[(PLAN_FILE, "Hosting budget is capped at 500 dollars per month. We expect strong growth after launch, "
                         "with a target of 20,000 subscribers within six months.")],
         status=S.REASONABLE_INFERENCE, impact=7, likelihood=6, urgency=6,
         action="Estimate cost per subscriber and see how the 500 dollar cap compares at 1,000, 5,000 and 20,000 "
                "subscribers.",
         question="At how many subscribers does the 500 dollar cap stop being enough?"),
    dict(title="Two engineers must finish an unfinished integration before launch", category=C.OVERLOOKED_CONSTRAINT,
         perspective="technical",
         explanation="Launch is 15 March with two engineers, and the legacy warehouse integration is not done. "
                     "The plan gives no estimate for that integration, for testing it, or for the engineers' "
                     "other work.",
         why_it_matters="A slipped integration blocks fulfilment, which means launch cannot happen on the "
                        "announced date.",
         quotes=[(PLAN_FILE, "Public launch is 15 March. The warehouse integration will be finished before launch.")],
         status=S.REASONABLE_INFERENCE, impact=7, likelihood=6, urgency=7,
         action="Break the integration into tasks with estimates, and agree what can be cut or delayed if it runs "
                "late.",
         question="How many engineer-weeks does the warehouse integration need, and who else can review it?"),
    dict(title="Allergy and dietary data are collected without a handling plan", category=C.OVERLOOKED_CONSTRAINT,
         perspective="security",
         explanation="The plan collects dietary preferences and allergy information, which is sensitive personal "
                     "data. It does not say how long it is kept, who can see it, or what happens when a "
                     "customer's allergy information is wrong or out of date.",
         why_it_matters="Mishandling the data harms customers' privacy, and an incorrect allergy record could "
                        "lead to a harmful box being sent.",
         quotes=[(PLAN_FILE, "We will collect dietary preferences and allergy information to personalise each box.")],
         status=S.REASONABLE_INFERENCE, impact=8, likelihood=5, urgency=6,
         action="Decide what is collected, who sees it, how long it is kept and how customers correct it. Have a "
                "privacy specialist review the plan.",
         question="Who is responsible if an allergy preference is missed when a box is packed?"),
    dict(title="Customer support has no owner, hours or tooling", category=C.MISSING_DEPENDENCY,
         perspective="operations",
         explanation="Support is left to the founders with no defined hours. Subscription food delivery generates "
                     "late, missing and wrong-box issues that need quick answers.",
         why_it_matters="Founder time is also needed for launch work, so support will be slow just when the first "
                        "customers form their opinion of the service.",
         quotes=[(PLAN_FILE, "Customer support will be handled by the founders. No support hours have been defined.")],
         status=S.VERIFIED_FACT, impact=5, likelihood=7, urgency=5,
         action="Define support hours, a shared inbox and target reply times. Decide when a hire becomes necessary.",
         question="Who answers a customer whose box did not arrive on a Saturday?"),
    dict(title="The beta is a chance to test the delivery promise", category=C.OPPORTUNITY, perspective="operations",
         explanation="The beta opens six weeks before the public launch. It can be used to measure real order-to-"
                     "delivery times and to test the nightly sync before the promise is made public.",
         why_it_matters="Evidence from real orders turns a guess about delivery speed into a number the "
                        "business can promise.",
         quotes=[(PLAN_FILE, "Beta opens on 1 February.")],
         status=S.REASONABLE_INFERENCE, impact=5, likelihood=6, urgency=6,
         action="Record order and delivery times for every beta order and review them before launch.",
         question="What delivery time do beta customers actually experience?"),
    dict(title="Food-safety and labelling rules are not mentioned", category=C.MISSING_INFORMATION,
         perspective="requirements",
         explanation="Nothing in the material covers food-safety, cold-chain or allergen labelling rules for a "
                     "business that ships food nationwide. This is a gap in the material, not a statement about "
                     "what the rules are.",
         why_it_matters="If rules apply and are discovered late, launch could be delayed or boxes recalled.",
         quotes=[],
         status=S.REASONABLE_INFERENCE, impact=7, likelihood=5, urgency=5,
         action="Ask a food-safety adviser which rules apply to shipping meal kits and add them to the plan.",
         question="Which food-safety and labelling rules apply to shipping meal kits nationwide?"),
]

_WHY = {
    "Card details are stored in the project's own database":
        "Storing the card is the shortcut that makes renewals easy, so it is chosen early and the risk is "
        "noticed only when someone asks how payments are secured.",
    "Nightly warehouse sync conflicts with the 24-hour delivery promise":
        "The sales promise and the warehouse integration are written by different people in different sections, "
        "so nobody reads them side by side.",
    "Staff share one admin password kept in a spreadsheet":
        "A shared password works fine with three people, so it never feels urgent until someone leaves.",
    "Order data already has gaps, duplicates and impossible values":
        "Teams look at totals, not rows, so one 18,000 order or a repeated id hides inside the sums.",
    "Hosting cap may not cover the growth target":
        "Budget and growth target are set in separate conversations and never multiplied together.",
    "Two engineers must finish an unfinished integration before launch":
        "\"Before launch\" sounds like a plan, but without an estimate nobody can tell it is not one.",
    "Allergy and dietary data are collected without a handling plan":
        "Collecting preferences feels like a product feature, so its safety and privacy side is left to later.",
    "Customer support has no owner, hours or tooling":
        "Founders assume they will simply cope, and support effort is invisible until volume arrives.",
    "The beta is a chance to test the delivery promise":
        "Betas are treated as bug-hunting, not as the cheapest chance to measure a promise.",
    "Food-safety and labelling rules are not mentioned":
        "The plan is written like a software launch, and food-specific rules sit outside the team's usual checklist.",
}

_UNDERSTANDING_FACTS: list[tuple[str, str, str, str]] = [
    (PLAN_FILE, "kind:goal", "goal", "Harvest Box is a subscription meal-kit web app for busy households."),
    (PLAN_FILE, "We launch publicly in March with two engineers and one part-time designer.", "commitment",
     "Public launch in March with two engineers and one part-time designer."),
    (PLAN_FILE, "Hosting budget is capped at 500 dollars per month.", "number", "Hosting budget is capped at 500 dollars a month."),
    (PLAN_FILE, "with a target of 20,000 subscribers within six months", "number", "Target of 20,000 subscribers within six months."),
    (PLAN_FILE, "Orders sync with a legacy warehouse system through a nightly CSV export.", "dependency",
     "Orders reach the warehouse through a nightly CSV export."),
    (PLAN_FILE, "Every order is promised delivery within 24 hours.", "commitment", "Every order is promised delivery within 24 hours."),
    (PLAN_FILE, "Customer support will be handled by the founders.", "decision", "Customer support is handled by the founders."),
    (ORDERS_FILE, "Data rows: 9", "data", "The sample orders file has 9 data rows and 5 columns."),
]
UNDERSTANDING_SUMMARY = (
    "Harvest Box is a meal-kit subscription app launching in March with a small team, a fixed hosting budget "
    "and a promise of 24-hour delivery that relies on an unfinished warehouse integration."
)
UNDERSTANDING_OPEN_ITEMS = [
    "The warehouse integration is to be finished \"before launch\" but has no estimate.",
    "No support hours have been defined.",
]

UNANSWERED = [
    "Who is the intended customer, and how many orders per week are expected in the first month?",
    "What happens to an order if the nightly export fails?",
    "How will perishable boxes stay cold across a nationwide delivery area?",
    "What is the refund and replacement policy for late or wrong boxes?",
    "Who monitors the system at night and on weekends after launch?",
]

SUMMARY = (
    "Harvest Box's biggest blind spots are payment-data handling, a delivery promise the order flow cannot keep, "
    "and shared admin access. Cost, staffing and support assumptions are thin for the growth the plan expects."
)


def load_sample_documents() -> list[ExtractedDocument]:
    docs = []
    for index, name in enumerate(SAMPLE_FILES, 1):
        docs.append(parse_file(SAMPLE_DIR / name, name, f"d{index}"))
    return docs


def _find_chunk(chunks: list[Chunk], filename: str, quote: str) -> Chunk:
    for chunk in chunks:
        if chunk.source.filename == filename and quote in chunk.text:
            return chunk
    raise ValueError(f"Demo quote not found in {filename}: {quote!r}")


def build_demo_result(project: Project) -> AnalysisResult:
    chunks = project.chunks
    chunk_map = project.chunk_map()
    findings = []
    for spec in _SPECS:
        citations = [EvidenceCitation(chunk_id=_find_chunk(chunks, f, q).chunk_id, quote=q) for f, q in spec["quotes"]]
        raw = RawFinding(
            title=spec["title"], category=spec["category"], perspective=spec["perspective"],
            explanation=spec["explanation"], why_it_matters=spec["why_it_matters"], citations=citations,
            epistemic_status=spec["status"], impact=spec["impact"], likelihood=spec["likelihood"],
            urgency=spec["urgency"], recommended_action=spec["action"], critical_question=spec["question"],
            why_overlooked=_WHY[spec["title"]],
        )
        findings.append(to_finding(raw, chunk_map, raised_by=["demo"], origin="demo"))
    findings = prioritize(findings)
    for index, finding in enumerate(findings, 1):
        finding.id = f"f{index}"
    facts = []
    for filename, quote, kind, statement in _UNDERSTANDING_FACTS:
        if quote == "kind:goal":
            quote = "Harvest Box is a subscription meal-kit web app for busy households."
        chunk = _find_chunk(chunks, filename, quote)
        facts.append(ProjectFact(statement=statement, kind=kind, evidence=resolve_evidence(
            [EvidenceCitation(chunk_id=chunk.chunk_id, quote=quote)], chunk_map)))
    understanding = ProjectUnderstanding(summary=UNDERSTANDING_SUMMARY, facts=facts,
                                         open_items=list(UNDERSTANDING_OPEN_ITEMS))
    return AnalysisResult(
        project_id=project.project_id, origin="demo", understanding=understanding, created_at=datetime.now(timezone.utc), findings=findings,
        unanswered_questions=list(UNANSWERED), overall_summary=SUMMARY,
        risk_summary=build_risk_summary(findings),
        perspectives=[info for _, info in select_perspectives(chunks)],
        models_consulted=[], warnings=[DEMO_WARNING],
    )
