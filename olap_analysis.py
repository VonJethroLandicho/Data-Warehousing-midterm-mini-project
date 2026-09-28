import sqlite3
import pymongo
from config import SQLITE_DB_PATH, MONGO_URI, MONGO_DB_NAME, MONGO_COLL_NAME

def run_sqlite_analysis():
    print("======================================================================")
    print("OLAP ANALYSIS: SQLITE (RELATIONAL STAR SCHEMA)")
    print("======================================================================")
    
    conn = None
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cur = conn.cursor()
        
        sqlite_query = """
        WITH MonthlyStats AS (
            SELECT 
                d.year,
                d.month,
                SUM(f.price) as total_sales,
                SUM(f.sqft_living) as total_sqft,
                (SUM(f.price) / SUM(f.sqft_living)) as avg_price_per_sqft
            FROM fact_property_sales f
            JOIN dim_date d ON f.date_id = d.date_id
            GROUP BY d.year, d.month
        ),
        WindowedStats AS (
            SELECT
                year,
                month,
                avg_price_per_sqft,
                LAG(avg_price_per_sqft) OVER (ORDER BY year, month) as prev_price_per_sqft,
                total_sales,
                SUM(total_sales) OVER (ORDER BY year, month) as running_total_sales
            FROM MonthlyStats
        )
        SELECT 
            year,
            month,
            avg_price_per_sqft,
            prev_price_per_sqft,
            CASE 
                WHEN prev_price_per_sqft IS NULL OR prev_price_per_sqft = 0 THEN 0.0 
                ELSE ((avg_price_per_sqft - prev_price_per_sqft) / prev_price_per_sqft) * 100.0 
            END as pct_change,
            total_sales,
            running_total_sales
        FROM WindowedStats
        ORDER BY year, month;
        """
        
        cur.execute(sqlite_query)
        rows = cur.fetchall()
        
        print("Query: Monthly Price Per SqFt Trends with Percentage Change and Running Totals\n")
        print(f"{'Year':<6} | {'Month':<6} | {'Avg Price/SqFt ($)':<20} | {'Prev Price/SqFt ($)':<20} | {'% Change':<10} | {'Total Sales ($)':<20} | {'Running Total ($)':<20}")
        print("-" * 115)
        for row in rows:
            prev = f"{row[3]:.2f}" if row[3] is not None else "NULL"
            print(f"{row[0]:<6} | {row[1]:<6} | {row[2]:<20.2f} | {prev:<20} | {row[4]:<10.2f} | {row[5]:<20.2f} | {row[6]:<20.2f}")
            
    except Exception as e:
        print(f"SQLite Error: {e}")
    finally:
        if conn:
            conn.close()
            print("\n[SQLite connection closed successfully]")

def run_mongodb_analysis():
    print("\n======================================================================")
    print("OLAP ANALYSIS: MONGODB (DOCUMENT STORE)")
    print("======================================================================")
    
    client = None
    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client[MONGO_DB_NAME]
        collection = db[MONGO_COLL_NAME]
        
        pipeline = [
            {
                "$facet": {
                    "by_bedrooms": [
                        { "$group": { "_id": "$architectural_specs.bedrooms", "count": { "$sum": 1 } } },
                        { "$sort": { "_id": 1 } }
                    ],
                    "by_grade": [
                        { "$group": { "_id": "$evaluation_metrics.grade", "count": { "$sum": 1 }, "avg_sqft": { "$avg": "$architectural_specs.sqft_living" } } },
                        { "$sort": { "_id": 1 } }
                    ],
                    "overall_metrics": [
                        { "$unwind": "$sales_history" },
                        { "$group": { 
                            "_id": None, 
                            "avg_price": { "$avg": "$sales_history.price" },
                            "avg_price_per_sqft": { "$avg": "$sales_history.price_per_sqft" },
                            "total_sales_volume": { "$sum": "$sales_history.price" }
                        }}
                    ]
                }
            }
        ]
        
        results = list(collection.aggregate(pipeline))[0]
        
        print("Query: Multi-faceted Aggregation (Bedrooms, Grade, and Overall Sales Metrics)\n")
        
        print("--- Facet 1: Property Distribution by Bedrooms ---")
        print(f"{'Bedrooms':<10} | {'Property Count':<15}")
        print("-" * 30)
        for doc in results['by_bedrooms']:
            print(f"{doc['_id']:<10} | {doc['count']:<15}")
            
        print("\n--- Facet 2: Average Living SqFt by Grade ---")
        print(f"{'Grade':<10} | {'Avg SqFt':<15} | {'Property Count':<15}")
        print("-" * 45)
        for doc in results['by_grade']:
            print(f"{doc['_id']:<10} | {doc['avg_sqft']:<15.2f} | {doc['count']:<15}")
            
        print("\n--- Facet 3: Overall Sales Metrics ---")
        overall = results['overall_metrics'][0]
        print(f"Average Price: ${overall['avg_price']:,.2f}")
        print(f"Average Price Per SqFt: ${overall['avg_price_per_sqft']:,.2f}")
        print(f"Total Sales Volume: ${overall['total_sales_volume']:,.2f}")
        
    except Exception as e:
        print(f"MongoDB Error: {e}")
    finally:
        if client:
            client.close()
            print("\n[MongoDB connection closed successfully]")

if __name__ == "__main__":
    run_sqlite_analysis()
    run_mongodb_analysis()
