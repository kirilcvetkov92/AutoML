import os

from sklearn.pipeline import Pipeline
import pandas as pd

from .model_selection.model_selection import get_evaluator
from .preprocessing.preprocessing import Preprocessing
from .model_selection.problem_classification import ProblemClassifier
from .model_selection.metadata_extraction import get_extractor


class AutoML:

    def __init__(self,
                 max_time=600,
                 time_accuracy_trade_rate=0.05,
                 problem_type=ProblemClassifier.REGRESSION,
                 ordinal_features=None,
                 dimensionality_reduction=None,
                 initial_preprocessing_pipeline=None):
        """

        :param max_time: time limit for processing in seconds
        :param time_accuracy_trade_rate: amount of accuracy(%) willing to trade for 10 times speed-up.
        :param problem_type: class of the problem (CLASSIFICATION/REGRESSION)
        :param ordinal_features: dictionary in format {feature_name: [labels_in_order]}
        :param dimensionality_reduction: weather to use dimensionality reduction
        :param initial_preprocessing_pipeline: custom preprocessing pipeline used at the beginning of the resulting pipeline
        """
        self.max_time = max_time
        self.problem_type = problem_type
        self.ordinal_features = ordinal_features
        self.dimensionality_reduction = dimensionality_reduction
        self.initial_preprocessing_pipeline = initial_preprocessing_pipeline

        self.pipeline = None
        self.meta_extractor = get_extractor(problem_type)
        self.model_evaluator = get_evaluator(problem_type, time_limit=max_time,
                                             time_accuracy_trade_rate=time_accuracy_trade_rate)

    def fit(self, X, y):
        steps = []

        # Initial pipeline
        if self.initial_preprocessing_pipeline:
            steps.append(('Initial pipeline', self.initial_preprocessing_pipeline))
            X = self.initial_preprocessing_pipeline.fit_transform(X, y)

        self.meta_extractor.extract_initial(X, y)

        # Preprocessing pipeline
        preprocessing_pipeline = Preprocessing(ordinal_features=self.ordinal_features).get_pipeline(X, y)
        if preprocessing_pipeline:
            steps.append(('Preprocessing pipeline', preprocessing_pipeline))
            X = preprocessing_pipeline.fit_transform(X, y)

        self.meta_extractor.extract_preprocessed(X, y)

        self.model_evaluator.evaluate_models(X, y, self.meta_extractor.as_dict())

        model = self.model_evaluator.get_best_model()
        model.fit(X, y)
        steps.append(('Model', model))

        self.pipeline = Pipeline(steps)
        return self

    def transform(self, X):
        return self.pipeline.transform(X)

    def predict(self, X):
        return self.pipeline.predict(X)

    def describe(self):
        self._describe_estimator(estimator=self.pipeline)

    def _describe_estimator(self, estimator, level=0):
        if isinstance(estimator, Pipeline):
            for name, estimator in estimator.steps:
                print('\t' * level, name, ':', sep='')
                self._describe_estimator(estimator, level + 1)
        else:
            print('\t' * level, estimator, sep='')

    def save_meta_data(self, file_path, task_name):
        meta_data = self.meta_extractor.as_dict()
        landmarks = self.model_evaluator.relative_landmarks

        meta_data['Task'] = task_name
        meta_data.move_to_end('Task', last=False)

        meta_data.update({cls.__name__: rl for (cls, kw), rl in landmarks})

        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
        else:
            df = pd.DataFrame(columns=meta_data.keys())

        df.append(meta_data, ignore_index=True).to_csv(file_path, index=False)
