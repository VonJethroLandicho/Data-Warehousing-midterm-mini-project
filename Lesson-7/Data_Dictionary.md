# Technical Data Dictionary Document
**Data Warehousing (LEC/LAB) — Lesson 7: Performance Tuning & Data Mart Creation**  
**Group 10: Real Estate Property Listing & Regional Market Value Warehouse**  
**Instructor: Prof. Rob Malitao** | **Date: October 2026**

## 1. Executive Summary & Warehouse Architecture
This data dictionary provides comprehensive metadata documentation for the Group 10 Real Estate Data Warehouse. It details the relational star schema (SQLite), strict data governance constraints, MongoDB document store schema, B-Tree performance indexes, and the materialized Real Estate Departmental Data Mart (`property_valuation_mart.db`).

## 2. Core Relational Star Schema (SQLite: `warehouse.db`)
### Table: `dim_date`
*Temporal dimension providing calendar attributes, quarterly partitioning, and weekend flags.*

| Column Name | Data Type | Constraints | Key Type | Source Mapping | Business Definition |
| --- | --- | --- | --- | --- | --- |
| date_id | INTEGER | PRIMARY KEY | PK | date (derived) | Surrogate integer date key formatted as YYYYMMDD |
| full_date | TEXT | NOT NULL | Attribute | date | Normalized ISO calendar date string (YYYY-MM-DD) |
| year | INTEGER | NOT NULL, 1900-2100 | Attribute | date (extracted) | Calendar year of property sale transaction |
| quarter | INTEGER | NOT NULL, 1-4 | Attribute | date (extracted) | Fiscal/calendar quarter (Q1 through Q4) |
| month | INTEGER | NOT NULL, 1-12 | Attribute | date (extracted) | Numerical calendar month (1 through 12) |
| month_name | TEXT | NOT NULL | Attribute | date (extracted) | Full textual month designation (e.g., 'May') |
| day | INTEGER | NOT NULL, 1-31 | Attribute | date (extracted) | Calendar day of month (1 through 31) |
| day_of_week | INTEGER | NOT NULL, 0-6 | Attribute | date (extracted) | Day of week index (0=Monday, 6=Sunday) |
| day_name | TEXT | NOT NULL | Attribute | date (extracted) | Full textual day of week name (e.g., 'Friday') |
| is_weekend | INTEGER | NOT NULL, 0 or 1 | Attribute | date (derived) | Binary boolean flag: 1 if Saturday/Sunday, else 0 |

### Table: `dim_location`
*Geographical dimension capturing postal zones and precise GPS centroids.*

| Column Name | Data Type | Constraints | Key Type | Source Mapping | Business Definition |
| --- | --- | --- | --- | --- | --- |
| location_id | INTEGER | PRIMARY KEY AUTO | PK | Derived ID | Surrogate geographic location identifier |
| zipcode | TEXT | NOT NULL, 5-digits | Attribute | zipcode | Standard 5-digit United States postal code |
| latitude | REAL | NOT NULL, [-90, 90] | Attribute | lat | Geodetic latitude coordinate in decimal degrees |
| longitude | REAL | NOT NULL, [-180, 180] | Attribute | long | Geodetic longitude coordinate in decimal degrees |

### Table: `dim_property`
*Physical asset dimension holding structural vintage and neighborhood reference footprints.*

| Column Name | Data Type | Constraints | Key Type | Source Mapping | Business Definition |
| --- | --- | --- | --- | --- | --- |
| property_id | INTEGER | PRIMARY KEY | PK | id | Unique public parcel identification number |
| yr_built | INTEGER | NOT NULL, >= 1800 | Attribute | yr_built | Original construction year of the main structure |
| yr_renovated | INTEGER | NOT NULL, >= 0 | Attribute | yr_renovated | Most recent major renovation year (0 if never renovated) |
| is_renovated | INTEGER | NOT NULL, 0 or 1 | Attribute | Derived flag | Binary flag indicating structural restoration (1=Yes, 0=No) |
| sqft_living15 | INTEGER | NOT NULL, > 0 | Attribute | sqft_living15 | Average interior living space of the nearest 15 neighboring homes |
| sqft_lot15 | INTEGER | NOT NULL, > 0 | Attribute | sqft_lot15 | Average parcel land area of the nearest 15 neighboring homes |

