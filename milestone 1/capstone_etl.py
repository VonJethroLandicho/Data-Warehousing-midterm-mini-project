"""
================================================================================
DATA WAREHOUSING (LEC/LAB) - LESSON 8: FINAL PROJECT
ENTERPRISE MULTI-ENGINE DATA WAREHOUSE & BI SYSTEM
MILESTONE 1: MASTER ETL & DATA GOVERNANCE PIPELINE (capstone_etl.py)
================================================================================
Group 10: Real Estate Property Listing & Regional Market Value Warehouse
Instructor: Prof. Rob Malitao
Date: October 2026
================================================================================
Description:
  Automated production-grade ETL script orchestrating Milestone 1 deliverables:
    1. Automated extraction from operational landing zone (./landing_zone/).
    2. Comprehensive data cleansing: duplicate dropping, null key handling,
       string/currency symbol stripping, and ISO datetime standardization.
    3. Dual-target concurrent loading into SQLite (enterprise_warehouse.db)
       under strict DDL constraints and MongoDB (real_estate_warehouse).
    4. Implementation and testing of MongoDB strict $jsonSchema validation rules
       (validationLevel='strict', validationAction='error').
    5. Database-level data governance verification testing (CHECK constraints,
       Foreign Key referential integrity, and document rejection tests).
    6. Detailed audit logging tracking pre- and post-cleansing metrics.
================================================================================
"""

import os
import sys
import re
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import WriteError, OperationFailure

# ==============================================================================
# 1. PATH CONFIGURATION & AUDIT LOGGER SETUP
# ==============================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
LANDING_ZONE_DIR = os.path.join(CURRENT_DIR, "landing_zone")

RAW_SALES_CSV = os.path.join(LANDING_ZONE_DIR, "raw_property_sales.csv")
RAW_FEEDBACK_JSON = os.path.join(LANDING_ZONE_DIR, "raw_property_feedback.json")

SQLITE_WAREHOUSE_PATH = os.path.join(CURRENT_DIR, "enterprise_warehouse.db")
AUDIT_LOG_PATH = os.path.join(CURRENT_DIR, "etl_execution_log.txt")

MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "real_estate_warehouse"
MONGO_COLL_SALES = "sales_documents"
MONGO_COLL_FEEDBACK = "feedback_documents"


