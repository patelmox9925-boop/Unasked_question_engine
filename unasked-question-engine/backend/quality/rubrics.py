"""Planted-issue rubrics.

Each issue lists *alternatives*; an issue counts as found when a finding's title/explanation/question contains
ALL words of at least one alternative. Keep alternatives short and distinctive so keyword luck is unlikely.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CASES_DIR = Path(__file__).parent / "cases"
DEMO_SAMPLE_DIR = Path(__file__).resolve().parents[1] / "app" / "demo" / "sample"


@dataclass(frozen=True)
class PlantedIssue:
    key: str
    description: str
    alternatives: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Case:
    name: str
    files: tuple[Path, ...]
    issues: tuple[PlantedIssue, ...]


HARVEST_BOX = Case(
    name="harvest_box",
    files=(DEMO_SAMPLE_DIR / "harvest_box_plan.md", DEMO_SAMPLE_DIR / "harvest_box_orders.csv"),
    issues=(
        PlantedIssue("card_storage", "Card details stored in the project's own database",
                     (("card", "database"), ("card", "stored"), ("payment", "stored"))),
        PlantedIssue("sync_vs_promise", "Nightly CSV sync cannot meet the 24-hour delivery promise",
                     (("nightly", "24"), ("sync", "24-hour"), ("csv", "24"))),
        PlantedIssue("shared_password", "Staff share one admin password in a spreadsheet",
                     (("shared", "password"),)),
        PlantedIssue("data_quality", "Duplicate, missing, negative and extreme order values",
                     (("duplicate",), ("negative",), ("18,000",), ("18000",), ("outlier",))),
        PlantedIssue("hosting_vs_growth", "500 dollar hosting cap vs 20,000 subscriber target",
                     (("500", "20,000"), ("hosting", "subscribers"), ("budget", "growth"))),
        PlantedIssue("integration_capacity", "Unfinished warehouse integration, two engineers, fixed date",
                     (("integration", "engineers"), ("integration", "estimate"), ("integration", "launch"))),
        PlantedIssue("allergy_data", "Allergy data collected without a handling plan",
                     (("allergy",), ("allergen",))),
        PlantedIssue("support_owner", "Founders handle support with no hours defined",
                     (("support", "founders"), ("support", "hours"))),
    ),
)

CLINICBOOK = Case(
    name="clinicbook",
    files=(CASES_DIR / "clinicbook.md",),
    issues=(
        PlantedIssue("big_bang", "All 12 clinics go live on the same day with one contractor",
                     (("12", "same"), ("all", "clinics", "go-live"), ("pilot",), ("phased",), ("big-bang",))),
        PlantedIssue("import_day_before", "Calendar import happens only the day before go-live",
                     (("import", "day before"), ("import", "migration"), ("calendar", "import"))),
        PlantedIssue("no_show_goal_metric", "60 percent call reduction has no baseline or measurement",
                     (("60", "baseline"), ("60 percent", "measure"), ("phone calls", "baseline"), ("reduction", "measure"))),
        PlantedIssue("sms_volume", "About 4,800 SMS a day: cost, provider limits and opt-out are not covered",
                     (("sms", "cost"), ("sms", "opt"), ("sms", "limit"), ("sms", "volume"))),
        PlantedIssue("cancel_contradiction", "Online cancellation at any time vs phone confirmation of each one",
                     (("cancel", "confirm"), ("cancellation", "phone"))),
        PlantedIssue("patient_data", "Patient data stored with no consent, retention or access plan",
                     (("patient", "consent"), ("patient", "retention"), ("patient data",), ("privacy",))),
        PlantedIssue("support_staff", "Reception staff become the support team with no training or tools",
                     (("reception", "support"), ("reception", "training"))),
        PlantedIssue("single_contractor", "A single contractor is a single point of failure after launch",
                     (("contractor", "maintenance"), ("contractor", "after"), ("single", "contractor"), ("one contractor",))),
    ),
)

CASES: tuple[Case, ...] = (HARVEST_BOX, CLINICBOOK)
