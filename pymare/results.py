"""Tools for representing and manipulating meta-regression results."""
from functools import lru_cache
from warnings import warn

import numpy as np
import pandas as pd
import scipy.stats as ss

try:
    import arviz as az
except:
    az = None

from .stats import q_profile


class MetaRegressionResults:
    """Container for results generated by PyMARE meta-regression estimators.

    Args:
        params (dict): A dictionary containing parameter estimates. Typically
            contains entries for at least 'beta' and 'tau^2'.
        dataset (`pymare.Dataset`): A Dataset instance containing the inputs
            to the estimator.
        estimator (`pymare.estimators.BaseEstimator`): The estimator used to
            produce the results.
        ci_method (str, optional): The method to use when generating confidence
            intervals for tau^2. Currently only 'QP' (Q-Profile) is supported.
        alpha (float, optional): alpha value defining the coverage of the CIs,
            where width = 1 - alpha. Defaults to 0.05.
    """
    def __init__(self, estimator, dataset, fe_params, fe_cov, tau2):
        self.estimator = estimator
        self.dataset = dataset
        self.fe_params = fe_params
        self.fe_cov = fe_cov
        self.tau2 = tau2

    @property
    @lru_cache(maxsize=1)
    def fe_se(self):
        cov = np.atleast_3d(self.fe_cov) # 3rd dim is for parallel datasets
        return np.sqrt(np.diagonal(cov)).T

    @lru_cache(maxsize=16)
    def get_fe_stats(self, alpha=0.05):
        beta, se = self.fe_params, self.fe_se
        z_se = ss.norm.ppf(1 - alpha / 2)
        z = beta / se
        return {
            'est': beta,
            'se': se,
            'ci_l': beta - z_se * se,
            'ci_u': beta + z_se * se,
            'z': z,
            'p': 1 - np.abs(0.5 - ss.norm.cdf(z)) * 2
        }

    @lru_cache(maxsize=16)
    def get_re_stats(self, method='QP', alpha=0.05):
        if method == 'QP':
            n_iters = self.tau2.shape[1]
            if len(n_iters > 10):
                warn("Method 'QP' is not parallelized; it may take a while to "
                     "compute CIs for {} parallel tau^2 values.".format(n_iters))

            # For sample size-based estimator, use sigma2/n instead of
            # sampling variances. TODO: find a solution than reaching
            # into the estimator's stored params, as this could fail if the
            # estimator has been applied to a different dataset.
            if self.dataset.v is None:
                v = self.estimator.params_['sigma2'] / self.dataset.n
            else:
                v = self.dataset.v

            cis = []
            for i in range(n_iters):
                args = {
                    'y': self.dataset.y[:, i],
                    'v': v[:, i],
                    'X': self.dataset.X,
                    'alpha': alpha,
                }
                q_cis = q_profile(**args)
                cis.append(q_cis)

        else:
            raise ValueError("Invalid CI method '{}'; currently only 'QP' is "
                             "available.".format(method))

        return {
            'tau^2': self.tau2,
            'ci_l': np.array([ci['ci_l'] for ci in cis])[:, None],
            'ci_u': np.array([ci['ci_u'] for ci in cis])[:, None]
        }

    def summary(self):
        pass

    def plot(self):
        pass

    def to_df(self, alpha=0.05, fixed=True, random=True):
        """Return a pandas DataFrame summarizing results."""
        b_shape = self.fe_params.shape
        if len(b_shape) > 1 and b_shape[1] > 1:
            raise ValueError("More than one set of results found! A summary "
                             "table cannot be displayed for multidimensional "
                             "results at the moment.")
        fe_stats = self.get_fe_stats(alpha).items()
        df = pd.DataFrame({k: v.ravel() for k, v in fe_stats})
        df['name'] = self.dataset.X_names
        df = df.loc[:, ['name', 'est', 'se', 'z', 'p', 'ci_l', 'ci_u']]
        ci_l = 'ci_{:.6g}'.format(alpha / 2)
        ci_u = 'ci_{:.6g}'.format(1 - alpha / 2)
        df.columns = ['name', 'estimate', 'se', 'z-score', 'p-val', ci_l, ci_u]

        return df


class BayesianMetaRegressionResults:
    """Container for MCMC sampling-based PyMARE meta-regression estimators.

    Args:
        data (`StanFit4Model` or `InferenceData`): Either a StanFit4Model
            instanced returned from PyStan or an ArviZ InferenceData instance.
        dataset (`pymare.Dataset`): A Dataset instance containing the inputs
            to the estimator.
        ci (float, optional): Desired width of highest posterior density (HPD)
            interval. Defaults to 95%.
    """
    def __init__(self, data, dataset, ci=95.):
        if az is None:
            raise ValueError("ArviZ package must be installed in order to work"
                             " with the BayesianMetaRegressionResults class.")
        if data.__class__.__name__ == 'StanFit4Model':
            data = az.from_pystan(data)
        self.data = data
        self.dataset = dataset
        self.ci = ci

    def summary(self, include_theta=False, **kwargs):
        """Summarize the posterior estimates via ArviZ.

        Args:
            include_theta (bool, optional): Whether or not to include the
                estimated group-level means in the summary. Defaults to False.
            kwargs: Optional keyword arguments to pass onto ArviZ's summary().

        Returns:
            A pandas DataFrame, unless the `fmt="xarray"` argument is passed in
            kwargs, in which case an xarray Dataset is returned.
        """
        var_names = ['beta', 'tau2']
        if include_theta:
            var_names.append('theta')
        var_names = kwargs.pop('var_names', var_names)
        return az.summary(self.data, var_names, **kwargs)

    def plot(self, kind='trace', **kwargs):
        """Generate various plots of the posterior estimates via ArviZ.

        Args:
            kind (str, optional): The type of ArviZ plot to generate. Can be
                any named function of the form "plot_{}" in the ArviZ
                namespace (e.g., 'trace', 'forest', 'posterior', etc.).
                Defaults to 'trace'.
            kwargs: Optional keyword arguments passed onto the corresponding
                ArviZ plotting function (see ArviZ docs for details).

        Returns:
            A matplotlib or bokeh object, depending on plot kind and kwargs.
        """
        name = 'plot_{}'.format(kind)
        plotter = getattr(az, name)
        if plotter is None:
            raise ValueError("ArviZ has no plotting function '{}'.".format(name))
        plotter(self.data, **kwargs)
