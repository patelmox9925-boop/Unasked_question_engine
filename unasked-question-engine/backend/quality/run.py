"""Run the real pipeline on the planted-issue cases and print recall.

    python -m quality.run            # uses the models configured in .env (costs API calls)
    python -m quality.run --demo     # scores the predefined demo results (offline sanity check of the rubric)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

from app.analysis.pipeline import AnalysisFailed, AnalysisPipeline
from app.config import Settings
from app.extraction.parsers import parse_file
from app.providers.router import LLMRouter
from app.store import ProjectStore

from .rubrics import CASES, Case, HARVEST_BOX
from .scoring import CaseScore, score


def load_project(case: Case):
    docs = [parse_file(path, path.name, f"d{i}") for i, path in enumerate(case.files, 1)]
    return ProjectStore().create(docs, [], False)


async def run_case(router: LLMRouter, case: Case) -> CaseScore:
    project = load_project(case)
    result = await AnalysisPipeline(router).run(project)
    return score(case, result.findings)


def print_score(s: CaseScore) -> None:
    print(f"\n{s.case}: recall {len(s.found)}/{len(s.found) + len(s.missed)} ({s.recall:.0%}), "
          f"{s.total_findings} findings, {s.citation_rate:.0%} with model citations")
    if s.missed:
        print("  missed:", ", ".join(s.missed))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="score the predefined demo results instead of calling models")
    args = parser.parse_args()
    if args.demo:
        from app.demo.data import build_demo_result, load_sample_documents

        project = ProjectStore().create(load_sample_documents(), [], False)
        print_score(score(HARVEST_BOX, build_demo_result(project).findings))
        return 0
    settings = Settings()
    router = LLMRouter(settings)
    if not router.role_available("A"):
        print("Model A is not configured. Add keys in the app's Settings page or in .env first.")
        return 1
    scores: list[CaseScore] = []
    for case in CASES:
        try:
            scores.append(await run_case(router, case))
        except AnalysisFailed as exc:
            print(f"{case.name}: analysis failed: {exc.message}")
            return 2
        print_score(scores[-1])
    average = sum(s.recall for s in scores) / len(scores)
    print(f"\nAverage recall: {average:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
