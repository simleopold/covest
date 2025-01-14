import inspect
import itertools
import multiprocessing
import sys
from covest_poisson import truncated_poisson as tr_poisson
from functools import lru_cache
from math import exp, fsum

import matplotlib.pyplot as plt
from scipy.special import comb

from covest import constants
from covest.utils import safe_log, fix_zero

MODEL_CLASS_SUFFIX = 'Model'

class BasicModel:
    params = ('coverage', 'error_rate')
    def __init__(self, k, r, hist, tail, max_error=None, max_cov=None, *args, **kwargs):
        self.repeats = False
        self.k = k
        self.r = r
        self.bounds = ((0.01, max_cov), (0, 0.5))
        self.defaults = (1, self._default_param(1))
        self.comb = [comb(k, s) * (3 ** s) for s in range(k + 1)]
        self.hist = hist
        self.tail = tail
        if max_error is None:
            self.max_error = self.k + 1
        else:
            self.max_error = min(self.k + 1, max_error)

    @classmethod
    def short_name(cls):
        name = cls.__name__
        if name.endswith(MODEL_CLASS_SUFFIX):
            name = name[:-len(MODEL_CLASS_SUFFIX)]
        return name.lower()

    @property
    def param_count(self):
        return len(self.params)

    def _default_param(self, i, default=None):
        l, r = self.bounds[i]
        if l is None or r is None:
            return default
        return (l + r) / 2

    def check_bounds(self, args):
        for arg, (l, r) in zip(args, self.bounds):
            if arg is None:
                continue
            if arg == float('NaN'):
                return False
            if (l is not None and arg < l) or (r is not None and arg > r):
                return False
        return True

    def fit_to_bounds(self, args):
        args = list(args)
        for i, (arg, (l, r)) in enumerate(zip(args, self.bounds)):
            if arg is None:
                continue
            if (l is not None and arg < l):
                args[i] = l
            elif (r is not None and arg > r):
                args[i] = r
        return args

    def correct_c(self, c):
        return c * (self.r - self.k + 1) / self.r

    @lru_cache(maxsize=None)
    def _get_lambda_s(self, c, err):
        return [
            c * (3 ** -s) * (1.0 - err) ** (self.k - s) * err ** s
            for s in range(self.max_error)
        ]

    def compute_probabilities(self, c, err, *_):
        # read to kmer coverage
        ck = self.correct_c(c)
        # lambda for kmers with s errors
        l_s = self._get_lambda_s(ck, err)
        # expected probability of kmers with s errors and coverage >= 1
        n_s = [self.comb[s] * (1.0 - exp(-l_s[s])) for s in range(self.max_error)]
        sum_n_s = fix_zero(sum(n_s[t] for t in range(self.max_error)))
        # portion of kmers with s errors
        a_s = [n_s[s] / sum_n_s for s in range(self.max_error)]
        # probability that unique kmer has coverage j (j > 0)
        p_j = {
            j: sum(
                a_s[s] * tr_poisson(l_s[s], j) for s in range(self.max_error)
            )
            for j in self.hist
        }
        return p_j

    def compute_loglikelihood(self, *args):
        args = self.fit_to_bounds(args)
        p_j = self.compute_probabilities(*args)
        sp_j = min(1, fsum(p_j.values()))
        tail = self.tail * safe_log(1 - sp_j) if sp_j < 1 else 0
        return float(sum(
            h * safe_log(p_j[j]) for j, h in self.hist.items() if h
        )) + tail

    def compute_loglikelihood_multi(self, args_list, thread_count=constants.DEFAULT_THREAD_COUNT):
        if thread_count is None:  # do not use multiprocessing
            likelihoods = itertools.starmap(self.compute_loglikelihood, args_list)
        else:
            pool = multiprocessing.Pool(processes=thread_count)
            likelihoods = pool.starmap(self.compute_loglikelihood, args_list)
        return {
            tuple(args): likelihood for args, likelihood in zip(args_list, likelihoods)
        }

    def plot_probs(self, est, guess, orig, cumulative=False, log_scale=True):
        def fmt(p):
            return ['{:.3f}'.format(x) if x is not None else 'None' for x in p[:20]]

        def adjust_probs(probs, hist=False):
            max_j = max(probs)
            if hist:
                tail = self.tail
            else:
                sp = sum(probs.values())
                tail = 1 - sp
            if cumulative:
                return [probs.get(i, 0) * i for i in range(max_j)]
            else:
                return [probs.get(i, 0) for i in range(max_j)]

        hs = float(sum(self.hist.values()))
        hp = adjust_probs({k: f / hs for k, f in self.hist.items()}, hist=True)
        ep = adjust_probs(self.compute_probabilities(*est))
        gp = adjust_probs(self.compute_probabilities(*guess))
        if orig is not None and None not in orig:
            op = adjust_probs(self.compute_probabilities(*orig))
        else:
            op = adjust_probs({1:0})

        if log_scale:
            plt.yscale('log')
        plt.plot(
            range(len(hp)), hp, 'ko',
            label='hist',
            ms=8,
        )
        plt.plot(
            range(len(ep)), ep, 'ro',
            label='est: {}'.format(fmt(est)),
            ms=6,
        )
        plt.plot(
            range(len(gp)), gp, 'go',
            label='guess: {}'.format(fmt(guess)),
            ms=5,
        )
        plt.plot(
            range(len(op)), op, 'co',
            label='orig: {}'.format(fmt(orig)),
            ms=4,
        )
        plt.legend()
        try:
            plt.show()
        except KeyboardInterrupt:
            pass


