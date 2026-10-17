import pytest

from app.demo.data import build_demo_result, load_sample_documents
from app.schemas import Finding
from app.store import ProjectStore
from quality.rubrics import CASES, CLINICBOOK, HARVEST_BOX
from quality.run import load_project
from quality.scoring import score


def mk(title, explanation="", question="q", cited=False):
    return Finding(id="x", title=title, category="risk", explanation=explanation or title, why_it_matters="w",
                   epistemic_status="reasonable_inference", impact=5, likelihood=5, urgency=5,
                   recommended_action="a", critical_question=question,
                   evidence=[{"chunk_id": "c", "source_label": "s", "filename": "f", "excerpt": "x",
                              "quote_verified": True}] if cited else [])


def test_demo_results_cover_every_planted_issue_in_the_sample():
    project = ProjectStore().create(load_sample_documents(), [], False)
    s = score(HARVEST_BOX, build_demo_result(project).findings)
    assert s.missed == [] and s.recall == 1.0 and s.citation_rate > 0.8


def test_scoring_counts_found_and_missed_issues():
    findings = [mk("Staff share a password", "A shared password is used by all staff", cited=True),
                mk("Unrelated topic")]
    s = score(HARVEST_BOX, findings)
    assert s.found == ["shared_password"] and len(s.missed) == len(HARVEST_BOX.issues) - 1
    assert s.citation_rate == 0.5 and 0 < s.recall < 0.2


def test_all_alternatives_must_match_not_any_single_word():
    assert score(CLINICBOOK, [mk("SMS")]).found == []
    assert score(CLINICBOOK, [mk("SMS volume is large", "4,800 sms a day, no cost or opt-out plan")]).found == ["sms_volume"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_case_files_exist_and_parse_and_every_issue_has_alternatives(case):
    assert all(p.exists() for p in case.files)
    assert load_project(case).chunks
    assert all(issue.alternatives and all(alt for alt in issue.alternatives) for issue in case.issues)
