import signal
from timeit import default_timer as timer
from os import path
from os import listdir

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.cross_decomposition import PLSRegression
from sklearn.ensemble import AdaBoostClassifier, ExtraTreesClassifier, GradientBoostingClassifier, \
    RandomForestClassifier, AdaBoostRegressor, BaggingRegressor, ExtraTreesRegressor, GradientBoostingRegressor, \
    RandomForestRegressor
from sklearn.kernel_ridge import KernelRidge
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV, PassiveAggressiveClassifier, Perceptron, \
    BayesianRidge, HuberRegressor, LinearRegression, \
    OrthogonalMatchingPursuit, \
    OrthogonalMatchingPursuitCV, PassiveAggressiveRegressor
from sklearn.model_selection import cross_val_score
from sklearn.naive_bayes import BernoulliNB, GaussianNB, MultinomialNB
from sklearn.neighbors import KNeighborsClassifier, NearestCentroid, KNeighborsRegressor
from sklearn.neural_network import MLPClassifier
from sklearn.svm import LinearSVC, SVC, LinearSVR, NuSVR, SVR
from sklearn.tree import DecisionTreeClassifier, ExtraTreeClassifier, DecisionTreeRegressor, ExtraTreeRegressor

from .problem_classification import ProblemClassifier
from .relative_landmarks import get_rls


class BaseEvaluator:
    models = None
    models_path = None

    def __init__(self, time_limit=0, time_accuracy_trade_rate=0):
        """
        :param time_limit: time limit for classification_meta_models evaluations. Default is 0 (no limit)
        :param time_accuracy_trade_rate: amount of accuracy(%) willing to trade for 10 times speed-up.
        """

        self.time_limit = time_limit
        self.time_accuracy_trade_rate = time_accuracy_trade_rate
        self.models_quality = pd.DataFrame(columns=['Model', 'Score', 'Time'])
        self._relative_landmarks = None

        if time_limit != 0:
            # otherwise meta classification_meta_models are not needed
            self._meta_models = self._get_meta_models()

    def _get_meta_models(self):
        return {
            f: joblib.load(path.join(self.models_path, f))
            for f in listdir(self.models_path)
        }

    def evaluate_models(self, X, y, meta_data=None):
        ordered_models = self._models_in_predicted_order(meta_data)
        try:
            signal.alarm(self.time_limit)

            for model_class, kwargs in ordered_models:
                model = model_class(**kwargs)
                score, time = self._evaluate_model(model, X, y)
                res = {
                    'Model': model_class.__name__,
                    'Score': score,
                    'Time': time
                }
                self.models_quality = self.models_quality.append(res, ignore_index=True)
        except TimeLimitExceeded:
            pass
        else:
            signal.alarm(0)
        finally:
            self.normalize_scores()
            rls = get_rls(self.models_quality, self.time_accuracy_trade_rate)
            self._relative_landmarks = list(zip(ordered_models, rls))

    def get_best_model(self):
        ordered_models = sorted(self.relative_landmarks, key=lambda x: x[1], reverse=True)
        (best_model, kwargs), rl = ordered_models[0]
        return best_model(**kwargs)

    @property
    def relative_landmarks(self):
        return self._relative_landmarks

    def _evaluate_model(self, model, X, y):
        """Evaluates model performance using cross validation.

        :returns score and processing time.
        """

        start = timer()
        score = cross_val_score(model, X, y, cv=3, scoring=self.score).mean()
        end = timer()
        return score, end - start

    def _models_in_predicted_order(self, meta_data=None):
        """Returns classification_meta_models in performance order, predicted using meta-features.
        If time_limit is zero returns unordered classification_meta_models."""

        if self.time_limit > 0:
            def predicted_landmark(model):
                cls, params = model
                return self._meta_models[cls.__name__].predict(pd.DataFrame(meta_data, index=[0]))

            return sorted(self.models, key=predicted_landmark, reverse=True)
        else:
            return self.models

    @staticmethod
    def score(y, y_pred, **kwargs):
        raise NotImplemented

    def normalize_scores(self):
        pass


class ClassificationEvaluator(BaseEvaluator):
    models = [
        (AdaBoostClassifier, dict()),
        (BernoulliNB, dict()),
        (CalibratedClassifierCV, dict()),
        (DecisionTreeClassifier, dict()),
        (ExtraTreeClassifier, dict()),
        (ExtraTreesClassifier, dict()),
        (GaussianNB, dict()),
        (GradientBoostingClassifier, dict()),
        (KNeighborsClassifier, dict()),
        (LinearSVC, dict()),
        (LogisticRegression, dict()),
        (LogisticRegressionCV, dict()),
        (MLPClassifier, dict()),
        (MultinomialNB, dict()),
        (NearestCentroid, dict()),
        (PassiveAggressiveClassifier, dict(max_iter=1e-3)),
        (Perceptron, dict(max_iter=1e-3)),
        (RandomForestClassifier, dict()),
        (SVC, dict())
    ]
    models_path = path.join(path.dirname(path.realpath(__file__)), 'classification_meta_models')

    score = 'accuracy'


class RegressionEvaluator(BaseEvaluator):
    models = [
        (AdaBoostRegressor, dict()),
        (BaggingRegressor, dict()),
        (BayesianRidge, dict()),
        (DecisionTreeRegressor, dict()),
        (ExtraTreeRegressor, dict()),
        (ExtraTreesRegressor, dict()),
        (GradientBoostingRegressor, dict()),
        (HuberRegressor, dict()),
        (KNeighborsRegressor, dict()),
        (KernelRidge, dict()),
        (LinearRegression, dict()),
        (LinearSVR, dict()),
        (NuSVR, dict()),
        (OrthogonalMatchingPursuit, dict()),
        (OrthogonalMatchingPursuitCV, dict()),
        (PLSRegression, dict()),
        (PassiveAggressiveRegressor, dict(tol=1e-3)),
        (RandomForestRegressor, dict()),
        (SVR, dict()),
    ]
    models_path = path.join(path.dirname(path.realpath(__file__)), 'regression_meta_models')

    score = 'neg_mean_squared_error'

    def normalize_scores(self):
        scores = np.sqrt(-self.models_quality['Score'])
        self.models_quality['Score'] = 1 - scores / scores.max() + 1e-6


def get_evaluator(problem_type, *args, **kwargs):
    if problem_type == ProblemClassifier.CLASSIFICATION:
        return ClassificationEvaluator(*args, **kwargs)
    elif problem_type == ProblemClassifier.REGRESSION:
        return RegressionEvaluator(*args, **kwargs)
    else:
        raise NotImplemented


# Signal processing
class TimeLimitExceeded(Exception):
    pass


def handler(signum, frame):
    raise TimeLimitExceeded


signal.signal(signal.SIGALRM, handler)
