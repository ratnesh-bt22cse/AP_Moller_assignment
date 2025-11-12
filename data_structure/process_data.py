# 1. IMPORT LIBRARIES
import pandas as pd
from sqlalchemy import create_engine
import sqlite3

# Set display options
pd.set_option('display.max_columns', 50)

print("Libraries imported successfully!")

# 2. LOAD DATASETS
data_path = ''

customers = pd.read_csv(data_path + "olist_customers_dataset.csv")
orders = pd.read_csv(data_path + "olist_orders_dataset.csv")
order_items = pd.read_csv(data_path + "olist_order_items_dataset.csv")
payments = pd.read_csv(data_path + "olist_order_payments_dataset.csv")
reviews = pd.read_csv(data_path + "olist_order_reviews_dataset.csv")
products = pd.read_csv(data_path + "olist_products_dataset.csv")
sellers = pd.read_csv(data_path + "olist_sellers_dataset.csv")
geolocation = pd.read_csv(data_path + "olist_geolocation_dataset.csv")
translation = pd.read_csv(data_path + "product_category_name_translation.csv")

print("All CSVs loaded successfully!")
print(f"Orders shape: {orders.shape}")
print(f"Customers shape: {customers.shape}")
print(f"Order items shape: {order_items.shape}")

# 3. CLEAN BASIC FORMATS

# Convert date columns to datetime
date_cols = [
    'order_purchase_timestamp', 'order_approved_at',
    'order_delivered_carrier_date', 'order_delivered_customer_date',
    'order_estimated_delivery_date'
]
for col in date_cols:
    orders[col] = pd.to_datetime(orders[col], errors='coerce')

# Merge product translations (Portuguese to English)
products = products.merge(translation, on='product_category_name', how='left')

print("Date conversions and product translations complete!")

# 4. MERGE LOGIC

# Step 1: Orders + Customers
df = pd.merge(orders, customers, on="customer_id", how="left")

# Step 2: Add Order Items
df = pd.merge(df, order_items, on="order_id", how="left")

# Step 3: Add Products
df = pd.merge(df, products, on="product_id", how="left")

# Step 4: Add Sellers
df = pd.merge(df, sellers, on="seller_id", how="left")

# Step 5: Add Payments
df = pd.merge(df, payments, on="order_id", how="left")

# Step 6: Add Reviews (only review_score)
df = pd.merge(df, reviews[['order_id', 'review_score']], on="order_id", how="left")

print(f"Merged dataset shape: {df.shape}")
print(f"Columns: {len(df.columns)}")

# 5. HANDLE NULL VALUES

# A. Dates - Keep NaT (meaningful)
# B. Product categories
df['product_category_name_english'].fillna('unknown_category', inplace=True)

# Numeric product columns - fill with median
num_cols = [
    'product_name_lenght', 'product_description_lenght', 'product_photos_qty',
    'product_weight_g', 'product_length_cm', 'product_height_cm', 'product_width_cm'
]
for col in num_cols:
    df[col].fillna(df[col].median(), inplace=True)

# C. Payments
df['payment_type'].fillna('unknown', inplace=True)
df['payment_installments'].fillna(1, inplace=True)
df['payment_value'].fillna(0, inplace=True)

# D. Review Scores
df['review_score'].fillna(0, inplace=True)

# E. Sellers
for col in ['seller_city', 'seller_state']:
    df[col].fillna('unknown', inplace=True)

# F. Price / Freight
df['price'].fillna(0, inplace=True)
df['freight_value'].fillna(0, inplace=True)

print("Missing values handled successfully!")
print(f"Remaining nulls: {df.isnull().sum().sum()}")

# 6. FEATURE ENGINEERING

# Delivery delay calculation
df['delivery_delay_days'] = (
    (df['order_delivered_customer_date'] - df['order_estimated_delivery_date'])
    .dt.days
)
df['delivery_delay_days'] = df['delivery_delay_days'].fillna(0)
df['is_delayed'] = (df['delivery_delay_days'] > 0).astype(int)

# Delivery completed flag
df['is_delivered'] = df['order_delivered_customer_date'].notnull().astype(int)

print("Feature engineering complete!")
print(f"New columns: delivery_delay_days, is_delayed, is_delivered")

# 7. CLEAN COLUMN NAMES
df.columns = [col.lower().replace(" ", "_") for col in df.columns]

print("Column names cleaned!")
print(f"Sample columns: {df.columns.tolist()[:10]}")

# 8. SAVE CLEANED OUTPUT

# Save to CSV
df.to_csv("olist_master_clean.csv", index=False)
print("Cleaned CSV saved as olist_master_clean.csv")

# Create SQLite database
engine = create_engine("sqlite:///olist_master_clean.db")
df.to_sql("olist_master", con=engine, index=False, if_exists="replace")
print("SQLite database created: olist_master_clean.db")

print(f"\nFinal dataset shape: {df.shape}")
print(f"Total records: {len(df)}")

# 9. TEST QUERY
conn = sqlite3.connect("olist_master_clean.db")

query = """
SELECT customer_state, ROUND(SUM(price),2) as total_sales
FROM olist_master
GROUP BY customer_state
ORDER BY total_sales DESC
LIMIT 5;
"""
result = pd.read_sql(query, conn)
print("\nTop 5 States by Total Sales:")
print(result)

print("\nAll steps completed successfully! Ready for GenAI/LLM use.")
