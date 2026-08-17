"""Full traceability graph and deterministic consistency checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.test_coverage import build_acceptance_criteria_index, calculate_test_coverage


STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
EXPECTED_EXCLUSION = "Expected Exclusion"
BROKEN_TRACEABILITY = "Broken Traceability"


@dataclass(frozen=True)
class TraceabilityArtifacts:
    reviews: list[dict[str, Any]]
    topics: list[dict[str, Any]]
    topic_validation: dict[str, Any]
    issues: list[dict[str, Any]]
    issue_validation: dict[str, Any]
    issue_classification: dict[str, Any]
    finding_eligibility: dict[str, Any]
    findings: list[dict[str, Any]]
    finding_validation: dict[str, Any]
    evidence_report: dict[str, Any]
    requirements: list[dict[str, Any]]
    requirement_validation: dict[str, Any]
    priority_report: dict[str, Any]
    roadmap: dict[str, Any]
    roadmap_validation: dict[str, Any]
    prds: list[dict[str, Any]]
    prd_validation: dict[str, Any]
    test_cases: list[dict[str, Any]]
    test_case_validation: dict[str, Any]
    test_coverage: dict[str, Any]
    processing_statistics: dict[str, Any] | None = None
    processing_report: dict[str, Any] | None = None


@dataclass(frozen=True)
class TracePath:
    test_case_id: str
    requirement_id: str
    acceptance_criteria_ids: list[str]
    finding_ids: list[str]
    issue_ids: list[str]
    topic_ids: list[str]
    review_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceabilityAuditResult:
    forward_traceability: str
    backward_traceability: str
    artifact_consistency: str
    evidence_traceability: str
    explicit_test_case_review_link: str
    version_prd_consistency: str
    ac_structural_coverage: str
    orphan_summary: dict[str, list[str]] = field(default_factory=dict)
    expected_exclusions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    test_case_paths: list[TracePath] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(
            status == STATUS_PASS
            for status in (
                self.forward_traceability,
                self.backward_traceability,
                self.artifact_consistency,
                self.evidence_traceability,
                self.explicit_test_case_review_link,
                self.version_prd_consistency,
                self.ac_structural_coverage,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["passed"] = self.passed
        payload["test_case_paths"] = [path.to_dict() for path in self.test_case_paths]
        return payload


class TraceabilityGraph:
    """Bidirectional lookup graph across Review -> Test Case artifacts."""

    def __init__(self, artifacts: TraceabilityArtifacts) -> None:
        self.artifacts = artifacts
        self.reviews_by_id = _index_by_id(artifacts.reviews, "id")
        self.topics_by_id = _index_by_id(artifacts.topics, "topic_id")
        self.issues_by_id = _index_by_id(artifacts.issues, "issue_id")
        self.findings_by_id = _index_by_id(artifacts.findings, "finding_id")
        self.requirements_by_id = _index_by_id(artifacts.requirements, "requirement_id")
        self.prds_by_id = _index_by_id(artifacts.prds, "prd_id")
        self.test_cases_by_id = _index_by_id(artifacts.test_cases, "test_case_id")
        self.acceptance_criteria_by_id = build_acceptance_criteria_index(artifacts.requirements)
        self.versions_by_id = _index_by_id(_list(artifacts.roadmap.get("versions")), "version_id")
        self.roadmap_items_by_requirement_id = _index_by_id(
            _list(artifacts.roadmap.get("roadmap_items")), "requirement_id"
        )

    def topics_for_review(self, review_id: str) -> list[dict[str, Any]]:
        return [
            topic
            for topic in self.artifacts.topics
            if review_id in _id_list(topic.get("review_ids"))
        ]

    def issues_for_topic(self, topic_id: str) -> list[dict[str, Any]]:
        return [
            issue
            for issue in self.artifacts.issues
            if topic_id in _id_list(issue.get("topic_ids"))
        ]

    def findings_for_issue(self, issue_id: str) -> list[dict[str, Any]]:
        return [
            finding
            for finding in self.artifacts.findings
            if issue_id in _id_list(finding.get("issue_ids"))
        ]

    def requirements_for_finding(self, finding_id: str) -> list[dict[str, Any]]:
        return [
            requirement
            for requirement in self.artifacts.requirements
            if finding_id in _id_list(requirement.get("finding_ids"))
        ]

    def versions_for_requirement(self, requirement_id: str) -> list[dict[str, Any]]:
        return [
            version
            for version in _list(self.artifacts.roadmap.get("versions"))
            if requirement_id in _id_list(version.get("requirement_ids"))
        ]

    def prds_for_requirement(self, requirement_id: str) -> list[dict[str, Any]]:
        return [
            prd
            for prd in self.artifacts.prds
            if requirement_id in _id_list(prd.get("requirement_ids"))
        ]

    def acceptance_criteria_for_requirement(self, requirement_id: str) -> list[dict[str, Any]]:
        return [
            criterion
            for criterion in self.acceptance_criteria_by_id.values()
            if criterion.get("requirement_id") == requirement_id
        ]

    def test_cases_for_acceptance_criteria(self, acceptance_criteria_id: str) -> list[dict[str, Any]]:
        return [
            test_case
            for test_case in self.artifacts.test_cases
            if acceptance_criteria_id in _id_list(test_case.get("acceptance_criteria_ids"))
        ]

    def reviews_for_test_case(self, test_case_id: str) -> list[dict[str, Any]]:
        path = self.trace_test_case(test_case_id)
        if not path:
            return []
        return [self.reviews_by_id[review_id] for review_id in path.review_ids if review_id in self.reviews_by_id]

    def trace_test_case(self, test_case_id: str) -> TracePath | None:
        test_case = self.test_cases_by_id.get(test_case_id)
        if not test_case:
            return None
        requirement_id = _text(test_case.get("requirement_id"))
        requirement = self.requirements_by_id.get(requirement_id, {})
        finding_ids = _id_list(requirement.get("finding_ids"))
        issue_ids: set[str] = set()
        topic_ids: set[str] = set()
        review_ids: set[str] = set()
        explicit_review_ids = _id_list(test_case.get("source_review_ids"))
        for finding_id in finding_ids:
            finding = self.findings_by_id.get(finding_id, {})
            review_ids.update(_id_list(finding.get("review_ids")))
            for issue_id in _id_list(finding.get("issue_ids")):
                issue_ids.add(issue_id)
                issue = self.issues_by_id.get(issue_id, {})
                review_ids.update(_id_list(issue.get("review_ids")))
                for topic_id in _id_list(issue.get("topic_ids")):
                    topic_ids.add(topic_id)
                    review_ids.update(_id_list(self.topics_by_id.get(topic_id, {}).get("review_ids")))
        return TracePath(
            test_case_id=test_case_id,
            requirement_id=requirement_id,
            acceptance_criteria_ids=_id_list(test_case.get("acceptance_criteria_ids")),
            finding_ids=sorted(finding_ids),
            issue_ids=sorted(issue_ids),
            topic_ids=sorted(topic_ids),
            review_ids=sorted(explicit_review_ids or review_ids),
        )

    def validate(self) -> TraceabilityAuditResult:
        errors: list[str] = []
        warnings: list[str] = []
        expected_exclusions: list[str] = []
        orphan_summary = self.find_orphans(expected_exclusions)
        counts = self.counts()

        forward_errors = self._forward_errors()
        backward_errors, test_case_paths = self._backward_errors()
        version_prd_errors = self._version_prd_errors()
        artifact_errors, artifact_warnings, coverage = self._artifact_consistency()
        evidence_errors = self._evidence_traceability_errors(test_case_paths)
        explicit_review_link_errors = self._explicit_test_case_review_link_errors()
        ac_errors = self._acceptance_criteria_errors()

        errors.extend(forward_errors)
        errors.extend(backward_errors)
        errors.extend(version_prd_errors)
        errors.extend(artifact_errors)
        errors.extend(evidence_errors)
        errors.extend(explicit_review_link_errors)
        errors.extend(ac_errors)
        warnings.extend(artifact_warnings)

        return TraceabilityAuditResult(
            forward_traceability=STATUS_PASS if not forward_errors else STATUS_FAIL,
            backward_traceability=STATUS_PASS if not backward_errors else STATUS_FAIL,
            artifact_consistency=STATUS_PASS if not artifact_errors else STATUS_FAIL,
            evidence_traceability=STATUS_PASS if not evidence_errors else STATUS_FAIL,
            explicit_test_case_review_link=STATUS_PASS if not explicit_review_link_errors else STATUS_FAIL,
            version_prd_consistency=STATUS_PASS if not version_prd_errors else STATUS_FAIL,
            ac_structural_coverage=STATUS_PASS if not ac_errors else STATUS_FAIL,
            orphan_summary=orphan_summary,
            expected_exclusions=expected_exclusions,
            errors=errors,
            warnings=warnings,
            counts=counts,
            coverage=coverage,
            test_case_paths=test_case_paths,
        )

    def counts(self) -> dict[str, int]:
        return {
            "reviews": len(self.artifacts.reviews),
            "topics": len(self.artifacts.topics),
            "issues": len(self.artifacts.issues),
            "findings": len(self.artifacts.findings),
            "requirements": len(self.artifacts.requirements),
            "versions": len(_list(self.artifacts.roadmap.get("versions"))),
            "prds": len(self.artifacts.prds),
            "acceptance_criteria": len(self.acceptance_criteria_by_id),
            "test_cases": len(self.artifacts.test_cases),
        }

    def find_orphans(self, expected_exclusions: list[str] | None = None) -> dict[str, list[str]]:
        expected_exclusions = expected_exclusions if expected_exclusions is not None else []
        eligibility_by_issue = {
            _text(item.get("issue_id")): bool(item.get("eligible_for_finding"))
            for item in _list(self.artifacts.finding_eligibility.get("eligibility"))
        }
        linked_topic_ids = {topic_id for issue in self.artifacts.issues for topic_id in _id_list(issue.get("topic_ids"))}
        linked_issue_ids = {issue_id for finding in self.artifacts.findings for issue_id in _id_list(finding.get("issue_ids"))}
        linked_finding_ids = {finding_id for req in self.artifacts.requirements for finding_id in _id_list(req.get("finding_ids"))}
        linked_requirement_ids = {item.get("requirement_id") for item in _list(self.artifacts.roadmap.get("roadmap_items"))}
        linked_prd_version_ids = {_text(prd.get("version_id")) for prd in self.artifacts.prds}
        linked_ac_ids = {ac_id for tc in self.artifacts.test_cases for ac_id in _id_list(tc.get("acceptance_criteria_ids"))}
        linked_test_case_ids = {_text(tc.get("test_case_id")) for tc in self.artifacts.test_cases if _text(tc.get("requirement_id"))}

        orphan_reviews = [
            review_id
            for review_id in sorted(self.reviews_by_id)
            if not self.topics_for_review(review_id)
        ]
        orphan_topics = sorted(set(self.topics_by_id) - linked_topic_ids)
        orphan_issues = []
        for issue_id in sorted(set(self.issues_by_id) - linked_issue_ids):
            if eligibility_by_issue.get(issue_id) is False:
                expected_exclusions.append(f"{issue_id}: positive/neutral issue excluded from Finding")
            else:
                orphan_issues.append(issue_id)

        return {
            "orphan_reviews": orphan_reviews,
            "orphan_topics": orphan_topics,
            "orphan_issues": orphan_issues,
            "orphan_findings": sorted(set(self.findings_by_id) - linked_finding_ids),
            "orphan_requirements": sorted(set(self.requirements_by_id) - {str(item) for item in linked_requirement_ids if item}),
            "orphan_prds": [
                prd_id
                for prd_id, prd in sorted(self.prds_by_id.items())
                if _text(prd.get("version_id")) not in self.versions_by_id
            ],
            "orphan_acceptance_criteria": sorted(set(self.acceptance_criteria_by_id) - linked_ac_ids),
            "orphan_test_cases": sorted(set(self.test_cases_by_id) - linked_test_case_ids),
            "version_without_prd": sorted(set(self.versions_by_id) - linked_prd_version_ids),
        }

    def _forward_errors(self) -> list[str]:
        errors: list[str] = []
        for topic_id, topic in self.topics_by_id.items():
            for review_id in _id_list(topic.get("review_ids")):
                if review_id not in self.reviews_by_id:
                    errors.append(f"{topic_id}: unknown review_id {review_id}")
            if not self.issues_for_topic(topic_id):
                errors.append(f"{topic_id}: no downstream issue")
        for issue_id, issue in self.issues_by_id.items():
            for topic_id in _id_list(issue.get("topic_ids")):
                if topic_id not in self.topics_by_id:
                    errors.append(f"{issue_id}: unknown topic_id {topic_id}")
            if not self.findings_for_issue(issue_id) and self._issue_eligible(issue_id):
                errors.append(f"{issue_id}: eligible issue has no downstream finding")
        for finding_id, finding in self.findings_by_id.items():
            for issue_id in _id_list(finding.get("issue_ids")):
                if issue_id not in self.issues_by_id:
                    errors.append(f"{finding_id}: unknown issue_id {issue_id}")
            if not self.requirements_for_finding(finding_id):
                errors.append(f"{finding_id}: no downstream requirement")
        for requirement_id in self.requirements_by_id:
            if not self.versions_for_requirement(requirement_id):
                errors.append(f"{requirement_id}: no downstream version")
            if not self.prds_for_requirement(requirement_id):
                errors.append(f"{requirement_id}: no downstream PRD")
            for criterion in self.acceptance_criteria_for_requirement(requirement_id):
                if not self.test_cases_for_acceptance_criteria(criterion["acceptance_criteria_id"]):
                    errors.append(f"{criterion['acceptance_criteria_id']}: no downstream test case")
        return errors

    def _backward_errors(self) -> tuple[list[str], list[TracePath]]:
        errors: list[str] = []
        paths: list[TracePath] = []
        for test_case_id, test_case in self.test_cases_by_id.items():
            requirement_id = _text(test_case.get("requirement_id"))
            requirement = self.requirements_by_id.get(requirement_id)
            if not requirement:
                errors.append(f"{test_case_id}: unknown requirement_id {requirement_id}")
                continue
            for acceptance_criteria_id in _id_list(test_case.get("acceptance_criteria_ids")):
                criterion = self.acceptance_criteria_by_id.get(acceptance_criteria_id)
                if not criterion:
                    errors.append(f"{test_case_id}: unknown acceptance_criteria_id {acceptance_criteria_id}")
                elif criterion.get("requirement_id") != requirement_id:
                    errors.append(
                        f"{test_case_id}: {acceptance_criteria_id} belongs to {criterion.get('requirement_id')}"
                    )
            finding_ids = _id_list(requirement.get("finding_ids"))
            if not finding_ids:
                errors.append(f"{test_case_id}: requirement {requirement_id} has no finding_ids")
            for finding_id in finding_ids:
                finding = self.findings_by_id.get(finding_id)
                if not finding:
                    errors.append(f"{test_case_id}: unknown finding_id {finding_id}")
                    continue
                if not _id_list(finding.get("review_ids")):
                    errors.append(f"{test_case_id}: finding {finding_id} has no review evidence")
                for issue_id in _id_list(finding.get("issue_ids")):
                    issue = self.issues_by_id.get(issue_id)
                    if not issue:
                        errors.append(f"{test_case_id}: unknown issue_id {issue_id}")
                        continue
                    for topic_id in _id_list(issue.get("topic_ids")):
                        topic = self.topics_by_id.get(topic_id)
                        if not topic:
                            errors.append(f"{test_case_id}: unknown topic_id {topic_id}")
                        else:
                            for review_id in _id_list(topic.get("review_ids")):
                                if review_id not in self.reviews_by_id:
                                    errors.append(f"{test_case_id}: unknown review_id {review_id}")
            path = self.trace_test_case(test_case_id)
            if path:
                paths.append(path)
        return errors, paths

    def _version_prd_errors(self) -> list[str]:
        errors: list[str] = []
        for prd in self.artifacts.prds:
            prd_id = _text(prd.get("prd_id"))
            version_id = _text(prd.get("version_id"))
            version = self.versions_by_id.get(version_id)
            if not version:
                errors.append(f"{prd_id}: unknown version_id {version_id}")
                continue
            prd_requirements = set(_id_list(prd.get("requirement_ids")))
            version_requirements = set(_id_list(version.get("requirement_ids")))
            if prd_requirements != version_requirements:
                errors.append(
                    f"{prd_id}: requirement_ids {sorted(prd_requirements)} != version {version_id} {sorted(version_requirements)}"
                )
        return errors

    def _artifact_consistency(self) -> tuple[list[str], list[str], dict[str, Any]]:
        errors: list[str] = []
        warnings: list[str] = []
        validation_files = {
            "topic_validation": self.artifacts.topic_validation,
            "issue_validation": self.artifacts.issue_validation,
            "finding_validation": self.artifacts.finding_validation,
            "requirement_validation": self.artifacts.requirement_validation,
            "roadmap_validation": self.artifacts.roadmap_validation,
            "prd_validation": self.artifacts.prd_validation,
            "test_case_validation": self.artifacts.test_case_validation,
        }
        for label, payload in validation_files.items():
            if not _validation_passed(payload):
                errors.append(f"{label}: not PASS")

        coverage_report = calculate_test_coverage(
            requirements=self.artifacts.requirements,
            test_cases=self.artifacts.test_cases,
        ).to_dict()
        for key in (
            "total_requirements",
            "covered_requirements",
            "requirement_coverage",
            "total_acceptance_criteria",
            "covered_acceptance_criteria",
            "acceptance_criteria_coverage",
        ):
            if self.artifacts.test_coverage.get(key) != coverage_report.get(key):
                errors.append(
                    f"test_coverage.{key}: artifact {self.artifacts.test_coverage.get(key)} != recalculated {coverage_report.get(key)}"
                )

        statistics = self.artifacts.processing_statistics or {}
        if statistics:
            if statistics.get("total") != len(self.artifacts.reviews):
                errors.append("processed statistics total does not match reviews count")
        else:
            warnings.append("processed statistics artifact not supplied")
        return errors, warnings, coverage_report

    def _evidence_traceability_errors(self, paths: list[TracePath]) -> list[str]:
        errors: list[str] = []
        for path in paths:
            if not path.review_ids:
                errors.append(f"{path.test_case_id}: no reachable review evidence")
            for review_id in path.review_ids:
                if review_id not in self.reviews_by_id:
                    errors.append(f"{path.test_case_id}: unknown reachable review {review_id}")
        return errors

    def _explicit_test_case_review_link_errors(self) -> list[str]:
        errors: list[str] = []
        for test_case_id, test_case in self.test_cases_by_id.items():
            if "source_review_ids" not in test_case:
                errors.append(f"{test_case_id}: missing source_review_ids")
                continue
            source_review_ids = _id_list(test_case.get("source_review_ids"))
            requirement = self.requirements_by_id.get(_text(test_case.get("requirement_id")))
            if not requirement:
                continue
            expected_review_ids: set[str] = set()
            for finding_id in _id_list(requirement.get("finding_ids")):
                finding = self.findings_by_id.get(finding_id)
                if finding:
                    expected_review_ids.update(_id_list(finding.get("review_ids")))
            if expected_review_ids and not source_review_ids:
                errors.append(f"{test_case_id}: source_review_ids must include requirement finding review evidence")
                continue
            for review_id in source_review_ids:
                if review_id not in self.reviews_by_id:
                    errors.append(f"{test_case_id}: source_review_ids references unknown review_id {review_id}")
            outside_review_ids = sorted(set(source_review_ids) - expected_review_ids)
            if expected_review_ids and outside_review_ids:
                errors.append(f"{test_case_id}: source_review_ids outside requirement finding evidence {outside_review_ids}")
            if expected_review_ids and not set(source_review_ids).intersection(expected_review_ids):
                errors.append(f"{test_case_id}: source_review_ids do not match requirement finding evidence")
        return errors

    def _acceptance_criteria_errors(self) -> list[str]:
        errors: list[str] = []
        for acceptance_criteria_id, criterion in self.acceptance_criteria_by_id.items():
            requirement_id = _text(criterion.get("requirement_id"))
            if requirement_id not in self.requirements_by_id:
                errors.append(f"{acceptance_criteria_id}: unknown owner requirement {requirement_id}")
            if not self.test_cases_for_acceptance_criteria(acceptance_criteria_id):
                errors.append(f"{acceptance_criteria_id}: uncovered")
        return errors

    def _issue_eligible(self, issue_id: str) -> bool:
        for item in _list(self.artifacts.finding_eligibility.get("eligibility")):
            if _text(item.get("issue_id")) == issue_id:
                return bool(item.get("eligible_for_finding"))
        return True


def _validation_passed(payload: dict[str, Any]) -> bool:
    return payload.get("passed") is True or payload.get("status") == "Success"


def _index_by_id(items: list[dict[str, Any]], field_name: str) -> dict[str, dict[str, Any]]:
    return {
        _text(item.get(field_name)): item
        for item in items
        if isinstance(item, dict) and _text(item.get(field_name))
    }


def _list(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def _id_list(value: Any) -> list[str]:
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else str(value).strip() if value is not None else ""