class AuditLogger:
    """Centralized logger writing concurrently to terminal and audit log file."""
    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log_file = open(log_path, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.terminal.flush()
        self.log_file.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def log(self, message=""):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"
        self.write(formatted)

    def banner(self, title):
        sep = "=" * 80
        self.write(f"\n{sep}\n {title.upper()}\n{sep}\n")

    def section(self, subtitle):
        self.write(f"\n--- {subtitle} ---\n")

    def close(self):
        if not self.log_file.closed:
            self.log_file.close()


logger = AuditLogger(AUDIT_LOG_PATH)


# ==============================================================================
# 2. DATA EXTRACTION FROM LANDING ZONE
# ==============================================================================
def extract_landing_zone_data():
    """
    Extracts raw operational data from CSV and JSON in the landing zone.
    """
    logger.banner("Phase 1: Automated Landing Zone Extraction")
    logger.log(f"Extracting raw property sales from: {RAW_SALES_CSV}")
    
    if not os.path.exists(RAW_SALES_CSV):
        raise FileNotFoundError(f"Landing zone CSV file missing: {RAW_SALES_CSV}")
    
    df_raw_sales = pd.read_csv(RAW_SALES_CSV, dtype=str)
    raw_sales_count = len(df_raw_sales)
    logger.log(f"Successfully extracted {raw_sales_count:,} raw sales records.")

    logger.log(f"Extracting raw feedback logs from: {RAW_FEEDBACK_JSON}")
    if not os.path.exists(RAW_FEEDBACK_JSON):
        raise FileNotFoundError(f"Landing zone JSON file missing: {RAW_FEEDBACK_JSON}")

    with open(RAW_FEEDBACK_JSON, "r", encoding="utf-8") as f:
        raw_feedback_data = json.load(f)
    raw_feedback_count = len(raw_feedback_data)
    logger.log(f"Successfully extracted {raw_feedback_count:,} raw feedback documents.")

    return df_raw_sales, raw_feedback_data, raw_sales_count, raw_feedback_count


# ==============================================================================
# 3. DATA CLEANSING & TRANSFORMATION LOGIC
# ==============================================================================
def clean_currency_string(val):
    """Strips currency symbols ($), commas, and spaces, converting to float."""
    if pd.isna(val) or val is None:
        return np.nan
    val_str = str(val).strip().replace("$", "").replace(",", "").strip()
    try:
        return float(val_str)
    except ValueError:
        return np.nan


def parse_mixed_date(val):
    """
    Standardizes mixed date formats (YYYYMMDDT000000, MM/DD/YYYY, YYYY-MM-DD,
    DD-MM-YYYY, or epoch timestamp) into a canonical (YYYY-MM-DD, date_id) tuple.
    """
    if pd.isna(val) or val is None or str(val).strip() in ("", "NULL", "None", "nan"):
        return None, None

    val_str = str(val).strip()

    # 1. Operational raw format: 20141013T000000
    if "T" in val_str:
        val_str = val_str.split("T")[0]

    # 2. Check if epoch timestamp (integer digits >= 9)
    if val_str.isdigit() and len(val_str) >= 9:
        try:
            dt = datetime.fromtimestamp(int(val_str))
            return dt.strftime("%Y-%m-%d"), int(dt.strftime("%Y%m%d"))
        except Exception:
            pass

    # 3. Try parsing known string date patterns
    date_patterns = [
        "%Y%m%d",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%m-%d-%Y"
    ]

    for pat in date_patterns:
        try:
            dt = datetime.strptime(val_str, pat)
            return dt.strftime("%Y-%m-%d"), int(dt.strftime("%Y%m%d"))
        except ValueError:
            continue

    return None, None


def cleanse_sales_data(df_raw):
    """
    Cleanses raw sales records:
      - Drops duplicate rows
      - Drops missing / null primary and critical keys
      - Cleans currency strings ($ and commas)
      - Standardizes mixed date formats to ISO-8601 YYYY-MM-DD
      - Validates and filters out business rule violations (negative prices, zero sqft)
      - Computes derived attributes (price_per_sqft, is_renovated, has_basement)
    """
    logger.banner("Phase 2A: Cleansing & Transforming Relational Sales Data")
    initial_count = len(df_raw)
    logger.log(f"Input raw sales row count: {initial_count:,}")

    # Step 1: Duplicate dropping
    df = df_raw.drop_duplicates()
    duplicates_dropped = initial_count - len(df)
    logger.log(f"Duplicate rows identified and dropped: {duplicates_dropped:,}")

    # Step 2: Critical Key Validation (Property ID and Price presence)
    valid_id_mask = df["id"].notna() & df["id"].str.strip().str.isdigit()
    null_keys_dropped = len(df) - valid_id_mask.sum()
    df = df[valid_id_mask].copy()
    df["property_id"] = df["id"].astype(np.int64)
    logger.log(f"Records with missing/corrupted property IDs dropped: {null_keys_dropped:,}")

    # Step 3: Currency & Numeric Cleansing
    df["price_clean"] = df["price"].apply(clean_currency_string)
    df["sqft_living_clean"] = pd.to_numeric(df["sqft_living"], errors="coerce")
    df["sqft_lot_clean"] = pd.to_numeric(df["sqft_lot"], errors="coerce")
    df["bedrooms_clean"] = pd.to_numeric(df["bedrooms"], errors="coerce").fillna(0).astype(int)
    df["bathrooms_clean"] = pd.to_numeric(df["bathrooms"], errors="coerce").fillna(1.0).astype(float)
    df["floors_clean"] = pd.to_numeric(df["floors"], errors="coerce").fillna(1.0).astype(float)
    df["waterfront_clean"] = pd.to_numeric(df["waterfront"], errors="coerce").fillna(0).astype(int)
    df["view_clean"] = pd.to_numeric(df["view"], errors="coerce").fillna(0).astype(int)
    df["condition_clean"] = pd.to_numeric(df["condition"], errors="coerce").fillna(3).astype(int)
    df["grade_clean"] = pd.to_numeric(df["grade"], errors="coerce").fillna(7).astype(int)
    df["sqft_above_clean"] = pd.to_numeric(df["sqft_above"], errors="coerce").fillna(0).astype(int)
    df["sqft_basement_clean"] = pd.to_numeric(df["sqft_basement"], errors="coerce").fillna(0).astype(int)
    df["yr_built_clean"] = pd.to_numeric(df["yr_built"], errors="coerce").fillna(1970).astype(int)
    df["yr_renovated_clean"] = pd.to_numeric(df["yr_renovated"], errors="coerce").fillna(0).astype(int)
    df["lat_clean"] = pd.to_numeric(df["lat"], errors="coerce")
    df["long_clean"] = pd.to_numeric(df["long"], errors="coerce")
    df["sqft_living15_clean"] = pd.to_numeric(df["sqft_living15"], errors="coerce").fillna(df["sqft_living_clean"]).astype(int)
    df["sqft_lot15_clean"] = pd.to_numeric(df["sqft_lot15"], errors="coerce").fillna(df["sqft_lot_clean"]).astype(int)

    # Clean zipcode string
    df["zipcode_clean"] = df["zipcode"].astype(str).str.strip().str.replace(r"[^\d]", "", regex=True)
    df["zipcode_clean"] = df["zipcode_clean"].str.zfill(5)

    # Step 4: ISO Date Standardization
    date_tuples = [parse_mixed_date(d) for d in df["date"]]
    df["full_date"] = [t[0] for t in date_tuples]
    df["date_id"] = [t[1] for t in date_tuples]

    # Filter records with unparseable dates
    valid_date_mask = df["date_id"].notna()
    invalid_dates_dropped = len(df) - valid_date_mask.sum()
    df = df[valid_date_mask].copy()
    df["date_id"] = df["date_id"].astype(int)
    logger.log(f"Records with invalid/missing date formats dropped: {invalid_dates_dropped:,}")

    # Step 5: Data Governance Business Rule Filtering
    # Rules: price > 0, sqft_living > 0, grade between 1 and 13, condition between 1 and 5
    valid_business_mask = (
        (df["price_clean"] > 0) &
        (df["sqft_living_clean"] > 0) &
        (df["sqft_lot_clean"] > 0) &
        (df["grade_clean"].between(1, 13)) &
        (df["condition_clean"].between(1, 5)) &
        (df["view_clean"].between(0, 4)) &
        (df["waterfront_clean"].isin([0, 1])) &
        (df["lat_clean"].between(-90, 90)) &
        (df["long_clean"].between(-180, 180)) &
        (df["zipcode_clean"].str.len() == 5)
    )
    constraint_violators_dropped = len(df) - valid_business_mask.sum()
    df = df[valid_business_mask].copy()
    logger.log(f"Constraint violators (negative prices, zero sqft, out-of-range bounds) dropped: {constraint_violators_dropped:,}")

    # Step 6: Feature Engineering
    df["price_per_sqft"] = (df["price_clean"] / df["sqft_living_clean"]).round(2)
    df["is_renovated"] = (df["yr_renovated_clean"] > 0).astype(int)
    df["has_basement"] = (df["sqft_basement_clean"] > 0).astype(int)

    # Step 7: Deduplicate transactional sales by (property_id, date_id)
    before_txn_dedup = len(df)
    df = df.drop_duplicates(subset=["property_id", "date_id"])
    txn_dedup_dropped = before_txn_dedup - len(df)
    logger.log(f"Duplicate property transactions on same date dropped: {txn_dedup_dropped:,}")

    final_clean_sales_count = len(df)
    logger.log(f"Final clean sales record count: {final_clean_sales_count:,}")

    # Summary table in log
    logger.section("Sales Cleansing Audit Breakdown")
    logger.write(f"  • Raw Records Extracted:           {initial_count:>8,}\n")
    logger.write(f"  • Exact Duplicate Rows Dropped:    {duplicates_dropped:>8,}\n")
    logger.write(f"  • Missing/Null Key Rows Dropped:   {null_keys_dropped:>8,}\n")
    logger.write(f"  • Unparseable Date Rows Dropped:   {invalid_dates_dropped:>8,}\n")
    logger.write(f"  • Business Rule Violators Dropped: {constraint_violators_dropped:>8,}\n")
    logger.write(f"  • Same-Day Duplicate Txns Dropped: {txn_dedup_dropped:>8,}\n")
    logger.write(f"  • Clean Records Ready for Loading: {final_clean_sales_count:>8,}\n")

    return df


def cleanse_feedback_data(raw_feedback):
    """
    Cleanses semi-structured feedback & inspection documents:
      - Drops duplicate review IDs
      - Filters out missing required fields
      - Standardizes dates to ISO-8601 (YYYY-MM-DD)
      - Filters out ratings outside [1, 5]
    """
    logger.banner("Phase 2B: Cleansing Semi-Structured Feedback Documents")
    initial_count = len(raw_feedback)
    logger.log(f"Input raw feedback document count: {initial_count:,}")

    clean_docs = []
    seen_ids = set()
    dup_count = 0
    missing_key_count = 0
    invalid_rating_count = 0
    invalid_date_count = 0

    required_keys = ["review_id", "property_id", "review_date", "rating", "reviewer_category", "inspection_passed"]
    allowed_categories = {"Buyer", "Seller", "Licensed Inspector", "Certified Appraiser", "Tenant"}

    for doc in raw_feedback:
        # Check required keys
        if not all(k in doc for k in required_keys):
            missing_key_count += 1
            continue

        review_id = str(doc["review_id"]).strip()
        if review_id in seen_ids:
            dup_count += 1
            continue
        seen_ids.add(review_id)

        # Validate rating
        try:
            rating = int(doc["rating"])
            if not (1 <= rating <= 5):
                invalid_rating_count += 1
                continue
        except (ValueError, TypeError):
            invalid_rating_count += 1
            continue

        # Validate & parse date
        iso_date, _ = parse_mixed_date(doc["review_date"])
        if not iso_date:
            invalid_date_count += 1
            continue

        # Standardize category
        category = str(doc["reviewer_category"]).strip()
        if category not in allowed_categories:
            category = "Buyer"

        # Standardize document structure
        clean_doc = {
            "review_id": review_id,
            "property_id": int(doc["property_id"]),
            "review_date": iso_date,
            "rating": rating,
            "reviewer_category": category,
            "inspection_passed": bool(doc["inspection_passed"]),
            "sentiment_score": float(doc.get("sentiment_score", 0.0)),
            "comments": str(doc.get("comments", "")).strip(),
            "architectural_highlights": list(doc.get("architectural_highlights", []))
        }
        clean_docs.append(clean_doc)

    final_clean_feedback_count = len(clean_docs)
    logger.log(f"Final clean feedback document count: {final_clean_feedback_count:,}")

    logger.section("Feedback Cleansing Audit Breakdown")
    logger.write(f"  • Raw Documents Extracted:        {initial_count:>8,}\n")
    logger.write(f"  • Duplicate Review IDs Dropped:   {dup_count:>8,}\n")
    logger.write(f"  • Missing Required Keys Dropped:  {missing_key_count:>8,}\n")
    logger.write(f"  • Out-of-Bounds Ratings Dropped:  {invalid_rating_count:>8,}\n")
    logger.write(f"  • Unparseable Date Docs Dropped:  {invalid_date_count:>8,}\n")
    logger.write(f"  • Clean Documents Ready for Mongo:{final_clean_feedback_count:>8,}\n")

    return clean_docs


# ==============================================================================
# 4. RELATIONAL STAR SCHEMA SETUP & LOADING (SQLITE)
# ==============================================================================
def setup_sqlite_schema(conn):
    """
    Creates the relational Star Schema with explicit Primary Keys, Foreign Keys,
    and CHECK constraints enforcing data governance.
    """
    logger.section("Initializing Relational Star Schema in SQLite (enterprise_warehouse.db)")
    cursor = conn.cursor()

    # Enable Foreign Key enforcement
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")

    # Drop existing tables cleanly for reproducible warehouse builds
    cursor.execute("DROP TABLE IF EXISTS fact_property_sales;")
    cursor.execute("DROP VIEW IF EXISTS fact_sales;")
    cursor.execute("DROP TABLE IF EXISTS dim_property;")
    cursor.execute("DROP TABLE IF EXISTS dim_location;")
    cursor.execute("DROP TABLE IF EXISTS dim_condition_grade;")
    cursor.execute("DROP TABLE IF EXISTS dim_date;")

    # Table 1: dim_property
    cursor.execute("""
        CREATE TABLE dim_property (
            property_id INTEGER PRIMARY KEY,
            yr_built INTEGER NOT NULL CHECK (yr_built BETWEEN 1800 AND 2050),
            yr_renovated INTEGER NOT NULL CHECK (yr_renovated >= 0),
            is_renovated INTEGER NOT NULL CHECK (is_renovated IN (0, 1)),
            sqft_living15 INTEGER NOT NULL CHECK (sqft_living15 > 0),
            sqft_lot15 INTEGER NOT NULL CHECK (sqft_lot15 > 0)
        );
    """)

    # Table 2: dim_location
    cursor.execute("""
        CREATE TABLE dim_location (
            location_id INTEGER PRIMARY KEY AUTOINCREMENT,
            zipcode TEXT NOT NULL,
            latitude REAL NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
            longitude REAL NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
            UNIQUE(zipcode, latitude, longitude)
        );
    """)

    # Table 3: dim_condition_grade
    cursor.execute("""
        CREATE TABLE dim_condition_grade (
            grade_condition_id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade INTEGER NOT NULL CHECK (grade BETWEEN 1 AND 13),
            condition INTEGER NOT NULL CHECK (condition BETWEEN 1 AND 5),
            view INTEGER NOT NULL CHECK (view BETWEEN 0 AND 4),
            waterfront INTEGER NOT NULL CHECK (waterfront IN (0, 1)),
            UNIQUE(grade, condition, view, waterfront)
        );
    """)

    # Table 4: dim_date
    cursor.execute("""
        CREATE TABLE dim_date (
            date_id INTEGER PRIMARY KEY,
            full_date TEXT NOT NULL,
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
            month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
            month_name TEXT NOT NULL,
            day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
            day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
            day_name TEXT NOT NULL,
            is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
        );
    """)

    # Central Fact Table: fact_property_sales
    cursor.execute("""
        CREATE TABLE fact_property_sales (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            date_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            grade_condition_id INTEGER NOT NULL,
            price REAL NOT NULL CHECK (price > 0.0),
            sqft_living INTEGER NOT NULL CHECK (sqft_living > 0),
            sqft_lot INTEGER NOT NULL CHECK (sqft_lot > 0),
            price_per_sqft REAL NOT NULL CHECK (price_per_sqft > 0.0),
            bedrooms INTEGER NOT NULL CHECK (bedrooms >= 0),
            bathrooms REAL NOT NULL CHECK (bathrooms >= 0.0),
            floors REAL NOT NULL CHECK (floors > 0.0),
            sqft_above INTEGER NOT NULL CHECK (sqft_above >= 0),
            sqft_basement INTEGER NOT NULL CHECK (sqft_basement >= 0),
            has_basement INTEGER NOT NULL CHECK (has_basement IN (0, 1)),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (property_id) REFERENCES dim_property (property_id) ON DELETE RESTRICT,
            FOREIGN KEY (date_id) REFERENCES dim_date (date_id) ON DELETE RESTRICT,
            FOREIGN KEY (location_id) REFERENCES dim_location (location_id) ON DELETE RESTRICT,
            FOREIGN KEY (grade_condition_id) REFERENCES dim_condition_grade (grade_condition_id) ON DELETE RESTRICT
        );
    """)

    # Create View alias fact_sales for universal prompt compatibility
    cursor.execute("CREATE VIEW fact_sales AS SELECT * FROM fact_property_sales;")

    conn.commit()
    logger.log("Created tables: dim_property, dim_location, dim_condition_grade, dim_date, fact_property_sales (and view fact_sales).")


def load_sqlite_warehouse(df_clean, db_path):
    """
    Populates the relational star schema tables and returns record counts.
    """
    logger.banner("Phase 3A: Loading Relational Star Schema (SQLite)")
    conn = sqlite3.connect(db_path)
    setup_sqlite_schema(conn)
    cursor = conn.cursor()

    # 1. Populate dim_property (Unique properties)
    prop_cols = ["property_id", "yr_built_clean", "yr_renovated_clean", "is_renovated", "sqft_living15_clean", "sqft_lot15_clean"]
    df_prop = df_clean[prop_cols].drop_duplicates(subset=["property_id"])
    cursor.executemany("""
        INSERT INTO dim_property (property_id, yr_built, yr_renovated, is_renovated, sqft_living15, sqft_lot15)
        VALUES (?, ?, ?, ?, ?, ?)
    """, df_prop.values.tolist())
    conn.commit()
    prop_count = cursor.execute("SELECT COUNT(*) FROM dim_property").fetchone()[0]
    logger.log(f"Loaded {prop_count:,} unique rows into dim_property.")

    # 2. Populate dim_location (Unique zip, lat, long)
    loc_cols = ["zipcode_clean", "lat_clean", "long_clean"]
    df_loc = df_clean[loc_cols].drop_duplicates()
    cursor.executemany("""
        INSERT OR IGNORE INTO dim_location (zipcode, latitude, longitude)
        VALUES (?, ?, ?)
    """, df_loc.values.tolist())
    conn.commit()
    loc_count = cursor.execute("SELECT COUNT(*) FROM dim_location").fetchone()[0]
    logger.log(f"Loaded {loc_count:,} unique rows into dim_location.")

    # Build location lookup map: (zipcode, lat, long) -> location_id
    loc_map = {}
    for row in cursor.execute("SELECT location_id, zipcode, latitude, longitude FROM dim_location"):
        loc_map[(row[1], round(row[2], 4), round(row[3], 4))] = row[0]

    # 3. Populate dim_condition_grade (Unique grade, condition, view, waterfront)
    cg_cols = ["grade_clean", "condition_clean", "view_clean", "waterfront_clean"]
    df_cg = df_clean[cg_cols].drop_duplicates()
    cursor.executemany("""
        INSERT OR IGNORE INTO dim_condition_grade (grade, condition, view, waterfront)
        VALUES (?, ?, ?, ?)
    """, df_cg.values.tolist())
    conn.commit()
    cg_count = cursor.execute("SELECT COUNT(*) FROM dim_condition_grade").fetchone()[0]
    logger.log(f"Loaded {cg_count:,} unique rows into dim_condition_grade.")

    # Build condition/grade lookup map: (grade, condition, view, waterfront) -> grade_condition_id
    cg_map = {}
    for row in cursor.execute("SELECT grade_condition_id, grade, condition, view, waterfront FROM dim_condition_grade"):
        cg_map[(row[1], row[2], row[3], row[4])] = row[0]

    # 4. Populate dim_date (Temporal attributes)
    unique_dates = df_clean[["date_id", "full_date"]].drop_duplicates()
    date_records = []
    for _, row in unique_dates.iterrows():
        d_id = int(row["date_id"])
        f_date = row["full_date"]
        dt = datetime.strptime(f_date, "%Y-%m-%d")
        quarter = (dt.month - 1) // 3 + 1
        is_weekend = 1 if dt.weekday() >= 5 else 0
        date_records.append((
            d_id, f_date, dt.year, quarter, dt.month,
            dt.strftime("%B"), dt.day, dt.weekday(),
            dt.strftime("%A"), is_weekend
        ))

    cursor.executemany("""
        INSERT OR IGNORE INTO dim_date (
            date_id, full_date, year, quarter, month,
            month_name, day, day_of_week, day_name, is_weekend
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, date_records)
    conn.commit()
    date_count = cursor.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0]
    logger.log(f"Loaded {date_count:,} unique calendar rows into dim_date.")

    # 5. Populate Fact Table: fact_property_sales
    logger.section("Mapping Surrogate Foreign Keys & Ingesting Fact Table")
    fact_records = []
    skipped_fk = 0

    for _, row in df_clean.iterrows():
        p_id = int(row["property_id"])
        d_id = int(row["date_id"])
        l_key = (row["zipcode_clean"], round(float(row["lat_clean"]), 4), round(float(row["long_clean"]), 4))
        cg_key = (int(row["grade_clean"]), int(row["condition_clean"]), int(row["view_clean"]), int(row["waterfront_clean"]))

        loc_id = loc_map.get(l_key)
        cg_id = cg_map.get(cg_key)

        if loc_id is None or cg_id is None:
            skipped_fk += 1
            continue

        fact_records.append((
            p_id, d_id, loc_id, cg_id,
            float(row["price_clean"]),
            int(row["sqft_living_clean"]),
            int(row["sqft_lot_clean"]),
            float(row["price_per_sqft"]),
            int(row["bedrooms_clean"]),
            float(row["bathrooms_clean"]),
            float(row["floors_clean"]),
            int(row["sqft_above_clean"]),
            int(row["sqft_basement_clean"]),
            int(row["has_basement"])
        ))

    cursor.executemany("""
        INSERT INTO fact_property_sales (
            property_id, date_id, location_id, grade_condition_id,
            price, sqft_living, sqft_lot, price_per_sqft,
            bedrooms, bathrooms, floors, sqft_above, sqft_basement, has_basement
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, fact_records)
    conn.commit()

    fact_count = cursor.execute("SELECT COUNT(*) FROM fact_property_sales").fetchone()[0]
    logger.log(f"Loaded {fact_count:,} rows into fact_property_sales (skipped {skipped_fk} due to FK mapping).")

    conn.close()
    return {
        "dim_property": prop_count,
        "dim_location": loc_count,
        "dim_condition_grade": cg_count,
        "dim_date": date_count,
        "fact_property_sales": fact_count
    }


# ==============================================================================
# 5. MONGODB DOCUMENT STORE GOVERNANCE & LOADING
# ==============================================================================
def setup_mongodb_governance(client):
    """
    Creates MongoDB collections with strict $jsonSchema validation rules
    (validationLevel='strict', validationAction='error').
    """
    logger.section("Configuring MongoDB Strict $jsonSchema Validation Rules")
    db = client[MONGO_DB_NAME]

    # Schema 1: sales_documents
    sales_schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["property_id", "sale_date", "price", "sqft_living", "architectural_specs", "location"],
            "properties": {
                "property_id": {
                    "bsonType": ["int", "long"],
                    "description": "Must be an integer and is required"
                },
                "sale_date": {
                    "bsonType": "string",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                    "description": "ISO date string YYYY-MM-DD required"
                },
                "price": {
                    "bsonType": ["double", "int", "long"],
                    "minimum": 1.0,
                    "description": "Strictly positive property closing price"
                },
                "sqft_living": {
                    "bsonType": ["int", "long"],
                    "minimum": 1,
                    "description": "Interior living space must be positive integer"
                },
                "price_per_sqft": {
                    "bsonType": ["double", "int"],
                    "minimum": 0.01,
                    "description": "Valuation rate per square foot"
                },
                "architectural_specs": {
                    "bsonType": "object",
                    "required": ["bedrooms", "bathrooms", "floors", "grade", "condition"],
                    "properties": {
                        "bedrooms": {"bsonType": "int", "minimum": 0},
                        "bathrooms": {"bsonType": ["double", "int"], "minimum": 0.0},
                        "floors": {"bsonType": ["double", "int"], "minimum": 0.5},
                        "grade": {"bsonType": "int", "minimum": 1, "maximum": 13},
                        "condition": {"bsonType": "int", "minimum": 1, "maximum": 5},
                        "view": {"bsonType": "int", "minimum": 0, "maximum": 4},
                        "waterfront": {"bsonType": "int", "enum": [0, 1]},
                        "yr_built": {"bsonType": "int", "minimum": 1800, "maximum": 2050}
                    }
                },
                "location": {
                    "bsonType": "object",
                    "required": ["zipcode", "coordinates"],
                    "properties": {
                        "zipcode": {"bsonType": "string", "pattern": "^\\d{5}$"},
                        "coordinates": {
                            "bsonType": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"bsonType": "double"}
                        }
                    }
                }
            }
        }
    }

    # Schema 2: feedback_documents
    feedback_schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["review_id", "property_id", "review_date", "rating", "reviewer_category", "inspection_passed"],
            "properties": {
                "review_id": {
                    "bsonType": "string",
                    "description": "Unique review string identifier"
                },
                "property_id": {
                    "bsonType": ["int", "long"],
                    "description": "Target property integer identifier"
                },
                "review_date": {
                    "bsonType": "string",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                    "description": "ISO date string required"
                },
                "rating": {
                    "bsonType": ["int", "long"],
                    "minimum": 1,
                    "maximum": 5,
                    "description": "Inspection rating must be between 1 and 5"
                },
                "reviewer_category": {
                    "bsonType": "string",
                    "enum": ["Buyer", "Seller", "Licensed Inspector", "Certified Appraiser", "Tenant"],
                    "description": "Category must belong to approved stakeholder list"
                },
                "inspection_passed": {
                    "bsonType": "bool",
                    "description": "Boolean inspection indicator"
                },
                "sentiment_score": {
                    "bsonType": ["double", "int"],
                    "description": "Analytical NLP sentiment polarity metric"
                },
                "comments": {
                    "bsonType": "string",
                    "description": "Textual commentary"
                },
                "architectural_highlights": {
                    "bsonType": "array",
                    "items": {"bsonType": "string"}
                }
            }
        }
    }

    # Apply or recreate collections with validation
    existing_colls = db.list_collection_names()

    for coll_name, schema in [(MONGO_COLL_SALES, sales_schema), (MONGO_COLL_FEEDBACK, feedback_schema)]:
        if coll_name in existing_colls:
            db.drop_collection(coll_name)
        
        db.create_collection(
            coll_name,
            validator=schema,
            validationLevel="strict",
            validationAction="error"
        )
        logger.log(f"Collection '{coll_name}' configured with strict $jsonSchema validation.")

    # Create helpful query indexes
    db[MONGO_COLL_SALES].create_index([("property_id", 1)])
    db[MONGO_COLL_SALES].create_index([("sale_date", 1)])
    db[MONGO_COLL_SALES].create_index([("location.zipcode", 1)])
    db[MONGO_COLL_FEEDBACK].create_index([("property_id", 1)])
    db[MONGO_COLL_FEEDBACK].create_index([("review_id", 1)], unique=True)
    logger.log("Created B-Tree indexes on property_id, sale_date, and unique review_id in MongoDB.")


