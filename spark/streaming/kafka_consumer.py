"""
Spark Streaming Consumer for Real-time Event Processing
Processes events from Kafka in 5-second micro-batches
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
import os

# Create Spark session
spark = SparkSession.builder \
    .appName("EcommerceStreamProcessing") \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
    .config("spark.sql.streaming.checkpointLocation", "/tmp/spark-checkpoint") \
    .config("spark.sql.session.timeZone", "UTC") \
    .config("spark.driver.extraJavaOptions", "-Duser.timezone=UTC") \
    .config("spark.executor.extraJavaOptions", "-Duser.timezone=UTC") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

print("Spark Streaming Consumer Started")
print("=" * 60)

# Define schema for user events
user_event_schema = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("user_id", IntegerType(), False),
    StructField("session_id", StringType(), False),
    StructField("timestamp", StringType(), False),
    StructField("page", StringType(), True),
    StructField("product_id", IntegerType(), True),
    StructField("device_type", StringType(), True),
    StructField("browser", StringType(), True),
    StructField("referrer", StringType(), True),
    StructField("position", IntegerType(), True),
    StructField("source", StringType(), True),
    StructField("quantity", IntegerType(), True)
])

# Define schema for transactions
transaction_schema = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("user_id", IntegerType(), False),
    StructField("session_id", StringType(), False),
    StructField("product_id", IntegerType(), False),
    StructField("quantity", IntegerType(), False),
    StructField("unit_price", DoubleType(), False),
    StructField("total_amount", DoubleType(), False),
    StructField("payment_method", StringType(), True),
    StructField("timestamp", StringType(), False)
])

# Read from Kafka - user_events topic
user_events_df = spark \
    .readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "user_events") \
    .option("startingOffsets", "latest") \
    .load()

# Parse JSON from Kafka
parsed_events = user_events_df \
    .select(from_json(col("value").cast("string"), user_event_schema).alias("data")) \
    .select("data.*") \
    .withColumn("timestamp", to_timestamp(col("timestamp")))

# Real-time aggregations with 5-second tumbling window
event_counts = parsed_events \
    .withWatermark("timestamp", "10 seconds") \
    .groupBy(
        window(col("timestamp"), "5 seconds"),
        col("event_type")
    ) \
    .agg(
        count("*").alias("event_count"),
        approx_count_distinct("user_id").alias("unique_users"),
        approx_count_distinct("session_id").alias("unique_sessions")
    ) \
    .select(
        col("window.start").alias("window_start"),
        col("window.end").alias("window_end"),
        col("event_type"),
        col("event_count").cast("integer"),
        col("unique_users").cast("integer"),
        col("unique_sessions").cast("integer"),
    )


# Function to write to PostgreSQL
def write_to_postgres(batch_df, batch_id):
    """Write aggregated metrics to PostgreSQL"""
    # Optimization: Check if empty before doing anything
    if batch_df.isEmpty():
        return

    print(f"\nWriting batch {batch_id} to PostgreSQL...")
    
    # FIX: Add the timezone directly to the URL string
    # We use 'options=-c%20timezone=UTC' to force the PG session to UTC
    jdbc_url = "jdbc:postgresql://localhost:5432/ecommerce?options=-c%20timezone=UTC"
    
    jdbc_props = {
        "user": "postgres",
        "password": "postgres",
        "driver": "org.postgresql.Driver"
    }

    try:
        batch_df.write.jdbc(
            url=jdbc_url,
            table="realtime_metrics",
            mode="append",
            properties=jdbc_props
        )
        print(f"   Successfully wrote {batch_df.count()} rows.")
        batch_df.show(5, truncate=False)
    except Exception as e:
        print(f"   ERROR writing batch {batch_id}: {e}")


# Console output for monitoring
console_query = event_counts \
    .writeStream \
    .outputMode("update") \
    .format("console") \
    .option("truncate", False) \
    .start()

# Write to PostgreSQL
postgres_query = event_counts \
    .writeStream \
    .foreachBatch(write_to_postgres) \
    .outputMode("update") \
    .option("checkpointLocation", "/tmp/spark-postgres-checkpoint") \
    .start()

print("\nStream processing active!")
print("   - Console output: Real-time metrics")
print("   - PostgreSQL: Writing every 5 seconds")
print("\nPress Ctrl+C to stop\n")

# Wait for termination
postgres_query.awaitTermination()
