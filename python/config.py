"""Cấu hình dùng chung."""
import os
from datetime import timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
DATA_DIR = os.getenv("DATA_DIR", "/data")
BRONZE_DB = os.path.join(DATA_DIR, "bronze", "bronze.sqlite")   # SQLite, OLTP
SILVER_DB = os.path.join(DATA_DIR, "silver", "silver.duckdb")   # DuckDB, OLAP
GOLD_DB = os.path.join(DATA_DIR, "gold", "gold.duckdb")         # DuckDB, OLAP
RAW_DIR = os.getenv("RAW_DIR", os.path.join(DATA_DIR, "bronze", "json"))
LEGACY_DB = os.getenv("DUCKDB_PATH", os.path.join(DATA_DIR, "stock.duckdb"))  # DB cũ, chỉ để di chuyển