def load_mongodb_store(df_clean, clean_feedback, client):
    """
    Transforms clean records into hierarchical BSON documents and ingests into MongoDB.
    """
    logger.banner("Phase 3B: Loading Document Store (MongoDB)")
    setup_mongodb_governance(client)
    db = client[MONGO_DB_NAME]

    # 1. Transform Sales DataFrame into Hierarchical BSON documents
    sales_docs = []
    for _, row in df_clean.iterrows():
        doc = {
            "property_id": int(row["property_id"]),
            "sale_date": str(row["full_date"]),
            "price": float(row["price_clean"]),
            "sqft_living": int(row["sqft_living_clean"]),
            "sqft_lot": int(row["sqft_lot_clean"]),
            "price_per_sqft": float(row["price_per_sqft"]),
            "architectural_specs": {
                "bedrooms": int(row["bedrooms_clean"]),
                "bathrooms": float(row["bathrooms_clean"]),
                "floors": float(row["floors_clean"]),
                "grade": int(row["grade_clean"]),
                "condition": int(row["condition_clean"]),
                "view": int(row["view_clean"]),
                "waterfront": int(row["waterfront_clean"]),
                "yr_built": int(row["yr_built_clean"]),
                "yr_renovated": int(row["yr_renovated_clean"]),
                "is_renovated": int(row["is_renovated"]),
                "has_basement": int(row["has_basement"])
            },
            "location": {
                "zipcode": str(row["zipcode_clean"]),
                "coordinates": [round(float(row["long_clean"]), 4), round(float(row["lat_clean"]), 4)]
            }
        }
        sales_docs.append(doc)

    if sales_docs:
        res_sales = db[MONGO_COLL_SALES].insert_many(sales_docs)
        sales_mongo_count = len(res_sales.inserted_ids)
        logger.log(f"Successfully loaded {sales_mongo_count:,} documents into '{MONGO_COLL_SALES}'.")
    else:
        sales_mongo_count = 0

    # 2. Ingest Clean Feedback Documents
    if clean_feedback:
        res_feedback = db[MONGO_COLL_FEEDBACK].insert_many(clean_feedback)
        feedback_mongo_count = len(res_feedback.inserted_ids)
        logger.log(f"Successfully loaded {feedback_mongo_count:,} documents into '{MONGO_COLL_FEEDBACK}'.")
    else:
        feedback_mongo_count = 0

    return {
        "sales_documents": sales_mongo_count,
        "feedback_documents": feedback_mongo_count
    }


