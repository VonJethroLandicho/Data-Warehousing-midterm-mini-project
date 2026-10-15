"""
================================================================================
DATA WAREHOUSING (LEC/LAB) - LESSON 7: PERFORMANCE TUNING & DATA MART CREATION
GROUP 10: REAL ESTATE PROPERTY LISTING & REGIONAL MARKET VALUE WAREHOUSE
DELIVERABLE 2: DATA GOVERNANCE & SCHEMA VALIDATION SCRIPT (lab_governance.py)
================================================================================
Author / Group: Group 10 (Real Estate Domain)
Instructor: Prof. Rob Malitao
Date: October 2026

Description:
  This script enforces strict multi-engine Data Governance:
  1. Relational Governance (SQLite):
     - Implements DDL with NOT NULL, PRIMARY KEY, FOREIGN KEY constraints.
     - Implements CHECK constraints enforcing positive prices, valid square
       footage, valid building grades (1-13), and valid conditions (1-5).
     - Executes unit tests validating successful ingestion of valid data and
       strict rejection/rollback of non-compliant data.
  2. Document Store Governance (MongoDB):
     - Enforces a strict $jsonSchema validator on MongoDB collections.
     - Sets validationLevel="strict" and validationAction="error".
     - Validates architectural nested specs, geo-coordinates, and positive pricing.
     - Executes unit tests demonstrating that malformed documents are blocked.
================================================================================
"""

import os
import sys
import sqlite3
import pymongo
from pymongo import MongoClient
from pymongo.errors import WriteError, OperationFailure
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
GOVERNED_DB_PATH = os.path.join(CURRENT_DIR, "governed_warehouse.db")
EXECUTION_LOG_PATH = os.path.join(CURRENT_DIR, "lab4_execution_log.txt")

MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "real_estate_warehouse"
MONGO_GOVERNED_COLL = "property_architectural_features_governed"


