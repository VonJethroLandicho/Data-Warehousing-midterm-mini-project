# Data Warehousing - Milestone 2
**Group 10: Real Estate Property Listing & Regional Market Value Warehouse**

## 1. Property Valuation Findings
Based on our multi-engine data analysis, we identified several key characteristics regarding property valuation in the region:
* **Overall Market Averages**: The average property price is **$540,088.14**, translating to a market-wide average of **$264.16 per square foot**.
* **Total Volume**: The total recorded sales volume across all properties equates to an impressive **$11,672,925,008.00**.
* **Property Size & Features (MongoDB Facets)**: 
  * The housing market is heavily dominated by 3-bedroom (9,732 properties) and 4-bedroom (6,849 properties) homes. 
  * Property grades correlate strongly with living space. The most common structural grade (Grade 7) has an average living area of 1,689 sqft. Meanwhile, ultra-premium Grade 13 properties average a massive 7,483 sqft of living space.

## 2. Market Trends (Price Per SqFt Over Time)
By leveraging window functions on our relational sales history, we tracked the month-over-month trajectory of price per square foot:
* **2014 Stability**: Between May and December 2014, property values remained relatively stable, fluctuating slightly between **$250.78 and $261.63 per sqft**.
* **2015 Growth Surge**: The market saw a noticeable upward trend beginning in early 2015. After sitting at $252.54 per sqft in February 2015, the price surged by **6.53%** in March (up to $269.03/sqft). This upward momentum continued, peaking at **$275.79 per sqft** by May 2015.

## 3. Multi-Engine Query Architecture Explained
Our dual-engine warehouse utilizes specialized query capabilities across SQLite and MongoDB to efficiently process analytics:

### Relational Engine (SQLite)
To analyze time-series trends, we used advanced SQL features:
* **CTE (Common Table Expressions)**: `WITH MonthlyStats AS (...)` was used to cleanly organize the data into temporary result sets, separating the aggregation of monthly averages from the complex calculations.
* **LAG()**: This window function allowed us to look back at the previous month's average price per sqft directly within the same row, enabling us to calculate the exact month-over-month percentage change without needing complex self-joins.
* **SUM() OVER()**: We utilized this window function to calculate the running total of sales volume. It continuously adds the current month's sales to all previous months' sales in chronological order.

### Document Engine (MongoDB)
To analyze the nested architectural properties, we utilized the MongoDB Aggregation Pipeline:
* **$facet**: This powerful stage allowed us to run multiple independent analytical pipelines within a single database query. Instead of running three separate queries, `$facet` let us simultaneously compute the distribution by bedrooms, the average sqft grouped by property grade, and the overall market sales metrics in one unified pass over the documents.
* **$unwind**: We used this operator within our facet to flatten the nested `sales_history` arrays, allowing us to accurately compute the overall average price and total sales volume directly from the document store.
