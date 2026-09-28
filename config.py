"""
================================================================================
CONFIGURATION MODULE - DATA WAREHOUSE ETL PIPELINE
================================================================================
Group 10: Real Estate Property Listing & Regional Market Value Warehouse
Instructor: Prof. Rob Malitao
================================================================================
"""

import os
import sys
import logging

# Project Directories & File Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE_PATH = os.path.join(BASE_DIR, "house_data.csv")
SQLITE_DB_PATH = os.path.join(BASE_DIR, "warehouse.db")
AUDIT_LOG_PATH = os.path.join(BASE_DIR, "milestone1_log.txt")

# MongoDB Connection Parameters
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "real_estate_warehouse"
MONGO_COLL_NAME = "property_architectural_features"


def setup_logger(name: str = "Milestone1_ETL") -> logging.Logger:
    """
    Configures and returns a centralized logger that outputs simultaneously
    to stdout and the milestone1_log.txt audit file.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(AUDIT_LOG_PATH, mode="w", encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        log_formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(log_formatter)
        console_handler.setFormatter(log_formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