### Table: `dim_condition_grade`
*Structural assessment dimension storing building construction quality and site vistas.*

| Column Name | Data Type | Constraints | Key Type | Source Mapping | Business Definition |
| --- | --- | --- | --- | --- | --- |
| grade_condition_id | INTEGER | PRIMARY KEY AUTO | PK | Derived ID | Surrogate structural rating identifier |
| grade | INTEGER | NOT NULL, 1-13 | Attribute | grade | Official King County building construction grade (1=Low, 13=Mansion) |
| condition | INTEGER | NOT NULL, 1-5 | Attribute | condition | Physical maintenance condition rating (1=Poor, 5=Excellent) |
| view | INTEGER | NOT NULL, 0-4 | Attribute | view | Visual scenic view quality score (0=None, 4=Panoramic) |
| waterfront | INTEGER | NOT NULL, 0 or 1 | Attribute | waterfront | Binary indicator: 1 if parcel fronts a body of water, else 0 |

### Table: `fact_property_sales`
*Central transactional fact table recording completed real estate sales and metrics.*

| Column Name | Data Type | Constraints | Key Type | Source Mapping | Business Definition |
| --- | --- | --- | --- | --- | --- |
| sale_id | INTEGER | PRIMARY KEY AUTO | PK | Auto Seq | Unique transactional surrogate sales identifier |
| property_id | INTEGER | NOT NULL | FK | id | Foreign key linking to dim_property(property_id) |
| date_id | INTEGER | NOT NULL | FK | Derived date | Foreign key linking to dim_date(date_id) |
| location_id | INTEGER | NOT NULL | FK | Derived loc | Foreign key linking to dim_location(location_id) |
| grade_condition_id | INTEGER | NOT NULL | FK | Derived grade | Foreign key linking to dim_condition_grade(grade_condition_id) |
| price | REAL | NOT NULL, CHECK > 0 | Measure | price | Total closing sales transaction price in USD ($) |
| sqft_living | INTEGER | NOT NULL, CHECK > 0 | Measure | sqft_living | Interior living area of the property in square feet |
| sqft_lot | INTEGER | NOT NULL, CHECK > 0 | Measure | sqft_lot | Total land parcel lot area in square feet |
| price_per_sqft | REAL | NOT NULL, CHECK > 0 | Measure | Calculated | Unit valuation metric: price divided by sqft_living ($/sqft) |
| bedrooms | INTEGER | NOT NULL, CHECK >= 0 | Attribute | bedrooms | Total count of bedrooms in the dwelling |
| bathrooms | REAL | NOT NULL, CHECK >= 0 | Attribute | bathrooms | Total count of bathrooms (quarter/half increments allowed) |
| floors | REAL | NOT NULL, CHECK > 0 | Attribute | floors | Number of vertical finished floors / stories |
| sqft_above | INTEGER | NOT NULL, CHECK >= 0 | Measure | sqft_above | Interior living space located strictly above grade level |
| sqft_basement | INTEGER | NOT NULL, CHECK >= 0 | Measure | sqft_basement | Subterranean basement interior area in square feet |
| has_basement | INTEGER | NOT NULL, 0 or 1 | Attribute | Derived flag | Binary flag indicating basement existence (1=Yes, 0=No) |

## 3. Data Governance & Relational Constraint Rules
Strict DDL constraints enforced in `governed_warehouse.db` to prevent invalid or corrupted records:

