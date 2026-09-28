"""
================================================================================
ETL PHASE 4: MONGODB DOCUMENT STORE LOADER MODULE
================================================================================
Responsible for hierarchical document transformation, GeoJSON geometry,
spatial indexing (2dsphere), and batch ingestion.
================================================================================
"""

import logging
from datetime import datetime, timezone
import pandas as pd
import pymongo
from pymongo import MongoClient

logger = logging.getLogger("Milestone1_ETL")


def load_mongodb_documents(df: pd.DataFrame, mongo_uri: str, db_name: str, coll_name: str):
    """
    Transforms tabular records into hierarchical architectural documents
    and performs bulk insert into MongoDB with spatial and attribute indexes.
    """
    logger.info("=" * 70)
    logger.info("STEP 4: MONGODB DOCUMENT STORE LOADING")
    logger.info("=" * 70)
    logger.info(f"Connecting to MongoDB at: {mongo_uri}")

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    server_info = client.server_info()
    logger.info(f"Connected to MongoDB Server v{server_info.get('version', 'Unknown')}")

    db = client[db_name]
    coll = db[coll_name]

    # Reset collection for deterministic loading
    coll.drop()
    logger.info(f"Cleaned staging collection '{coll_name}' in database '{db_name}'.")

    logger.info("Transforming tabular data into nested architectural feature documents...")
    documents = []

    grouped = df.groupby("id")
    for prop_id, group in grouped:
        latest = group.iloc[-1]

        sales_history = []
        for _, sale in group.iterrows():
            sales_history.append({
                "sale_date": sale["full_date"],
                "price": float(sale["price"]),
                "price_per_sqft": float(sale["price_per_sqft"])
            })

        doc = {
            "_id": int(prop_id),
            "property_id": int(prop_id),
            "architectural_specs": {
                "bedrooms": int(latest["bedrooms"]),
                "bathrooms": float(latest["bathrooms"]),
                "floors": float(latest["floors"]),
                "sqft_living": int(latest["sqft_living"]),
                "sqft_lot": int(latest["sqft_lot"]),
                "sqft_above": int(latest["sqft_above"]),
                "sqft_basement": int(latest["sqft_basement"]),
                "has_basement": bool(latest["has_basement"])
            },
            "construction_history": {
                "yr_built": int(latest["yr_built"]),
                "yr_renovated": int(latest["yr_renovated"]),
                "is_renovated": bool(latest["is_renovated"])
            },
            "evaluation_metrics": {
                "grade": int(latest["grade"]),
                "condition": int(latest["condition"]),
                "view": int(latest["view"]),
                "waterfront": bool(latest["waterfront"])
            },
            "neighborhood_context": {
                "zipcode": str(latest["zipcode"]),
                "location": {
                    "type": "Point",
                    "coordinates": [float(latest["long"]), float(latest["lat"])]  # GeoJSON: [lng, lat]
                },
                "sqft_living15": int(latest["sqft_living15"]),
                "sqft_lot15": int(latest["sqft_lot15"])
            },
            "sales_history": sales_history,
            "metadata": {
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "group_domain": "Group 10 - Real Estate Property Listing & Regional Market Value Warehouse"
            }
        }
        documents.append(doc)

    # Bulk insert
    logger.info(f"Bulk inserting {len(documents):,} documents into MongoDB collection '{coll_name}'...")
    result = coll.insert_many(documents)
    logger.info(f"Successfully inserted {len(result.inserted_ids):,} documents into MongoDB.")

    # Create indexes
    logger.info("Creating MongoDB indexes (property_id, zipcode, 2dsphere location, grade)...")
    coll.create_index([("property_id", pymongo.ASCENDING)], unique=True)
    coll.create_index([("neighborhood_context.zipcode", pymongo.ASCENDING)])
    coll.create_index([("neighborhood_context.location", "2dsphere")])
    coll.create_index([("evaluation_metrics.grade", pymongo.ASCENDING)])
    logger.info("MongoDB indexing successfully completed.")

    client.close()

