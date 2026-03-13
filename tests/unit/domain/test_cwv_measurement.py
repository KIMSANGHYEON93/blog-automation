"""CwvMeasurement Value Object tests."""
from src.domain.value_objects.cwv_measurement import CwvMeasurement


class TestCwvMeasurement:
    def test_lcp_grade_good(self):
        m = CwvMeasurement(lcp_seconds=1.5, cls_score=0.05, performance_score=95, passed=True)
        assert m.lcp_grade == "good"

    def test_lcp_grade_needs_improvement(self):
        m = CwvMeasurement(lcp_seconds=3.0, cls_score=0.05, performance_score=70, passed=False)
        assert m.lcp_grade == "needs_improvement"

    def test_lcp_grade_poor(self):
        m = CwvMeasurement(lcp_seconds=5.0, cls_score=0.05, performance_score=40, passed=False)
        assert m.lcp_grade == "poor"

    def test_cls_grade_good(self):
        m = CwvMeasurement(lcp_seconds=2.0, cls_score=0.05, performance_score=90, passed=True)
        assert m.cls_grade == "good"

    def test_cls_grade_needs_improvement(self):
        m = CwvMeasurement(lcp_seconds=2.0, cls_score=0.2, performance_score=70, passed=False)
        assert m.cls_grade == "needs_improvement"

    def test_cls_grade_poor(self):
        m = CwvMeasurement(lcp_seconds=2.0, cls_score=0.4, performance_score=40, passed=False)
        assert m.cls_grade == "poor"

    def test_needs_optimization_when_poor(self):
        m = CwvMeasurement(lcp_seconds=5.0, cls_score=0.05, performance_score=40, passed=False)
        assert m.needs_optimization is True

    def test_no_optimization_when_good(self):
        m = CwvMeasurement(lcp_seconds=2.0, cls_score=0.05, performance_score=90, passed=True)
        assert m.needs_optimization is False

    def test_boundary_lcp_2_5(self):
        m = CwvMeasurement(lcp_seconds=2.5, cls_score=0.0, performance_score=90, passed=True)
        assert m.lcp_grade == "good"

    def test_boundary_cls_0_1(self):
        m = CwvMeasurement(lcp_seconds=1.0, cls_score=0.1, performance_score=90, passed=True)
        assert m.cls_grade == "good"

    def test_frozen_immutable(self):
        m = CwvMeasurement(lcp_seconds=2.0, cls_score=0.05, performance_score=90, passed=True)
        try:
            m.lcp_seconds = 5.0  # type: ignore[misc]
            raise AssertionError("Should raise FrozenInstanceError")
        except AttributeError:
            pass
