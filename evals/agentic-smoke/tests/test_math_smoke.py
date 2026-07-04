import numpy as np
import pytest
from hypothesis import given, strategies as st
from scipy import stats


def mean_with_numpy(values: list[float]) -> float:
    return float(np.mean(values))


@given(st.lists(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False), min_size=1, max_size=25))
def test_numpy_mean_matches_python(values: list[float]) -> None:
    assert mean_with_numpy(values) == pytest.approx(sum(values) / len(values))


def test_scipy_normal_cdf_midpoint() -> None:
    assert stats.norm.cdf(0) == 0.5
