"""Golden-set regression test for HeuristicChecker.

Synthetic cases are stable and run in CI. Real-video calibration is manual
(see HANDOFF / Task 35). Drift > 0.1 from expected scores will fail this test.
"""
import json
from pathlib import Path

import pytest

from skills.neurolearn.quality.heuristic_checker import HeuristicChecker
from skills.neurolearn.utils.output_writer import Segment


GOLDEN = json.loads(
    (Path(__file__).parent / "data" / "quality_golden.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["id"])
def test_golden_case(case):
    checker = HeuristicChecker()
    segments = [Segment(start=0.0, end=10.0, text=case["text"])]
    report = checker.check(segments, case["language"], source=case["source"])

    if "expected_score_min" in case:
        assert report.score >= case["expected_score_min"] - 0.05, \
            f"{case['id']}: score {report.score} below expected min {case['expected_score_min']}"
    if "expected_score_max" in case:
        assert report.score <= case["expected_score_max"] + 0.05, \
            f"{case['id']}: score {report.score} above expected max {case['expected_score_max']}"
    if "expected_recommendation" in case:
        assert report.recommendation == case["expected_recommendation"], \
            f"{case['id']}: rec={report.recommendation}, expected={case['expected_recommendation']}"
    if "expected_flags_include" in case:
        assert case["expected_flags_include"] in report.flags, \
            f"{case['id']}: flag missing. Got flags: {report.flags}"
    if "expected_flags_include_any" in case:
        wanted = case["expected_flags_include_any"]
        assert any(f in report.flags for f in wanted), \
            f"{case['id']}: none of {wanted} in {report.flags}"