class RepeatsModel(BasicModel):
    params = BasicModel.params + ('q1', 'q2', 'q')
    def __init__(self, k, r, hist, tail, max_error=None, max_cov=None, threshold=1e-8,
                 min_single_copy_ratio=0.3, *args, **kwargs):
        super(RepeatsModel, self).__init__(k, r, hist, tail, max_error=max_error)
        self.repeats = True
        self.bounds = self.bounds +  ((min_single_copy_ratio, 1), (0, 1), (0, 1))
        self.defaults = self.defaults + tuple(
            self._default_param(i, default=0.5) for i in range(2, 5)
        )
        self.threshold = threshold

    def get_hist_threshold(self, b_o, threshold):
        hist_size = max(self.hist)
        if threshold is not None:
            for o in range(1, hist_size):
                if b_o(o) <= threshold:
                    return o
        return hist_size

    @staticmethod
    def get_b_o(q1, q2, q):
        o_2 = (1 - q1) * q2
        o_n = (1 - q1) * (1 - q2) * q

        def b_o(o):
            if o == 0:
                return 0
            elif o == 1:
                return q1
            elif o == 2:
                return o_2
            else:
                return o_n * (1 - q) ** (o - 3)

        return b_o

    # noinspection PyMethodOverriding
    def compute_probabilities(self, c, err, q1, q2, q, *_):
        b_o = self.get_b_o(q1, q2, q)
        threshold_o = self.get_hist_threshold(b_o, self.threshold)
        # read to kmer coverage
        c = self.correct_c(c)
        # lambda for kmers with s errors
        l_s = self._get_lambda_s(c, err)
        # expected probability of kmers with s errors and coverage >= 1
        # noinspection PyTypeChecker
        n_os = [None] + [
            [self.comb[s] * (1.0 - exp(o * -l_s[s])) for s in range(self.max_error)]
            for o in range(1, threshold_o)
        ]
        sum_n_os = [None] + [
            fix_zero(sum(n_os[o][t] for t in range(self.max_error))) for o in range(1, threshold_o)
        ]

        # portion of kmers wit1h s errors
        # noinspection PyTypeChecker
        a_os = [None] + [
            [n_os[o][s] / (sum_n_os[o] if sum_n_os[o] != 0 else 1) for s in range(self.max_error)]
            for o in range(1, threshold_o)
        ]
        # probability that unique kmer has coverage j (j > 0)
        p_j = {
            j: sum(
                b_o(o) * sum(
                    a_os[o][s] * tr_poisson(o * l_s[s], j) for s in range(self.max_error)
                ) for o in range(1, threshold_o)
            ) for j in self.hist
        }
        return p_j


models = {
    cls.short_name(): cls for _, cls in inspect.getmembers(
        sys.modules[__name__], predicate=lambda x: inspect.isclass(x) and x.__name__.endswith(MODEL_CLASS_SUFFIX)
    )
}


def select_model(m):
    if m in models:
        return models[m]
    else:
        for k, model in models.items():
            if k.startswith(m):
                return model
    raise ValueError('Not such model: {}.'.format(m))