| Rule Category | Target Table | Target Column(s) | Enforced Constraint | Business Rationale |
| --- | --- | --- | --- | --- |
| Financial Integrity | fact_property_sales | price | CHECK (price > 0.0) | Guarantees transaction price is strictly positive. |
| Physical Integrity | fact_property_sales | sqft_living, sqft_lot | CHECK (sqft > 0) | Prevents zero or negative dwelling space. |
| Unit Rate Integrity | fact_property_sales | price_per_sqft | CHECK (price_per_sqft > 0.0) | Enforces calculated valuation rate positivity. |
| Structural Bounds | dim_condition_grade | grade | CHECK (grade BETWEEN 1 AND 13) | Enforces official King County grading codes. |
| Maintenance Bounds | dim_condition_grade | condition | CHECK (condition BETWEEN 1 AND 5) | Validates inspection maintenance rating scale. |
| Temporal Integrity | dim_property | yr_built | CHECK (yr_built BETWEEN 1800 AND 2050) | Blocks corrupted vintage years. |
| Spatial Bounds | dim_location | latitude, longitude | CHECK (lat [-90,90], long [-180,180]) | Blocks out-of-range geodetic coordinates. |
| Referential Integrity | fact_property_sales | Foreign Keys | NOT NULL, ON DELETE RESTRICT | Guarantees no orphaned fact rows. |

## 4. Document Store Schema & $jsonSchema Governance (MongoDB)
Enforces strict document validation on `property_architectural_features_governed` with `validationLevel='strict'`:

| BSON Field Path | BSON Type | Validation Rule | Business Definition |
| --- | --- | --- | --- |
| `_id / property_id` | int / long | Required, Unique | Unique parcel identification. |
| `architectural_specs.bedrooms` | int | minimum: 0 | Non-negative bedroom count. |
| `architectural_specs.bathrooms` | double / int | minimum: 0.0 | Non-negative bathroom count. |
| `architectural_specs.sqft_living` | int | minimum: 1 | Strictly positive interior living area. |
| `evaluation_metrics.grade` | int | minimum: 1, maximum: 13 | Validates construction quality rating. |
| `evaluation_metrics.condition` | int | minimum: 1, maximum: 5 | Validates maintenance condition. |
| `neighborhood_context.zipcode` | string | pattern: `^[0-9]{5}$` | Enforces 5-digit US postal pattern. |
| `neighborhood_context.location` | object | GeoJSON Point `[lng, lat]` | 2dsphere spatial indexing. |
| `sales_history.price` | double / int | minimum: 1.0 | Blocks negative/zero closing prices. |

## 5. Departmental Data Mart Schema (`property_valuation_mart.db`)
### Data Mart Table: `monthly_property_valuation_mart`
*Downstream aggregate table summarizing chronological market pricing and volume.*

| Column Name | Data Type | Constraints | Business Definition |
| --- | --- | --- | --- |
| year | INTEGER | NOT NULL | Calendar transaction year |
| month | INTEGER | NOT NULL | Calendar transaction month (1-12) |
| month_name | TEXT | NOT NULL | Full month name (e.g., 'May') |
| total_transactions | INTEGER | NOT NULL | Total number of closed property sales |
| total_sales_volume | REAL | NOT NULL | Total dollar sum of closed transactions ($) |
| avg_property_price | REAL | NOT NULL | Arithmetic mean property sale price ($) |
| min_property_price | REAL | NOT NULL | Minimum closed property price in the month ($) |
| max_property_price | REAL | NOT NULL | Maximum closed property price in the month ($) |
| avg_price_per_sqft | REAL | NOT NULL | Mean market unit price per square foot ($/sqft) |
| total_sqft_living | INTEGER | NOT NULL | Cumulative living square footage sold |
| avg_sqft_living | REAL | NOT NULL | Average interior living area of sold dwellings |

### Data Mart Table: `regional_zipcode_valuation_mart`
*Downstream aggregate table partitioning real estate performance by postal zones.*

