from timeit import default_timer as timer

import pandas as pd
import numpy as np
from scipy.stats.mstats import gmean
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LinearRegression
from sklearn.metrics import make_scorer, mean_squared_error
from sklearn.metrics.scorer import accuracy_scorer
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from model_selection.problem_classification import ProblemClassifier


class BaseMetaExtractor:
    landmarks_models = []

    def __init__(self):
        self.meta_data = {}

    def extract_initial(self, X, y):
        examples, features = X.shape
        numerical = X.select_dtypes(include=[np.number]).columns.shape[0]
        categorical = X.select_dtypes(exclude=[np.number]).columns.shape[0]
        binary = (X.nunique(dropna=False) == 2).sum()
        features_with_nans = (X.count(axis=0) > 0).sum()
        examples_with_nans = (X.count(axis=1) > 0).sum()

        self.meta_data.update({
            'NExamples': examples,
            'NFeatures': features,
            'NNumerical': numerical,
            'NCategorical': categorical,
            'NBinary': binary,
            'NFeaturesWithNANs': features_with_nans,
            'NExamplesWithNANs': examples_with_nans
        })

    def extract_preprocessed(self, X, y):
        stds = X.std(axis=0)
        stds = stds[stds > 0]
        std_ratio = gmean(stds)
        corr_mean = X.corr(method='pearson').abs().values.mean()
        skew_mean = X.skew(axis=0).mean()
        kurt_mean = X.kurtosis(axis=0).mean()

        self.meta_data.update({
            'STDRatio': std_ratio,
            'CorrelationMean': corr_mean,
            'SkewnessMean': skew_mean,
            'KurtosisMean': kurt_mean
        })

        self._extract_landmarks(X, y)

    @staticmethod
    def score(y, y_pred, **kwargs):
        raise NotImplemented

    def _extract_landmarks(self, X, y, sample_size=500):
        sample = X.assign(y=y).sample(min(sample_size, len(y)))
        X, y = sample.drop('y', axis=1), sample['y']

        for i, (model_class, model_kwargs) in enumerate(self.landmarks_models):
            model = model_class(**model_kwargs)
            start = timer()
            score = cross_val_score(model, X, y, cv=5).mean()
            end = timer()
            self.meta_data['lp {}'.format(i)] = score
            self.meta_data['lt {}'.format(i)] = end - start

    def as_df(self):
        return pd.DataFrame(self.meta_data, index=[0])

    def as_dict(self):
        return self.meta_data


class ClassificationMetaExtractor(BaseMetaExtractor):
    landmarks_models = [
        (DecisionTreeClassifier, dict(max_depth=2)),
        (KNeighborsClassifier, dict(n_neighbors=1)),
        (KNeighborsClassifier, dict(n_neighbors=3)),
        (LinearDiscriminantAnalysis, dict())
    ]

    def extract_initial(self, X, y):
        super().extract_initial(X, y)

        classes = y.unique().shape[0]
        y_imbalance = y.value_counts().std()

        self.meta_data.update({
            'NClasses': classes,
            'YImbalance': y_imbalance,
        })

    score = accuracy_scorer


class RegressionMetaExtractor(BaseMetaExtractor):
    landmarks_models = [
        (DecisionTreeRegressor, dict(max_depth=2)),
        (KNeighborsRegressor, dict(n_neighbors=1)),
        (KNeighborsRegressor, dict(n_neighbors=3)),
        (LinearRegression, dict()),
    ]

    def extract_initial(self, X, y):
        super().extract_initial(X, y)

        y_std = y.std()
        bins_counts = pd.cut(y, bins=10).value_counts()
        y_imbalance = bins_counts[bins_counts > 0].std()

        self.meta_data.update({
            'YStd': y_std,
            'YImbalance': y_imbalance,
        })

    score = make_scorer(mean_squared_error, greater_is_better=False)


def get_extractor(problem_type):
    if problem_type == ProblemClassifier.CLASSIFICATION:
        return ClassificationMetaExtractor()
    elif problem_type == ProblemClassifier.REGRESSION:
        return RegressionMetaExtractor()
    else:
        return BaseMetaExtractor()
