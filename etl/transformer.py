"""
================================================================================
ETL PHASE 2: CLEANSING & TRANSFORMATION MODULE
================================================================================
Responsible for resolving data anomalies, validating missing values,
standardizing datetime formats to ISO-8601, and deriving analytical metrics.
================================================================================
"""

import logging
import pandas as pd

logger = logging.getLogger("Milestone1_ETL")


def cleanse_and_transform_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleanses anomalies, formats dates, handles data types, and derives metrics.

    Key Stewardship Operations:
      1. Anomaly Resolution:
         - Identifies and corrects Property ID 2402100895 (33-bedroom data-entry typo
           on a 1,620 sqft house, corrected to 3 bedrooms).
      2. Completeness Check:
         - Validates column null counts.
      3. Date Standardization:
         - Parses raw 'YYYYMMDDT000000' into ISO-8601 and extracts date dimension features.
      4. Feature Engineering:
         - Computes price_per_sqft.
         - Derives boolean flags (has_basement, is_renovated).
         - Standardizes postal codes and coordinates.
    """
    logger.info("=" * 70)
    logger.info("STEP 2: DATA CLEANSING & TRANSFORMATION PHASE")
    logger.info("=" * 70)

    df_clean = df.copy()

    # 2.1 Audit Nulls & Data Completeness
    null_summary = df_clean.isnull().sum()
    null_cols = null_summary[null_summary > 0]
    if null_cols.empty:
        logger.info("Data Completeness Audit: No null values detected in raw source.")
    else:
        logger.warning(f"Data Completeness Audit: Null values detected:\n{null_cols}")
        df_clean = df_clean.dropna()
        logger.info(f"Rows remaining after dropping nulls: {len(df_clean):,}")

    # 2.2 Anomaly Handling: Bedroom Data-Entry Error Fix
    bedroom_outliers = df_clean[df_clean["bedrooms"] == 33]
    if not bedroom_outliers.empty:
        for idx, row in bedroom_outliers.iterrows():
            logger.warning(
                f"[ANOMALY AUDIT] Detected bedroom data-entry typo: "
                f"Property ID {row['id']} has bedrooms={row['bedrooms']} "
                f"for sqft_living={row['sqft_living']}. Correcting bedrooms to 3."
            )
            df_clean.at[idx, "bedrooms"] = 3

    logger.info(f"Bedrooms range after correction: min={df_clean['bedrooms'].min()}, max={df_clean['bedrooms'].max()}")

    # 2.3 Date Cleansing & Standardization
    logger.info("Standardizing date format from raw 'YYYYMMDDT000000' to ISO-8601...")
    parsed_dates = pd.to_datetime(df_clean["date"], format="%Y%m%dT%H%M%S", errors="coerce")

    df_clean["sale_datetime"] = parsed_dates
    df_clean["full_date"] = parsed_dates.dt.strftime("%Y-%m-%d")
    df_clean["date_id"] = parsed_dates.dt.strftime("%Y%m%d").astype(int)
    df_clean["year"] = parsed_dates.dt.year
    df_clean["quarter"] = parsed_dates.dt.quarter
    df_clean["month"] = parsed_dates.dt.month
    df_clean["month_name"] = parsed_dates.dt.strftime("%B")
    df_clean["day"] = parsed_dates.dt.day
    df_clean["day_of_week"] = parsed_dates.dt.dayofweek + 1  # 1=Monday, 7=Sunday
    df_clean["day_name"] = parsed_dates.dt.strftime("%A")
    df_clean["is_weekend"] = parsed_dates.dt.dayofweek.isin([5, 6]).astype(int)

    # 2.4 Zipcode Standardization
    df_clean["zipcode"] = df_clean["zipcode"].astype(str).str.strip().str.zfill(5)

    # 2.5 Derived Engineering Metrics
    df_clean["price_per_sqft"] = (df_clean["price"] / df_clean["sqft_living"]).round(2)
    df_clean["has_basement"] = (df_clean["sqft_basement"] > 0).astype(int)
    df_clean["is_renovated"] = (df_clean["yr_renovated"] > 0).astype(int)

    # Precision formatting
    df_clean["bathrooms"] = df_clean["bathrooms"].round(2)
    df_clean["floors"] = df_clean["floors"].round(1)
    df_clean["lat"] = df_clean["lat"].round(5)
    df_clean["long"] = df_clean["long"].round(5)

    total_rows = len(df_clean)
    logger.info(f"Total sales transactions processed: {total_rows:,}")
    logger.info(f"Unique property entities identified: {df_clean['id'].nunique():,}")
    logger.info("Data cleansing and feature engineering successfully completed.")

    return df_clean

