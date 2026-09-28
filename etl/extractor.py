"""
================================================================================
ETL PHASE 1: EXTRACTION MODULE
================================================================================
Responsible for ingesting raw data from CSV, validating file integrity,
and logging source schema metadata.
================================================================================
"""

import os
import logging
import pandas as pd

logger = logging.getLogger("Milestone1_ETL")


def extract_raw_data(file_path: str) -> pd.DataFrame:
    """
    Extracts raw housing dataset from the specified CSV file path.
    Validates file existence and returns a pandas DataFrame.
    """
    logger.info("=" * 70)
    logger.info("STEP 1: EXTRACTION PHASE")
    logger.info("=" * 70)

    if not os.path.exists(file_path):
        err_msg = f"Source dataset not found at path: {file_path}"
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)

    logger.info(f"Reading raw dataset from: {file_path}")
    df = pd.read_csv(file_path, dtype={"id": "int64", "zipcode": "str"})

    logger.info("Raw data successfully extracted.")
    logger.info(f"Total records ingested: {len(df):,}")
    logger.info(f"Total attributes detected: {len(df.columns)}")
    logger.info(f"Column list: {list(df.columns)}")
    return df

