"""
================================================================================
ETL PHASE 3: SQLITE STAR SCHEMA LOADER MODULE
================================================================================
Responsible for DDL execution, primary/foreign key constraint enforcement,
populating dimension and fact tables, and indexing.
================================================================================
"""

import os
import logging
import sqlite3
import pandas as pd

logger = logging.getLogger("Milestone1_ETL")


def load_sqlite_warehouse(df: pd.DataFrame, db_path: str):
    """
    Builds and populates a normalized star schema in SQLite:
      - Dimensions: dim_date, dim_location, dim_property, dim_condition_grade
      - Fact: fact_property_sales
    """
    logger.info("=" * 70)
    logger.info("STEP 3: SQLITE STAR SCHEMA WAREHOUSE LOADING")
    logger.info("=" * 70)
    logger.info(f"Initializing SQLite Database at: {db_path}")

    # Remove existing database file if present to guarantee deterministic state
    if os.path.exists(db_path):
        os.remove(db_path)
        logger.info(f"Removed pre-existing database file: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        # 3.1 DDL: Create Star Schema Tables
        logger.info("Executing DDL statements to build star schema tables...")

        # Dimension: Date
        cursor.execute("""
        CREATE TABLE dim_date (
            date_id INTEGER PRIMARY KEY,
            full_date TEXT NOT NULL,
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            month INTEGER NOT NULL,
            month_name TEXT NOT NULL,
            day INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            day_name TEXT NOT NULL,
            is_weekend INTEGER NOT NULL
        );
        """)

        # Dimension: Location
        cursor.execute("""
        CREATE TABLE dim_location (
            location_id INTEGER PRIMARY KEY AUTOINCREMENT,
            zipcode TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            UNIQUE(zipcode, latitude, longitude)
        );
        """)

        # Dimension: Property
        cursor.execute("""
        CREATE TABLE dim_property (
            property_id INTEGER PRIMARY KEY,
            yr_built INTEGER NOT NULL,
            yr_renovated INTEGER NOT NULL,
            is_renovated INTEGER NOT NULL,
            sqft_living15 INTEGER NOT NULL,
            sqft_lot15 INTEGER NOT NULL
        );
        """)

        # Dimension: Condition & Grade
        cursor.execute("""
        CREATE TABLE dim_condition_grade (
            grade_condition_id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade INTEGER NOT NULL,
            condition INTEGER NOT NULL,
            view INTEGER NOT NULL,
            waterfront INTEGER NOT NULL,
            UNIQUE(grade, condition, view, waterfront)
        );
        """)

        # Fact: Property Sales
        cursor.execute("""
        CREATE TABLE fact_property_sales (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            date_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            grade_condition_id INTEGER NOT NULL,
            price REAL NOT NULL,
            sqft_living INTEGER NOT NULL,
            sqft_lot INTEGER NOT NULL,
            price_per_sqft REAL NOT NULL,
            bedrooms INTEGER NOT NULL,
            bathrooms REAL NOT NULL,
            floors REAL NOT NULL,
            sqft_above INTEGER NOT NULL,
            sqft_basement INTEGER NOT NULL,
            has_basement INTEGER NOT NULL,
            FOREIGN KEY (property_id) REFERENCES dim_property(property_id),
            FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
            FOREIGN KEY (location_id) REFERENCES dim_location(location_id),
            FOREIGN KEY (grade_condition_id) REFERENCES dim_condition_grade(grade_condition_id)
        );
        """)

        # Performance Indexes for analytical queries
        cursor.execute("CREATE INDEX idx_fact_date ON fact_property_sales(date_id);")
        cursor.execute("CREATE INDEX idx_fact_location ON fact_property_sales(location_id);")
        cursor.execute("CREATE INDEX idx_fact_grade ON fact_property_sales(grade_condition_id);")
        cursor.execute("CREATE INDEX idx_fact_property ON fact_property_sales(property_id);")
        cursor.execute("CREATE INDEX idx_dim_loc_zip ON dim_location(zipcode);")

        # 3.2 Populate Dimension: Date
        logger.info("Populating 'dim_date' table...")
        date_cols = ["date_id", "full_date", "year", "quarter", "month", "month_name", "day", "day_of_week", "day_name", "is_weekend"]
        df_dates = df[date_cols].drop_duplicates().sort_values("date_id")
        df_dates.to_sql("dim_date", conn, if_exists="append", index=False)
        logger.info(f"Loaded {len(df_dates):,} records into 'dim_date'.")

        # 3.3 Populate Dimension: Location
        logger.info("Populating 'dim_location' table...")
        loc_cols = ["zipcode", "lat", "long"]
        df_locs = df[loc_cols].drop_duplicates().rename(columns={"lat": "latitude", "long": "longitude"})
        df_locs.to_sql("dim_location", conn, if_exists="append", index=False)
        logger.info(f"Loaded {len(df_locs):,} records into 'dim_location'.")

        loc_lookup = pd.read_sql_query("SELECT location_id, zipcode, latitude, longitude FROM dim_location", conn)

        # 3.4 Populate Dimension: Property
        logger.info("Populating 'dim_property' table...")
        prop_cols = ["id", "yr_built", "yr_renovated", "is_renovated", "sqft_living15", "sqft_lot15"]
        df_props = df[prop_cols].drop_duplicates(subset=["id"]).rename(columns={"id": "property_id"})
        df_props.to_sql("dim_property", conn, if_exists="append", index=False)
        logger.info(f"Loaded {len(df_props):,} records into 'dim_property'.")

        # 3.5 Populate Dimension: Condition & Grade
        logger.info("Populating 'dim_condition_grade' table...")
        grade_cols = ["grade", "condition", "view", "waterfront"]
        df_grades = df[grade_cols].drop_duplicates().sort_values(["grade", "condition"])
        df_grades.to_sql("dim_condition_grade", conn, if_exists="append", index=False)
        logger.info(f"Loaded {len(df_grades):,} records into 'dim_condition_grade'.")

        grade_lookup = pd.read_sql_query("SELECT grade_condition_id, grade, condition, view, waterfront FROM dim_condition_grade", conn)

        # 3.6 Populate Fact: Property Sales
        logger.info("Mapping foreign keys and populating 'fact_property_sales' table...")

        df_fact = df.merge(
            loc_lookup,
            left_on=["zipcode", "lat", "long"],
            right_on=["zipcode", "latitude", "longitude"],
            how="inner"
        )

        df_fact = df_fact.merge(
            grade_lookup,
            on=["grade", "condition", "view", "waterfront"],
            how="inner"
        )

        df_fact = df_fact.rename(columns={"id": "property_id"})
        fact_final_cols = [
            "property_id", "date_id", "location_id", "grade_condition_id",
            "price", "sqft_living", "sqft_lot", "price_per_sqft",
            "bedrooms", "bathrooms", "floors", "sqft_above", "sqft_basement", "has_basement"
        ]
        df_fact_to_load = df_fact[fact_final_cols]
        df_fact_to_load.to_sql("fact_property_sales", conn, if_exists="append", index=False)

        conn.commit()
        logger.info(f"Loaded {len(df_fact_to_load):,} records into 'fact_property_sales'.")

        # Foreign Key Verification
        cursor.execute("PRAGMA foreign_key_check;")
        fk_violations = cursor.fetchall()
        if not fk_violations:
            logger.info("Integrity Check PASSED: 0 foreign key constraint violations detected.")
        else:
            logger.error(f"Integrity Check FAILED: Foreign key violations detected: {fk_violations}")
            raise ValueError("Foreign key constraint violations in warehouse.db")

    finally:
        conn.close()

