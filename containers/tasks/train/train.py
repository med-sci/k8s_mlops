import os
import numpy as np

from os.path import dirname, abspath
from sklearn.model_selection import KFold, train_test_split
from loguru import logger

from ray import tune
from ray.tune.search.optuna import OptunaSearch

from mlbase.utils import read_array, ClientS3

from models import RandomForest
from utils import parse_space_from_file, get_metric

ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
BUCKET_NAME = os.environ.get("BUCKET_NAME")

FEATURES_PATH = os.environ.get("FEATURES_PATH")
TARGET_PATH = os.environ.get("TARGET_PATH")
TMP_TARGET_PATH = os.path.join('/tmp', TARGET_PATH)
TMP_FEATURES_PATH = os.path.join('/tmp', FEATURES_PATH)

N_SPLITS = 5
RANDOM_STATE = 42
MODE = 'regression'
METRIC = 'r2_score'
METRIC_MODE = 'max'
TEST_SIZE = 0.2
SEARCH_SPACE_PATH = os.path.join(dirname(abspath(__file__)), "search_spaces/random_forest.json")

METRIC_TO_OPTIMIZE = f'{METRIC}_cv_mean'
METRIC_FUNC = get_metric(METRIC)

s3_client = ClientS3(
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY
)

logger.info(
    f"Loading features {FEATURES_PATH} from"
    f" {BUCKET_NAME} bucket to {TMP_FEATURES_PATH}"
)
s3_client.load_from_s3(
    bucket=BUCKET_NAME,
    remote_path=FEATURES_PATH,
    local_path=TMP_FEATURES_PATH
)

logger.info(
    f"Loading target {TARGET_PATH} from"
    f" {BUCKET_NAME} bucket to {TMP_TARGET_PATH}")
s3_client.load_from_s3(
    bucket=BUCKET_NAME,
    remote_path=TARGET_PATH,
    local_path=TMP_TARGET_PATH
)

logger.info(f"Loading features from {TMP_FEATURES_PATH}")
features = read_array(TMP_FEATURES_PATH)

logger.info(f"Loading target from {TMP_TARGET_PATH}")
target = read_array(TMP_TARGET_PATH)

def trainable(params):
    features_train, features_test, target_train, target_test = train_test_split(
        features, target, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    kfd = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    models = []
    scores = []
    for fold, (train_index, test_index) in enumerate(kfd.split(features_train)):
        logger.info(f"Starting training on fold {fold}")

        model = RandomForest(mode=MODE, params=params)
        model.fit(X=features_train[train_index], y=target_train[train_index])

        fold_preds = model.predict(features_train[test_index])
        score = METRIC_FUNC(y_true=target_train[test_index], y_pred=fold_preds)
        logger.info(f"{METRIC} for fold {fold}: {score}")

        models.append(model)
        scores.append(score)

    test_preds = np.column_stack([model.predict(features_test) for model in models])
    mean_test_preds = np.mean(test_preds, axis=1)
    r2_score_test = METRIC_FUNC(target_test, mean_test_preds)

    return {f'{METRIC}_test': r2_score_test, METRIC_TO_OPTIMIZE: np.mean(scores)}

search_space = parse_space_from_file(SEARCH_SPACE_PATH)
search_algorithm = OptunaSearch(
    metric=METRIC_TO_OPTIMIZE,
    mode=METRIC_MODE
)

tune_config = tune.TuneConfig(
    mode=METRIC_MODE,
    metric=METRIC_TO_OPTIMIZE,
    num_samples=100,
    search_alg=search_algorithm
)

tuner = tune.Tuner(
    trainable,
    param_space=search_space,
    tune_config=tune_config,
)
results = tuner.fit()

print(
    results.get_best_result(
        metric=METRIC_TO_OPTIMIZE,
        mode=METRIC_MODE
    ).metrics_dataframe
)



