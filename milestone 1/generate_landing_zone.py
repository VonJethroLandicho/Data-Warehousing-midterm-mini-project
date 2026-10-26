"""
================================================================================
MILESTONE 1: LANDING ZONE SYNTHETIC GENERATOR WITH REAL-WORLD ANOMALIES
================================================================================
Group 10: Real Estate Property Listing & Regional Market Value Warehouse
Instructor: Prof. Rob Malitao
================================================================================
This script extracts source records from house_data.csv and programmatically
injects realistic enterprise operational anomalies:
  1. Exact duplicate rows (to test deduplication logic)
  2. Dirty currency formatting (e.g., '$540,000.00', ' $1,250,000 ', commas)
  3. Mixed and inconsistent date formats (ISO, MM/DD/YYYY, DD-MM-YYYY, epoch)
  4. Null and missing primary / foreign keys
  5. Whitespace padding and casing inconsistencies
  6. Out-of-bounds metrics (negative prices, zero sqft)
It also generates semi-structured operational inspection & feedback JSON logs
with missing keys, varied dates, and categorical distributions.
================================================================================
"""

import os
import csv
import json
import random
from datetime import datetime, timedelta

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
LANDING_ZONE_DIR = os.path.join(CURRENT_DIR, "landing_zone")
SOURCE_CSV = os.path.join(PROJECT_ROOT, "house_data.csv")

TARGET_CSV = os.path.join(LANDING_ZONE_DIR, "raw_property_sales.csv")
TARGET_JSON = os.path.join(LANDING_ZONE_DIR, "raw_property_feedback.json")

os.makedirs(LANDING_ZONE_DIR, exist_ok=True)