| Column Name | Data Type | Constraints | Business Definition |
| --- | --- | --- | --- |
| zipcode | TEXT | PRIMARY / INDEXED | 5-digit regional postal code |
| centroid_latitude | REAL | NOT NULL | Average latitude centroid for the postal region |
| centroid_longitude | REAL | NOT NULL | Average longitude centroid for the postal region |
| total_listings_sold | INTEGER | NOT NULL | Volume of properties sold in the postal zone |
| total_regional_sales_volume | REAL | NOT NULL | Aggregate dollar sales volume in the zipcode ($) |
| avg_market_value | REAL | NOT NULL | Mean residential property market valuation ($) |
| avg_price_per_sqft | REAL | NOT NULL | Mean unit price per living square foot ($/sqft) |
| avg_living_area_sqft | REAL | NOT NULL | Mean interior living space in square feet |
| waterfront_property_count | INTEGER | NOT NULL | Number of waterfront properties sold in region |
| avg_bedrooms | REAL | NOT NULL | Mean bedroom count across regional homes |
| avg_bathrooms | REAL | NOT NULL | Mean bathroom count across regional homes |

### Data Mart Table: `structural_grade_valuation_mart`
*Downstream aggregate table evaluating valuation premiums by architectural grade tiers.*

| Column Name | Data Type | Constraints | Business Definition |
| --- | --- | --- | --- |
| grade | INTEGER | NOT NULL | King County construction grade rating (1-13) |
| condition | INTEGER | NOT NULL | Maintenance condition score (1-5) |
| market_tier | TEXT | NOT NULL | Categorical tier (Economy, Mid-Market, Executive, Luxury Estate) |
| property_count | INTEGER | NOT NULL | Number of properties belonging to this tier |
| aggregate_tier_valuation | REAL | NOT NULL | Total financial sales volume within tier ($) |
| avg_valuation | REAL | NOT NULL | Mean transaction sales price in tier ($) |
| avg_price_per_sqft | REAL | NOT NULL | Mean unit price per square foot in tier ($/sqft) |
| avg_sqft_living | REAL | NOT NULL | Mean interior living area in square feet |
| avg_lot_size | REAL | NOT NULL | Mean land parcel size in square feet |

## 6. Index Catalog & Performance Tuning Audit
| Index Name | Target Table | Indexed Columns | Index Type | Tuning & Query Plan Impact |
| --- | --- | --- | --- | --- |
| idx_fact_date | fact_property_sales | date_id | Single B-Tree | Optimizes temporal joins to dim_date and monthly filtering |
| idx_fact_location | fact_property_sales | location_id | Single B-Tree | Accelerates regional spatial joins and postal aggregations |
| idx_fact_grade | fact_property_sales | grade_condition_id | Single B-Tree | Accelerates joins on property construction ratings |
| idx_fact_property | fact_property_sales | property_id | Single B-Tree | Speeds up parcel lookup and property history tracing |
| idx_dim_loc_zip | dim_location | zipcode | Single B-Tree | Accelerates zipcode filtering and spatial grouping |
| idx_dim_date_ym | dim_date | year, month | Compound B-Tree | Enables index skip scans on year/month time-series queries |
| idx_fact_date_price | fact_property_sales | date_id, price | Compound B-Tree | Eliminates table scans when querying date ranges with price thresholds |
| idx_fact_loc_price_sqft | fact_property_sales | location_id, price, sqft_living | Compound Covering | Directly satisfies regional valuation queries without table heap reads |
| idx_fact_grade_price | fact_property_sales | grade_condition_id, price | Compound B-Tree | Replaces full table scans with index searches for luxury grade filtering |
| idx_fact_bed_price | fact_property_sales | bedrooms, price | Compound B-Tree | Accelerates bedroom-level market segment aggregations |
| 2dsphere (Mongo) | property_features | neighborhood_context.location | 2dsphere Spatial | Enables geospatial indexing and radius queries ($near, $geoWithin) |
