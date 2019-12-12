'''Stan meta-regression estimator.'''

import numpy as np
try:
    from pystan import StanModel
    import arviz as az
except:
    StanModel = None
    az = None

from .estimators import accepts_dataset


class StanMetaRegression:

    def __init__(self, **sampling_kwargs):

        if StanModel is None:
            raise ImportError("Unable to import PyStan package. Is it "
                              "installed?")
        if az is None:
            raise ValueError("Bayesian meta-regression results require the ArviZ"
                             " library, which doesn't seem to be installed.")
        self.sampling_kwargs = sampling_kwargs
        self.model = None
        self.result_ = None

    def compile(self):
        # Note: we deliberately use a centered parameterization for the
        # thetas at the moment. This is sub-optimal in terms of estimation,
        # but allows us to avoid having to add extra logic to detect and
        # handle intercepts in X.
        spec = f"""
        data {{
            int<lower=1> N;
            int<lower=1> K;
            vector[N] y;
            int<lower=1,upper=K> id[N];
            int<lower=1> C;
            matrix[K, C] X;
            vector[N] sigma;
        }}
        parameters {{
            vector[C] beta;
            vector[K] theta;
            real<lower=0> tau2;
        }}
        transformed parameters {{
            vector[N] mu;
            mu = theta[id] + X * beta;
        }}
        model {{
            y ~ normal(mu, sigma);
            theta ~ normal(0, tau2);
        }}
        """
        self.model = StanModel(model_code=spec)

    def fit(self, y, v, X, groups=None):

        if self.model is None:
            self.compile()

        N = y.shape[0]
        groups = groups or np.arange(1, N + 1, dtype=int)
        K = len(np.unique(groups))

        data = {
            "K": K,
            "N": N,
            'id': groups,
            'C': X.shape[1],
            'X': X,
            'y': y,
            'sigma': v
        }

        result = self.model.sampling(data=data, **self.sampling_kwargs)
        self.result_ = az.from_pystan(result)
        return self.result_


@accepts_dataset
def stan(y, v, X, groups=None, **sampling_kwargs):
    model = StanMetaRegression(**sampling_kwargs)
    return model.fit(y, v, X, groups)
