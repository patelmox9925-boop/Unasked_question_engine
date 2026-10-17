"""Score a list of findings against a case's planted issues."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import Finding

from .rubrics import Case


@dataclass
class CaseScore:
    case: str
    found: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    total_findings: int = 0
    cited_findings: int = 0

    @property
    def recall(self) -> float:
        total = len(self.found) + len(self.missed)
        return len(self.found) / total if total else 0.0

    @property
    def citation_rate(self) -> float:
        return self.cited_findings / self.total_findings if self.total_findings else 0.0


def finding_text(f: Finding) -> str:
    return " ".join([f.title, f.explanation, f.why_it_matters, f.critical_question]).lower()


def score(case: Case, findings: list[Finding]) -> CaseScore:
    texts = [finding_text(f) for f in findings]
    result = CaseScore(case.name, total_findings=len(findings),
                       cited_findings=sum(1 for f in findings if any(e.kind == "cited" for e in f.evidence)))
    for issue in case.issues:
        hit = any(all(word in text for word in alt) for alt in issue.alternatives for text in texts)
        (result.found if hit else result.missed).append(issue.key)
    return result