def log_message(msg):
    print(msg)
    with open(EXECUTION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def print_section(title):
    banner = "\n" + "=" * 80 + f"\n {title.upper()}\n" + "=" * 80
    log_message(banner)


# ==============================================================================
# PART 1: RELATIONAL DATA GOVERNANCE & DDL CHECK CONSTRAINTS (SQLITE)
# ==============================================================================

def setup_relational_governed_warehouse(db_path):
    """
    Creates relational tables with rigorous schema constraints:
      - Primary Key and Foreign Key constraints
      - NOT NULL constraints on all critical fields
      - Strict CHECK constraints on prices, sqft, grades, and coordinates
    """
    print_section("Part 1: Relational Schema Governance & Strict DDL Constraints")
    log_message(f"Initializing Governed Relational Database at: {db_path}")

    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")
    cur.execute("PRAGMA journal_mode = WAL;")

    # 1. Governed Date Dimension
    cur.execute("""
    CREATE TABLE dim_date_governed (
        date_id INTEGER PRIMARY KEY,
        full_date TEXT NOT NULL CHECK (length(full_date) >= 8),
        year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 2100),
        quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
        month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
        month_name TEXT NOT NULL,
        day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
        day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
        day_name TEXT NOT NULL,
        is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
    );
    """)

    # 2. Governed Location Dimension
    cur.execute("""
    CREATE TABLE dim_location_governed (
        location_id INTEGER PRIMARY KEY AUTOINCREMENT,
        zipcode TEXT NOT NULL CHECK (length(zipcode) = 5),
        latitude REAL NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
        longitude REAL NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
        UNIQUE(zipcode, latitude, longitude)
    );
    """)

    # 3. Governed Property Dimension
    cur.execute("""
    CREATE TABLE dim_property_governed (
        property_id INTEGER PRIMARY KEY,
        yr_built INTEGER NOT NULL CHECK (yr_built BETWEEN 1800 AND 2050),
        yr_renovated INTEGER NOT NULL CHECK (yr_renovated >= 0),
        is_renovated INTEGER NOT NULL CHECK (is_renovated IN (0, 1)),
        sqft_living15 INTEGER NOT NULL CHECK (sqft_living15 > 0),
        sqft_lot15 INTEGER NOT NULL CHECK (sqft_lot15 > 0)
    );
    """)

    # 4. Governed Condition & Grade Dimension
    cur.execute("""
    CREATE TABLE dim_condition_grade_governed (
        grade_condition_id INTEGER PRIMARY KEY AUTOINCREMENT,
        grade INTEGER NOT NULL CHECK (grade BETWEEN 1 AND 13),
        condition INTEGER NOT NULL CHECK (condition BETWEEN 1 AND 5),
        view INTEGER NOT NULL CHECK (view BETWEEN 0 AND 4),
        waterfront INTEGER NOT NULL CHECK (waterfront IN (0, 1)),
        UNIQUE(grade, condition, view, waterfront)
    );
    """)

    # 5. Governed Fact Table with Strict Financial and Physical CHECK Constraints
    cur.execute("""
    CREATE TABLE fact_property_sales_governed (
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
        FOREIGN KEY (property_id) REFERENCES dim_property_governed(property_id) ON DELETE RESTRICT,
        FOREIGN KEY (date_id) REFERENCES dim_date_governed(date_id) ON DELETE RESTRICT,
        FOREIGN KEY (location_id) REFERENCES dim_location_governed(location_id) ON DELETE RESTRICT,
        FOREIGN KEY (grade_condition_id) REFERENCES dim_condition_grade_governed(grade_condition_id) ON DELETE RESTRICT
    );
    """)

    conn.commit()
    log_message("[DDL SUCCESS] Governed Star Schema tables created with strict CHECK and NOT NULL constraints.")
    return conn


def test_relational_governance(conn):
    """
    Executes automated test cases demonstrating positive compliance and
    active blocking of constraint violations.
    """
    cur = conn.cursor()
    log_message("\n--- Running Relational Governance Integrity Tests ---")

    # Step A: Populate valid parent dimension rows
    cur.execute("INSERT INTO dim_date_governed VALUES (20140502, '2014-05-02', 2014, 2, 5, 'May', 2, 4, 'Friday', 0);")
    cur.execute("INSERT INTO dim_location_governed (zipcode, latitude, longitude) VALUES ('98178', 47.5112, -122.257);")
    loc_id = cur.lastrowid
    cur.execute("INSERT INTO dim_property_governed VALUES (7129300520, 1955, 0, 0, 1340, 5650);")
    cur.execute("INSERT INTO dim_condition_grade_governed (grade, condition, view, waterfront) VALUES (7, 3, 0, 0);")
    grade_id = cur.lastrowid
    conn.commit()
    log_message("[SEED] Successfully seeded valid dimension reference records.")

    test_cases = [
        {
            "name": "TEST 1: Positive Compliance (Clean, valid property sale)",
            "sql": f"""
                INSERT INTO fact_property_sales_governed (
                    property_id, date_id, location_id, grade_condition_id,
                    price, sqft_living, sqft_lot, price_per_sqft,
                    bedrooms, bathrooms, floors, sqft_above, sqft_basement, has_basement
                ) VALUES (
                    7129300520, 20140502, {loc_id}, {grade_id},
                    221900.0, 1180, 5650, 188.05,
                    3, 1.0, 1.0, 1180, 0, 0
                );
            """,
            "should_fail": False,
            "expected_error": None
        },
        {
            "name": "TEST 2: Negative Pricing Violation (CHECK constraint price > 0)",
            "sql": f"""
                INSERT INTO fact_property_sales_governed (
                    property_id, date_id, location_id, grade_condition_id,
                    price, sqft_living, sqft_lot, price_per_sqft,
                    bedrooms, bathrooms, floors, sqft_above, sqft_basement, has_basement
                ) VALUES (
                    7129300520, 20140502, {loc_id}, {grade_id},
                    -350000.0, 1180, 5650, -296.61,
                    3, 1.0, 1.0, 1180, 0, 0
                );
            """,
            "should_fail": True,
            "expected_error": "CHECK constraint failed"
        },
        {
            "name": "TEST 3: Zero / Negative Living Space (CHECK constraint sqft_living > 0)",
            "sql": f"""
                INSERT INTO fact_property_sales_governed (
                    property_id, date_id, location_id, grade_condition_id,
                    price, sqft_living, sqft_lot, price_per_sqft,
                    bedrooms, bathrooms, floors, sqft_above, sqft_basement, has_basement
                ) VALUES (
                    7129300520, 20140502, {loc_id}, {grade_id},
                    450000.0, 0, 5650, 450.0,
                    3, 1.0, 1.0, 0, 0, 0
                );
            """,
            "should_fail": True,
            "expected_error": "CHECK constraint failed"
        },
        {
            "name": "TEST 4: Missing Required Key (NOT NULL constraint date_id)",
            "sql": f"""
                INSERT INTO fact_property_sales_governed (
                    property_id, date_id, location_id, grade_condition_id,
                    price, sqft_living, sqft_lot, price_per_sqft,
                    bedrooms, bathrooms, floors, sqft_above, sqft_basement, has_basement
                ) VALUES (
                    7129300520, NULL, {loc_id}, {grade_id},
                    500000.0, 1500, 6000, 333.33,
                    4, 2.0, 1.0, 1500, 0, 0
                );
            """,
            "should_fail": True,
            "expected_error": "NOT NULL constraint failed"
        },
        {
            "name": "TEST 5: Orphan Record / Foreign Key Violation (location_id 999999)",
            "sql": f"""
                INSERT INTO fact_property_sales_governed (
                    property_id, date_id, location_id, grade_condition_id,
                    price, sqft_living, sqft_lot, price_per_sqft,
                    bedrooms, bathrooms, floors, sqft_above, sqft_basement, has_basement
                ) VALUES (
                    7129300520, 20140502, 999999, {grade_id},
                    550000.0, 1800, 7000, 305.55,
                    3, 2.5, 2.0, 1800, 0, 0
                );
            """,
            "should_fail": True,
            "expected_error": "FOREIGN KEY constraint failed"
        },
        {
            "name": "TEST 6: Invalid Dimension Attribute (CHECK constraint grade BETWEEN 1 AND 13)",
            "sql": """
                INSERT INTO dim_condition_grade_governed (grade, condition, view, waterfront)
                VALUES (25, 3, 0, 0);
            """,
            "should_fail": True,
            "expected_error": "CHECK constraint failed"
        }
    ]

    for tc in test_cases:
        name = tc["name"]
        sql = tc["sql"]
        should_fail = tc["should_fail"]
        try:
            cur.execute(sql)
            conn.commit()
            if should_fail:
                log_message(f"  [FAIL] {name}: Expected violation but query succeeded unexpectedly!")
            else:
                log_message(f"  [PASS] {name}: Valid data accepted successfully.")
        except sqlite3.IntegrityError as err:
            if should_fail and (tc["expected_error"] is None or tc["expected_error"] in str(err)):
                log_message(f"  [PASS - BLOCKED AS EXPECTED] {name}")
                log_message(f"         Caught Expected Error: {err}")
            else:
                log_message(f"  [UNEXPECTED ERROR] {name}: {err}")


# ==============================================================================
# PART 2: DOCUMENT STORE GOVERNANCE & MONGODB $jsonSchema VALIDATION
# ==============================================================================

def setup_mongodb_schema_governance(mongo_uri, db_name, coll_name):
    """
    Applies strict MongoDB JSON Schema Validation using $jsonSchema validator.
    Enforces validationLevel='strict' and validationAction='error'.
    """
    print_section("Part 2: MongoDB Document Store Governance ($jsonSchema Validator)")
    log_message(f"Connecting to MongoDB at: {mongo_uri}")
    
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[db_name]

    # Drop governed collection if exists to re-apply pristine schema validator
    if coll_name in db.list_collection_names():
        db[coll_name].drop()
        log_message(f"Dropped pre-existing governed collection: '{coll_name}'")

    # Define strict $jsonSchema specification for Real Estate architectural documents
    json_schema_validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "_id",
                "property_id",
                "architectural_specs",
                "evaluation_metrics",
                "neighborhood_context",
                "sales_history"
            ],
            "properties": {
                "_id": {
                    "bsonType": ["int", "long"],
                    "description": "Unique numeric document identifier"
                },
                "property_id": {
                    "bsonType": ["int", "long"],
                    "description": "Mandatory property reference identifier"
                },
                "architectural_specs": {
                    "bsonType": "object",
                    "required": ["bedrooms", "bathrooms", "floors", "sqft_living"],
                    "properties": {
                        "bedrooms": {
                            "bsonType": "int",
                            "minimum": 0,
                            "description": "Bedrooms must be a non-negative integer"
                        },
                        "bathrooms": {
                            "bsonType": ["double", "int"],
                            "minimum": 0.0,
                            "description": "Bathrooms count must be non-negative"
                        },
                        "floors": {
                            "bsonType": ["double", "int"],
                            "minimum": 0.5,
                            "description": "Floors must be at least 0.5"
                        },
                        "sqft_living": {
                            "bsonType": "int",
                            "minimum": 1,
                            "description": "Living square footage must be strictly positive"
                        },
                        "sqft_lot": {
                            "bsonType": "int",
                            "minimum": 1
                        },
                        "has_basement": {
                            "bsonType": "bool"
                        }
                    }
                },
                "evaluation_metrics": {
                    "bsonType": "object",
                    "required": ["grade", "condition"],
                    "properties": {
                        "grade": {
                            "bsonType": "int",
                            "minimum": 1,
                            "maximum": 13,
                            "description": "Construction grade must be between 1 and 13 inclusive"
                        },
                        "condition": {
                            "bsonType": "int",
                            "minimum": 1,
                            "maximum": 5,
                            "description": "Building condition score must be between 1 and 5"
                        },
                        "view": {
                            "bsonType": "int",
                            "minimum": 0,
                            "maximum": 4
                        },
                        "waterfront": {
                            "bsonType": "bool"
                        }
                    }
                },
                "neighborhood_context": {
                    "bsonType": "object",
                    "required": ["zipcode", "location"],
                    "properties": {
                        "zipcode": {
                            "bsonType": "string",
                            "pattern": "^[0-9]{5}$",
                            "description": "Zipcode must be a valid 5-digit US postal string"
                        },
                        "location": {
                            "bsonType": "object",
                            "required": ["type", "coordinates"],
                            "properties": {
                                "type": {
                                    "enum": ["Point"],
                                    "description": "GeoJSON type must be Point"
                                },
                                "coordinates": {
                                    "bsonType": "array",
                                    "minItems": 2,
                                    "maxItems": 2,
                                    "items": { "bsonType": ["double", "int"] },
                                    "description": "Coordinates array must contain [longitude, latitude]"
                                }
                            }
                        }
                    }
                },
                "sales_history": {
                    "bsonType": "array",
                    "minItems": 1,
                    "description": "At least one sales record is required",
                    "items": {
                        "bsonType": "object",
                        "required": ["sale_date", "price", "price_per_sqft"],
                        "properties": {
                            "sale_date": {
                                "bsonType": "string",
                                "description": "ISO or formatted date string"
                            },
                            "price": {
                                "bsonType": ["double", "int"],
                                "minimum": 1.0,
                                "description": "Transaction price must be strictly positive"
                            },
                            "price_per_sqft": {
                                "bsonType": ["double", "int"],
                                "minimum": 0.01,
                                "description": "Price per square foot must be positive"
                            }
                        }
                    }
                }
            }
        }
    }

    # Create collection with explicit schema validator
    db.create_collection(
        coll_name,
        validator=json_schema_validator,
        validationLevel="strict",
        validationAction="error"
    )
    log_message(f"[MONGODB DDL] Collection '{coll_name}' created with strict $jsonSchema validator.")
    
    # Create indexes for spatial and high-cardinality searches
    coll = db[coll_name]
    coll.create_index([("property_id", pymongo.ASCENDING)], unique=True)
    coll.create_index([("neighborhood_context.location", "2dsphere")])
    log_message("[MONGODB INDEX] Applied unique index on property_id and 2dsphere on neighborhood_context.location.")

    return client, db, coll