def generate_raw_sales_csv(sample_size=6000):
    print(f"[*] Reading source data from: {SOURCE_CSV}")
    records = []
    with open(SOURCE_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    random.seed(42)
    selected = random.sample(records, min(sample_size, len(records)))
    print(f"[*] Sampled {len(selected)} base operational records.")

    # Incur anomalies
    dirty_records = []
    
    # 1. Normal and mildly dirty records
    for i, row in enumerate(selected):
        new_row = dict(row)
        
        # Inject currency formatting into ~20% of rows
        if i % 5 == 0:
            price_val = float(new_row["price"])
            if i % 10 == 0:
                new_row["price"] = f"${price_val:,.2f}"
            elif i % 15 == 0:
                new_row["price"] = f" ${int(price_val):,} "
            else:
                new_row["price"] = f"${int(price_val)}"

        # Inject mixed date formats into ~25% of rows
        if i % 4 == 0:
            raw_date = new_row["date"][:8] # YYYYMMDD
            try:
                dt = datetime.strptime(raw_date, "%Y%m%d")
                if i % 8 == 0:
                    new_row["date"] = dt.strftime("%m/%d/%Y")  # US style
                elif i % 12 == 0:
                    new_row["date"] = dt.strftime("%d-%m-%Y")  # Hyphenated
                elif i % 16 == 0:
                    new_row["date"] = dt.strftime("%Y-%m-%d")  # ISO style
                else:
                    new_row["date"] = f"{dt.strftime('%Y-%m-%d')} 00:00:00"
            except Exception:
                pass

        # Inject string padding into zipcode
        if i % 7 == 0:
            new_row["zipcode"] = f"  {new_row['zipcode']}  "

        dirty_records.append(new_row)

    # 2. Inject duplicate rows (150 exact duplicates)
    duplicates = [dict(r) for r in random.sample(dirty_records, 150)]
    dirty_records.extend(duplicates)
    print(f"[*] Injected {len(duplicates)} duplicate records.")

    # 3. Inject null / missing keys (40 rows)
    for _ in range(40):
        corrupted = dict(random.choice(selected))
        corrupt_type = random.choice(["missing_id", "missing_price", "missing_date", "missing_zipcode"])
        if corrupt_type == "missing_id":
            corrupted["id"] = ""
        elif corrupt_type == "missing_price":
            corrupted["price"] = ""
        elif corrupt_type == "missing_date":
            corrupted["date"] = "NULL"
        elif corrupt_type == "missing_zipcode":
            corrupted["zipcode"] = ""
        dirty_records.append(corrupted)
    print(f"[*] Injected 40 corrupted/null key records.")

    # 4. Inject business rule constraint violations (30 rows: negative price, 0 sqft)
    for _ in range(15):
        neg_price = dict(random.choice(selected))
        neg_price["price"] = f"-{float(neg_price['price']):.2f}"
        dirty_records.append(neg_price)

    for _ in range(15):
        zero_sqft = dict(random.choice(selected))
        zero_sqft["sqft_living"] = "0"
        dirty_records.append(zero_sqft)
    print(f"[*] Injected 30 constraint violation records (negative prices, zero living sqft).")

    # Shuffle to mix anomalies realistically
    random.shuffle(dirty_records)

    fieldnames = list(selected[0].keys())
    with open(TARGET_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dirty_records)

    print(f"[+] Successfully wrote {len(dirty_records)} raw anomaly-ridden records to: {TARGET_CSV}")
    return len(dirty_records)


def generate_raw_feedback_json(sample_properties, count=1500):
    print(f"[*] Generating {count} semi-structured feedback & inspection documents...")
    categories = ["Buyer", "Seller", "Licensed Inspector", "Certified Appraiser", "Tenant"]
    positive_comments = [
        "Exceptional architectural construction with immaculate hardwood floors and spacious backyard.",
        "Stunning panoramic view of the lake; foundation and structural condition in pristine shape.",
        "Fully renovated gourmet kitchen with quartz countertops and updated HVAC system.",
        "Charming craftsman styling in a quiet, highly desirable neighborhood.",
        "Excellent property layout, ample natural lighting, and well-maintained cedar siding."
    ]
    neutral_comments = [
        "Property shows average wear and tear; roofing may require maintenance within 3-5 years.",
        "Decent mid-century construction; plumbing is functional but vintage.",
        "Interior floorplan is slightly dated, but lot area and location provide strong potential.",
        "Fair property condition. Minor basement dampness noted during inspection."
    ]
    negative_comments = [
        "Severe dry rot observed on exterior porch; electrical panel does not meet code.",
        "Basement foundation shows visible settling cracks; structural reinforcement required.",
        "Plumbing leaks detected in master bathroom; condition grade is significantly degraded.",
        "High localized traffic noise and poor stormwater drainage in the driveway."
    ]
    highlights_pool = [
        "waterfront access", "mountain view", "remodeled kitchen", "hardwood floors",
        "finished basement", "detached garage", "solar panels", "mature landscaping",
        "energy-efficient windows", "central AC", "vaulted ceilings"
    ]

    random.seed(84)
    documents = []

    for i in range(count):
        prop_id = int(random.choice(sample_properties))
        cat = random.choice(categories)
        review_id = f"REV-{100000 + i}"
        
        # Rating & sentiment
        roll = random.random()
        if roll < 0.65:
            rating = random.randint(4, 5)
            comments = random.choice(positive_comments)
            passed = True
            sentiment = round(random.uniform(0.60, 0.98), 2)
        elif roll < 0.85:
            rating = 3
            comments = random.choice(neutral_comments)
            passed = True
            sentiment = round(random.uniform(0.10, 0.55), 2)
        else:
            rating = random.randint(1, 2)
            comments = random.choice(negative_comments)
            passed = False
            sentiment = round(random.uniform(-0.85, -0.10), 2)

        # Dates with mixed formats
        days_ago = random.randint(30, 800)
        dt = datetime(2015, 6, 1) - timedelta(days=days_ago)
        if i % 6 == 0:
            review_date = dt.strftime("%m/%d/%Y")
        elif i % 10 == 0:
            review_date = dt.strftime("%d-%m-%Y")
        elif i % 15 == 0:
            review_date = int(dt.timestamp())
        else:
            review_date = dt.strftime("%Y-%m-%d")

        doc = {
            "review_id": review_id,
            "property_id": prop_id,
            "review_date": review_date,
            "rating": rating,
            "reviewer_category": cat,
            "inspection_passed": passed,
            "sentiment_score": sentiment,
            "comments": comments,
            "architectural_highlights": random.sample(highlights_pool, random.randint(1, 4))
        }
        documents.append(doc)

    # Incur anomalies in JSON:
    # 1. Duplicate review IDs (40 duplicates)
    dup_docs = [dict(d) for d in random.sample(documents, 40)]
    documents.extend(dup_docs)

    # 2. Missing required keys (30 docs)
    for _ in range(30):
        corrupt_doc = dict(random.choice(documents))
        key_to_del = random.choice(["property_id", "rating", "inspection_passed", "review_date"])
        corrupt_doc.pop(key_to_del, None)
        documents.append(corrupt_doc)

    # 3. Invalid rating out of bounds (1-5 rule violation) (25 docs)
    for _ in range(25):
        invalid_rating_doc = dict(random.choice(documents))
        invalid_rating_doc["rating"] = random.choice([0, 6, 10, -2])
        documents.append(invalid_rating_doc)

    random.shuffle(documents)

    with open(TARGET_JSON, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2)

    print(f"[+] Successfully wrote {len(documents)} raw semi-structured feedback records to: {TARGET_JSON}")
    return len(documents)


if __name__ == "__main__":
    sales_count = generate_raw_sales_csv(sample_size=5500)
    
    # Read unique property IDs to link feedback
    sample_ids = []
    with open(TARGET_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("id") and r["id"].isdigit():
                sample_ids.append(int(r["id"]))

    generate_raw_feedback_json(sample_ids, count=1200)
    print("\n[OK] Landing Zone generated successfully with realistic anomalies.")
