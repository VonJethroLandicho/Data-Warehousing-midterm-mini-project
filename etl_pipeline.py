"""
================================================================================
DATA WAREHOUSING (LAB/LEC) - LESSON 6 MIDTERM MINI-PROJECT
GROUP 10: REAL ESTATE PROPERTY LISTING & REGIONAL MARKET VALUE WAREHOUSE
MILESTONE 1: MASTER ETL PIPELINE ORCHESTRATOR
================================================================================
Author / Group: Group 10
Instructor: Prof. Rob Malitao
Date: September 2026

Description:
  Main entry point for Milestone 1. Orchestrates modular ETL components:
    1. etl.extractor       -> Raw data extraction and source validation
    2. etl.transformer     -> Data cleansing, anomaly resolution, feature engineering
    3. etl.sqlite_loader   -> Relational star schema warehouse loading
    4. etl.mongo_loader    -> Document store hierarchical ingestion & indexing
    5. etl.verifier        -> Cross-engine auditing and sample OLAP validation
================================================================================
"""

import sys
from datetime import datetime

from config import (
    CSV_FILE_PATH,
    SQLITE_DB_PATH,
    AUDIT_LOG_PATH,
    MONGO_URI,
    MONGO_DB_NAME,
    MONGO_COLL_NAME,
    setup_logger
)
from etl import (
    extract_raw_data,
    cleanse_and_transform_data,
    load_sqlite_warehouse,
    load_mongodb_documents,
    verify_and_audit
)

# Initialize centralized logger (writes to stdout and milestone1_log.txt)
logger = setup_logger()


def run_pipeline():
    """
    Executes the complete end-to-end ETL workflow sequentially.
    """
    start_time = datetime.now()
    logger.info(f"Starting Milestone 1 Master ETL Pipeline at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Target Database: {SQLITE_DB_PATH}")
    logger.info(f"Target Mongo Collection: {MONGO_DB_NAME}.{MONGO_COLL_NAME}")
    logger.info(f"Audit Trail: {AUDIT_LOG_PATH}")

    try:
        # Step 1: Extraction
        df_raw = extract_raw_data(CSV_FILE_PATH)

        # Step 2: Cleansing & Transformation
        df_clean = cleanse_and_transform_data(df_raw)

        # Step 3: Relational Star Schema Loading (SQLite)
        load_sqlite_warehouse(df_clean, SQLITE_DB_PATH)

        # Step 4: Document Store Ingestion (MongoDB)
        load_mongodb_documents(df_clean, MONGO_URI, MONGO_DB_NAME, MONGO_COLL_NAME)

        # Step 5: Verification & Auditing
        verify_and_audit(SQLITE_DB_PATH, MONGO_URI, MONGO_DB_NAME, MONGO_COLL_NAME)

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Master ETL Pipeline finished successfully in {elapsed:.2f} seconds.")

    except Exception as e:
        logger.exception(f"Pipeline execution aborted due to unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_pipeline()
