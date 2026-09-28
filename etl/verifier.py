"""
================================================================================
ETL PHASE 5: VERIFICATION & AUDIT MODULE
================================================================================
Responsible for cross-engine integrity checks, table/collection row counting,
and executing sample OLAP analytical queries.
================================================================================
"""

import logging
import sqlite3
from pymongo import MongoClient

logger = logging.getLogger("Milestone1_ETL")


def verify_and_audit(db_path: str, mongo_uri: str, db_name: str, coll_name: str):
    """
    Executes automated post-load verification across SQLite and MongoDB.
    """
    logger.info("=" * 70)
    logger.info("STEP 5: CROSS-ENGINE AUDIT & VERIFICATION")
    logger.info("=" * 70)

    # 5.1 SQLite Verification
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    tables = ["dim_date", "dim_location", "dim_property", "dim_condition_grade", "fact_property_sales"]
    logger.info("SQLite Table Record Counts:")
    for tbl in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
        cnt = cursor.fetchone()[0]
        logger.info(f"  - {tbl:<20}: {cnt:>8,} rows")

    # Sample OLAP Join Query on SQLite
    sample_query = """
    SELECT 
        d.year,
        d.quarter,
        COUNT(f.sale_id) AS total_transactions,
        ROUND(AVG(f.price), 2) AS avg_sale_price,
        ROUND(AVG(f.price_per_sqft), 2) AS avg_price_per_sqft
    FROM fact_property_sales f
    JOIN dim_date d ON f.date_id = d.date_id
    GROUP BY d.year, d.quarter
    ORDER BY d.year, d.quarter;
    """
    logger.info("\nVerification Query: Quarterly Sales Summary (SQLite):")
    cursor.execute(sample_query)
    rows = cursor.fetchall()
    logger.info(f"  {'Year':<6} {'Quarter':<8} {'Transactions':<14} {'Avg Price ($)':<16} {'Avg Price/SqFt ($)':<18}")
    logger.info("  " + "-" * 64)
    for r in rows:
        logger.info(f"  {r[0]:<6} Q{r[1]:<7} {r[2]:<14,} ${r[3]:<15,.2f} ${r[4]:<17.2f}")

    conn.close()

    # 5.2 MongoDB Verification
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    coll = client[db_name][coll_name]
    mongo_count = coll.count_documents({})
    logger.info(f"\nMongoDB Document Count: {mongo_count:,} documents in '{coll_name}'")

    # Sample Document Inspection
    sample_doc = coll.find_one({"property_id": 7129300520}, {"_id": 0, "metadata": 0})
    logger.info(f"Sample Document Inspection (Property ID 7129300520):")
    logger.info(f"  Bedrooms: {sample_doc['architectural_specs']['bedrooms']}, Bathrooms: {sample_doc['architectural_specs']['bathrooms']}")
    logger.info(f"  Living SqFt: {sample_doc['architectural_specs']['sqft_living']}, Grade: {sample_doc['evaluation_metrics']['grade']}")
    logger.info(f"  Coordinates: {sample_doc['neighborhood_context']['location']['coordinates']}")
    logger.info(f"  Sales Recorded: {len(sample_doc['sales_history'])}")

    client.close()

    logger.info("=" * 70)
    logger.info("MILESTONE 1 PIPELINE EXECUTION COMPLETED SUCCESSFULLY")
    logger.info("=" * 70)