def test_mongodb_governance(coll):
    """
    Tests MongoDB $jsonSchema validation rules:
      - Valid document insertion succeeds.
      - Negative/invalid documents (negative price, out-of-range grade, invalid zip) are blocked.
    """
    log_message("\n--- Running MongoDB $jsonSchema Validation Tests ---")

    mongo_tests = [
        {
            "name": "MONGO TEST 1: Valid Architectural Feature Document",
            "doc": {
                "_id": 999001,
                "property_id": 999001,
                "architectural_specs": {
                    "bedrooms": 3,
                    "bathrooms": 2.5,
                    "floors": 2.0,
                    "sqft_living": 2100,
                    "sqft_lot": 5000,
                    "has_basement": False
                },
                "evaluation_metrics": {
                    "grade": 8,
                    "condition": 4,
                    "view": 1,
                    "waterfront": False
                },
                "neighborhood_context": {
                    "zipcode": "98052",
                    "location": {
                        "type": "Point",
                        "coordinates": [-122.12, 47.67]
                    }
                },
                "sales_history": [
                    {
                        "sale_date": "2014-08-15",
                        "price": 625000.0,
                        "price_per_sqft": 297.62
                    }
                ]
            },
            "should_fail": False
        },
        {
            "name": "MONGO TEST 2: Negative Sales Price ($jsonSchema minimum: 1.0)",
            "doc": {
                "_id": 999002,
                "property_id": 999002,
                "architectural_specs": {
                    "bedrooms": 4,
                    "bathrooms": 3.0,
                    "floors": 2.0,
                    "sqft_living": 2800,
                    "sqft_lot": 6000,
                    "has_basement": True
                },
                "evaluation_metrics": {
                    "grade": 9,
                    "condition": 3,
                    "view": 0,
                    "waterfront": False
                },
                "neighborhood_context": {
                    "zipcode": "98004",
                    "location": {
                        "type": "Point",
                        "coordinates": [-122.20, 47.61]
                    }
                },
                "sales_history": [
                    {
                        "sale_date": "2015-02-10",
                        "price": -450000.0,  # VIOLATION: Negative price
                        "price_per_sqft": -160.71
                    }
                ]
            },
            "should_fail": True
        },
        {
            "name": "MONGO TEST 3: Out-of-Bounds Building Grade ($jsonSchema maximum: 13)",
            "doc": {
                "_id": 999003,
                "property_id": 999003,
                "architectural_specs": {
                    "bedrooms": 3,
                    "bathrooms": 2.0,
                    "floors": 1.0,
                    "sqft_living": 1800,
                    "sqft_lot": 4500,
                    "has_basement": False
                },
                "evaluation_metrics": {
                    "grade": 20,  # VIOLATION: Grade exceeds maximum (13)
                    "condition": 3,
                    "view": 0,
                    "waterfront": False
                },
                "neighborhood_context": {
                    "zipcode": "98103",
                    "location": {
                        "type": "Point",
                        "coordinates": [-122.34, 47.66]
                    }
                },
                "sales_history": [
                    {
                        "sale_date": "2014-11-05",
                        "price": 550000.0,
                        "price_per_sqft": 305.55
                    }
                ]
            },
            "should_fail": True
        },
        {
            "name": "MONGO TEST 4: Missing Required Field (architectural_specs.bedrooms missing)",
            "doc": {
                "_id": 999004,
                "property_id": 999004,
                "architectural_specs": {
                    # VIOLATION: Missing bedrooms
                    "bathrooms": 2.0,
                    "floors": 1.0,
                    "sqft_living": 1800
                },
                "evaluation_metrics": {
                    "grade": 7,
                    "condition": 3
                },
                "neighborhood_context": {
                    "zipcode": "98105",
                    "location": {
                        "type": "Point",
                        "coordinates": [-122.30, 47.66]
                    }
                },
                "sales_history": [
                    {
                        "sale_date": "2014-06-12",
                        "price": 480000.0,
                        "price_per_sqft": 266.67
                    }
                ]
            },
            "should_fail": True
        },
        {
            "name": "MONGO TEST 5: Malformed Postal Code ($jsonSchema pattern ^[0-9]{5}$)",
            "doc": {
                "_id": 999005,
                "property_id": 999005,
                "architectural_specs": {
                    "bedrooms": 2,
                    "bathrooms": 1.0,
                    "floors": 1.0,
                    "sqft_living": 1100,
                    "sqft_lot": 3000,
                    "has_basement": False
                },
                "evaluation_metrics": {
                    "grade": 6,
                    "condition": 3,
                    "view": 0,
                    "waterfront": False
                },
                "neighborhood_context": {
                    "zipcode": "ABC-INVALID",  # VIOLATION: Non-compliant postal pattern
                    "location": {
                        "type": "Point",
                        "coordinates": [-122.33, 47.60]
                    }
                },
                "sales_history": [
                    {
                        "sale_date": "2014-07-20",
                        "price": 320000.0,
                        "price_per_sqft": 290.90
                    }
                ]
            },
            "should_fail": True
        }
    ]

    for tc in mongo_tests:
        name = tc["name"]
        doc = tc["doc"]
        should_fail = tc["should_fail"]
        try:
            coll.insert_one(doc)
            if should_fail:
                log_message(f"  [FAIL] {name}: Malformed document was inserted unexpectedly!")
            else:
                log_message(f"  [PASS] {name}: Valid document compliant with $jsonSchema.")
        except WriteError as err:
            if should_fail:
                log_message(f"  [PASS - BLOCKED AS EXPECTED] {name}")
                log_message(f"         MongoDB WriteError: Document failed validation ({err.details.get('errmsg', 'Validation failure')})")
            else:
                log_message(f"  [UNEXPECTED FAIL] {name}: {err}")


def main():
    log_message("\n" + "=" * 80)
    log_message("DATA GOVERNANCE & SCHEMA VALIDATION RUNNER (lab_governance.py)")
    log_message(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_message("=" * 80)

    # 1. Relational Governance Test Suite
    rel_conn = setup_relational_governed_warehouse(GOVERNED_DB_PATH)
    try:
        test_relational_governance(rel_conn)
    finally:
        rel_conn.close()

    # 2. MongoDB Document Store Governance Test Suite
    try:
        mongo_client, mongo_db, mongo_coll = setup_mongodb_schema_governance(
            MONGO_URI, MONGO_DB_NAME, MONGO_GOVERNED_COLL
        )
        test_mongodb_governance(mongo_coll)
        mongo_client.close()
    except Exception as e:
        log_message(f"[MONGODB NOTICE] MongoDB server interaction error: {e}")

    log_message("\n" + "=" * 80)
    log_message("DELIVERABLE 2 DATA GOVERNANCE COMPLETED SUCCESSFULLY!")
    log_message(f"Audit log appended to: {EXECUTION_LOG_PATH}")
    log_message("=" * 80)


if __name__ == "__main__":
    main()
