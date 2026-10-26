# Milestone 1: Enterprise Multi-Engine Data Warehouse & BI System
**Course:** Data Warehousing (LEC/LAB) — Lesson 8 Final Project  
**Domain:** Real Estate Property Listing & Regional Market Value Warehouse (Group 10)  
**Instructor:** Prof. Rob Malitao  
**Submission Due:** October 26, 2026  

---

## Deliverables Checklist (Milestone 1)

All mandatory Milestone 1 deliverables specified in the Final Project guidelines have been accomplished and packaged inside this directory (`milestone 1/`):

| # | Required Deliverable | Target Location | Description & Verification |
|---|:---|:---|:---|
| 1 | **Architectural Design Document / ERD (.pdf)** | [`Architectural_Design_Document.pdf`](./Architectural_Design_Document.pdf) | Formal multi-page executive document with high-resolution Star Schema ERD diagram, complete data dictionary, relational DDL constraints, and MongoDB `$jsonSchema` blueprints. *(Companion Markdown: [`Architectural_Design_Document.md`](./Architectural_Design_Document.md))* |
| 2 | **Python ETL & Validation Script (`capstone_etl.py`)** | [`capstone_etl.py`](./capstone_etl.py) | Production-grade automated script that ingests from `./landing_zone/`, executes data cleansing (deduplication, ISO standardization, currency stripping), sets up strict database constraints, loads both SQLite and MongoDB concurrently, and runs unit tests. |
| 3 | **ETL Execution Audit Log (`etl_execution_log.txt`)** | [`etl_execution_log.txt`](./etl_execution_log.txt) | Detailed console & file audit trail recording pre- and post-cleansing row counts, database insertion totals, and execution proofs for relational & document governance tests. |
| 4 | **Operational Landing Zone (`./landing_zone/`)** | [`landing_zone/`](./landing_zone/) | Directory containing raw anomaly-ridden operational files: [`raw_property_sales.csv`](./landing_zone/raw_property_sales.csv) (5,720 rows) and [`raw_property_feedback.json`](./landing_zone/raw_property_feedback.json) (1,295 documents). |

---

## Directory Structure

```text
milestone 1/
│
├── landing_zone/                               # Raw operational data repository
│   ├── raw_property_sales.csv                  # Anomaly-ridden sales transactions (duplicates, $, bad dates)
│   └── raw_property_feedback.json              # Semi-structured feedback & inspection logs (missing keys, etc.)
│
├── capstone_etl.py                             # Master ETL & Governance execution script
├── enterprise_warehouse.db                     # Populated SQLite Star Schema Data Warehouse
├── etl_execution_log.txt                       # Complete audit execution log output
│
├── Architectural_Design_Document.pdf           # Executive PDF report with Star Schema ERD and Data Dictionary
├── Architectural_Design_Document.md            # Markdown version of architectural documentation
├── visual_erd.png                              # High-resolution rendered Star Schema ERD diagram
│
├── generate_landing_zone.py                    # Generator script for realistic anomaly-ridden landing zone
├── generate_erd_pdf.py                         # ReportLab/Matplotlib generator script for the PDF deliverable
└── README.md                                   # This milestone briefing and instruction manual
```

---

## Quickstart Instructions

### 1. Prerequisites
Ensure Python 3.10+ and local MongoDB daemon are available:
```powershell
# Python libraries used:
pip install pandas pymongo reportlab matplotlib
```

### 2. Run the Master ETL & Governance Pipeline
To re-run the entire pipeline from scratch, regenerate the database, populate MongoDB, and produce the audit log:
```powershell
python "milestone 1\capstone_etl.py"
```

### 3. Regenerate the Architectural PDF & ERD Diagram
To recompile the official executive PDF document:
```powershell
python "milestone 1\generate_erd_pdf.py"
```

---

## Audit Execution Highlights
* **Sales Cleansing:** 5,720 raw rows extracted $\rightarrow$ 150 duplicate rows dropped $\rightarrow$ 70 invalid/corrupt rows quarantined $\rightarrow$ **5,500 clean rows committed**.
* **Feedback Cleansing:** 1,295 raw documents extracted $\rightarrow$ 65 duplicates dropped $\rightarrow$ 41 invalid documents filtered $\rightarrow$ **1,189 clean documents committed**.
* **SQLite Star Schema:** Loaded `fact_property_sales` (5,500 rows), `dim_property` (5,487 rows), `dim_location` (5,457 rows), `dim_condition_grade` (131 rows), and `dim_date` (331 rows).
* **MongoDB Collections:** Loaded `sales_documents` (5,500 documents) and `feedback_documents` (1,189 documents) under strict `$jsonSchema` validation (`validationLevel="strict"`, `validationAction="error"`).
* **Data Governance Verification:** All 4 multi-engine integrity unit tests (CHECK price, Foreign Key enforcement, MongoDB rating bounds, MongoDB price validation) **PASSED with 100% compliance**.
