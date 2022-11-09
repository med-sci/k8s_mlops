import os
import pandas as pd
from typing import Literal, List
from loguru import logger
from mlbase.utils import write_array, ClientS3
from preprocess.utils import (
    drop_duplicates,
    get_dataframe,
    drop_nan,
    calculate_features,
    get_target,
    log_10_target
)
TASK: Literal["Train", "Score"] = os.environ.get("TASK")
SMILES: List[str] = os.environ.get("SMILES").split()

ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
BUCKET_NAME = os.environ.get("BUCKET_NAME")

DATA_PATH = os.environ.get("DATA_PATH")
TRIM_DATA = os.environ.get("TRIM_DATA")
TARGET_PATH = os.environ.get("TARGET_PATH")
TARGET_NAME = os.environ.get("TARGET_NAME")
FEATURES_PATH = os.environ.get("FEATURES_PATH")
SMILES_COLUMN_NAME = os.environ.get("SMILES_COLUMN_NAME")
LOG10_TARGET = os.environ.get("LOG10_TARGET")

TMP_FEATURES_PATH = os.path.join('/tmp', FEATURES_PATH)

logger.info(f"Instantiating client..")
s3_client = ClientS3(
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY
)
if TASK == "Train":
    TMP_DATA_PATH = os.path.join('/tmp', DATA_PATH)
    TMP_TARGET_PATH = os.path.join('/tmp', TARGET_PATH)

    logger.info(
        f"Loading data {DATA_PATH} from"
        f"{BUCKET_NAME} bucket to {TMP_DATA_PATH}"
    )
    s3_client.load_from_s3(
        bucket=BUCKET_NAME,
        remote_path=DATA_PATH,
        local_path=TMP_DATA_PATH
    )

    logger.info(f"Loading data from {TMP_DATA_PATH}")
    dataframe = get_dataframe(TMP_DATA_PATH)

    if TRIM_DATA == 'True':
        logger.info(f"Removing duplicates. Initial shape: {dataframe.shape}")
        dataframe = drop_duplicates(dataframe)
        logger.info(f"Final shape: {dataframe.shape}")

        logger.info(f"Removing NaN initial shape: {dataframe.shape}")
        dataframe = drop_nan(dataframe)
        logger.info(f"Final shape: {dataframe.shape}")


    logger.info(f"Loading {TARGET_NAME}")
    target = get_target(dataframe=dataframe, target=TARGET_NAME)


    if LOG10_TARGET == 'True':
        logger.info("Converting target values to log10")
        target = log_10_target(target)


    logger.info(f"Writing target {TARGET_NAME} to {TMP_TARGET_PATH}")
    write_array(array=target, path=TMP_TARGET_PATH)

    logger.info(
        f"Uploading {TARGET_NAME} from {TMP_TARGET_PATH} to"
        f" {TARGET_PATH} in {BUCKET_NAME}")
    s3_client.upload_to_s3(
        bucket=BUCKET_NAME,
        remote_path=TARGET_PATH,
        local_path=TMP_TARGET_PATH
    )

elif TASK == "Score":
    dataframe = pd.DataFrame({SMILES_COLUMN_NAME: SMILES})

logger.info("Calculating features")
features = calculate_features(dataframe=dataframe, smiles_col=SMILES_COLUMN_NAME)

logger.info(f"Writing features to {TMP_FEATURES_PATH}")
write_array(array=features, path=TMP_FEATURES_PATH)

logger.info(
    f"Uploading features from {TMP_FEATURES_PATH} to"
    f" {FEATURES_PATH} in {BUCKET_NAME} bucket")
s3_client.upload_to_s3(
    bucket=BUCKET_NAME,
    remote_path=FEATURES_PATH,
    local_path=TMP_FEATURES_PATH
)