# ==============================================================================
# 6. DATABASE GOVERNANCE & CONSTRAINT VERIFICATION TESTS
# ==============================================================================
def run_governance_verification_suite(db_path, client):
    """
    Executes unit tests validating:
      1. Relational CHECK constraint enforcement (negative price rejection).
      2. Relational Foreign Key enforcement (orphan record rejection).
      3. MongoDB strict $jsonSchema validation (invalid rating rejection).
      4. MongoDB strict $jsonSchema validation (negative price rejection).
    """
    logger.banner("Phase 4: Multi-Engine Data Governance Verification Testing")
    test_results = []

    # --- Test 1: SQLite Negative Price CHECK Constraint ---
    logger.section("Unit Test 1: SQLite Negative Price CHECK Constraint")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    # Grab valid FKs
    prop_id = cursor.execute("SELECT property_id FROM dim_property LIMIT 1").fetchone()[0]
    date_id = cursor.execute("SELECT date_id FROM dim_date LIMIT 1").fetchone()[0]
    loc_id = cursor.execute("SELECT location_id FROM dim_location LIMIT 1").fetchone()[0]
    cg_id = cursor.execute("SELECT grade_condition_id FROM dim_condition_grade LIMIT 1").fetchone()[0]

    try:
        cursor.execute(f"""
            INSERT INTO fact_property_sales (
                property_id, date_id, location_id, grade_condition_id,
                price, sqft_living, sqft_lot, price_per_sqft,
                bedrooms, bathrooms, floors, sqft_above, sqft_basement, has_basement
            ) VALUES (
                {prop_id}, {date_id}, {loc_id}, {cg_id},
                -450000.0, 1500, 5000, -300.0,
                3, 2.0, 1.0, 1500, 0, 0
            )
        """)
        conn.commit()
        logger.log("[FAIL] Unexpectedly allowed negative price into fact_property_sales.")
        test_results.append(("SQLite CHECK Price > 0", "FAILED", "Constraint not triggered"))
    except sqlite3.IntegrityError as e:
        logger.log(f"[PASS] Relational engine successfully blocked negative price: {e}")
        test_results.append(("SQLite CHECK Price > 0", "PASSED", str(e)))
    finally:
        conn.rollback()

    # --- Test 2: SQLite Foreign Key Referential Integrity ---
    logger.section("Unit Test 2: SQLite Foreign Key Referential Integrity")
    try:
        cursor.execute(f"""
            INSERT INTO fact_property_sales (
                property_id, date_id, location_id, grade_condition_id,
                price, sqft_living, sqft_lot, price_per_sqft,
                bedrooms, bathrooms, floors, sqft_above, sqft_basement, has_basement
            ) VALUES (
                999999999999, {date_id}, {loc_id}, {cg_id},
                500000.0, 1500, 5000, 333.33,
                3, 2.0, 1.0, 1500, 0, 0
            )
        """)
        conn.commit()
        logger.log("[FAIL] Unexpectedly allowed orphaned record with invalid property_id.")
        test_results.append(("SQLite FK Referential Integrity", "FAILED", "Constraint not triggered"))
    except sqlite3.IntegrityError as e:
        logger.log(f"[PASS] Relational engine successfully blocked invalid foreign key: {e}")
        test_results.append(("SQLite FK Referential Integrity", "PASSED", str(e)))
    finally:
        conn.rollback()
        conn.close()

    # --- Test 3: MongoDB Strict $jsonSchema Validation (Out-of-Bounds Rating) ---
    logger.section("Unit Test 3: MongoDB Strict $jsonSchema (Out-of-Bounds Rating: 7)")
    db = client[MONGO_DB_NAME]
    invalid_feedback_doc = {
        "review_id": "TEST-FAIL-001",
        "property_id": int(prop_id),
        "review_date": "2015-05-15",
        "rating": 7,  # Invalid: max allowed is 5
        "reviewer_category": "Buyer",
        "inspection_passed": True
    }
    try:
        db[MONGO_COLL_FEEDBACK].insert_one(invalid_feedback_doc)
        logger.log("[FAIL] Unexpectedly allowed invalid rating (7) into feedback_documents.")
        test_results.append(("MongoDB $jsonSchema Rating 1-5", "FAILED", "Validation not triggered"))
    except WriteError as e:
        logger.log(f"[PASS] MongoDB successfully blocked invalid document via $jsonSchema: {e.details.get('errmsg', e)}")
        test_results.append(("MongoDB $jsonSchema Rating 1-5", "PASSED", "Document failed validation"))

    # --- Test 4: MongoDB Strict $jsonSchema Validation (Negative Price) ---
    logger.section("Unit Test 4: MongoDB Strict $jsonSchema (Negative Price: -100.0)")
    invalid_sales_doc = {
        "property_id": int(prop_id),
        "sale_date": "2015-05-15",
        "price": -100.0,  # Invalid: minimum is 1.0
        "sqft_living": 1500,
        "architectural_specs": {
            "bedrooms": 3,
            "bathrooms": 2.0,
            "floors": 1.0,
            "grade": 7,
            "condition": 3
        },
        "location": {
            "zipcode": "98178",
            "coordinates": [-122.257, 47.511]
        }
    }
    try:
        db[MONGO_COLL_SALES].insert_one(invalid_sales_doc)
        logger.log("[FAIL] Unexpectedly allowed negative price into sales_documents.")
        test_results.append(("MongoDB $jsonSchema Price >= 1.0", "FAILED", "Validation not triggered"))
    except WriteError as e:
        logger.log(f"[PASS] MongoDB successfully blocked negative price document: {e.details.get('errmsg', e)}")
        test_results.append(("MongoDB $jsonSchema Price >= 1.0", "PASSED", "Document failed validation"))

    return test_results


