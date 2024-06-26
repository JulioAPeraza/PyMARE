"""Tests for estimators that use stan."""

import sys

import pytest

from pymare.estimators import StanMetaRegression


@pytest.mark.skipif(sys.version_info < (3, 7), reason="requires python 3.7 or higher")
def test_stan_estimator(dataset):
    """Run smoke test for StanMetaRegression."""
    # no ground truth here, so we use sanity checks and rough bounds
    est = StanMetaRegression(num_samples=3000).fit_dataset(dataset)
    results = est.summary()
    assert "BayesianMetaRegressionResults" == results.__class__.__name__
    summary = results.summary(["beta", "tau2"])
    beta1, beta2, tau2 = summary["mean"].values[:3]
    assert -0.5 < beta1 < 0.1
    assert 0.6 < beta2 < 0.9
    assert 3 < tau2 < 5


@pytest.mark.skipif(sys.version_info < (3, 7), reason="requires python 3.7 or higher")
def test_stan_2d_input_failure(dataset_2d):
    """Run smoke test for StanMetaRegression on 2D data."""
    with pytest.raises(ValueError) as exc:
        StanMetaRegression(num_samples=500).fit_dataset(dataset_2d)
    assert str(exc.value).startswith("The StanMetaRegression")


def test_stan_python_36_failure(dataset):
    """Run smoke test for StanMetaRegression with Python 3.6."""
    if sys.version_info < (3, 7):
        # Raise error if StanMetaRegression is initialize with python 3.6 or lower
        with pytest.raises(RuntimeError):
            StanMetaRegression(num_samples=3000).fit_dataset(dataset)