# ==============================================================================
# 7. MASTER PIPELINE ORCHESTRATION & SUMMARY REPORTING
# ==============================================================================
def run_capstone_etl():
    """
    Main orchestration routine coordinating extraction, transformation, dual loading,
    and governance audit verification.
    """
    start_time = datetime.now()
    logger.banner("RetailPulse / Group 10 Multi-Engine Data Warehouse")
    logger.write(f" Execution Date:       {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    logger.write(f" Domain:               Real Estate Property Valuation Warehouse (Group 10)\n")
    logger.write(f" Target Relational DB: {SQLITE_WAREHOUSE_PATH}\n")
    logger.write(f" Target Mongo Database:{MONGO_DB_NAME}\n")
    logger.write(f" Audit Log File:       {AUDIT_LOG_PATH}\n")

    try:
        # Step 1: Extract
        df_raw_sales, raw_feedback_data, raw_sales_cnt, raw_feed_cnt = extract_landing_zone_data()

        # Step 2: Cleanse & Transform
        df_clean_sales = cleanse_sales_data(df_raw_sales)
        clean_feedback_docs = cleanse_feedback_data(raw_feedback_data)

        # Step 3: Load Relational Star Schema (SQLite)
        sqlite_counts = load_sqlite_warehouse(df_clean_sales, SQLITE_WAREHOUSE_PATH)

        # Step 4: Load Document Store (MongoDB)
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        # Check connection
        mongo_client.server_info()
        mongo_counts = load_mongodb_store(df_clean_sales, clean_feedback_docs, mongo_client)

        # Step 5: Run Governance Verification Tests
        test_results = run_governance_verification_suite(SQLITE_WAREHOUSE_PATH, mongo_client)

        # Step 6: Summary & Timing
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.banner("Milestone 1 Master Execution Audit Summary")
        logger.write(f" Total Execution Time: {elapsed:.2f} seconds\n\n")

        logger.write(" [A] Operational Cleansing Metrics:\n")
        logger.write(f"     • Raw Sales Rows Ingested:        {raw_sales_cnt:>8,}\n")
        logger.write(f"     • Final Clean Sales Rows:         {len(df_clean_sales):>8,}\n")
        logger.write(f"     • Raw Feedback Documents Read:    {raw_feed_cnt:>8,}\n")
        logger.write(f"     • Final Clean Feedback Docs:      {len(clean_feedback_docs):>8,}\n\n")

        logger.write(" [B] Relational Star Schema (SQLite: enterprise_warehouse.db):\n")
        for tbl, cnt in sqlite_counts.items():
            logger.write(f"     • {tbl:<26}: {cnt:>8,} rows\n")
        logger.write("\n")

        logger.write(f" [C] Document Collections (MongoDB: {MONGO_DB_NAME}):\n")
        for coll, cnt in mongo_counts.items():
            logger.write(f"     • {coll:<26}: {cnt:>8,} documents\n")
        logger.write("\n")

        logger.write(" [D] Data Governance & Constraint Verification Suite:\n")
        for test_name, status, detail in test_results:
            logger.write(f"     • {test_name:<32} [{status}] ({detail[:45]}...)\n")
        logger.write("\n")

        all_passed = all(status == "PASSED" for _, status, _ in test_results)
        if all_passed:
            logger.write(" >>> STATUS: MILESTONE 1 ETL & GOVERNANCE COMPLETED SUCCESSFULLY (100% PASS) <<<\n")
        else:
            logger.write(" >>> STATUS: COMPLETED WITH WARNINGS <<<\n")

    except Exception as e:
        logger.write(f"\n[CRITICAL ERROR] Pipeline execution halted: {e}\n")
        import traceback
        logger.write(traceback.format_exc())
    finally:
        logger.close()


if __name__ == "__main__":
    run_capstone_etl()
