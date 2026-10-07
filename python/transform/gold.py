"""Gold (DuckDB, OLAP): mô hình hình sao để truy vấn phân tích.
dim_ticker, dim_date, fact_price_daily, fact_news; dựng lại hoàn toàn từ silver và watchlist mỗi lần chạy."""
import os

import duckdb
import pandas as pd

from config import GOLD_DB, SILVER_DB
from storage import bronze

DIM_DATE_SQL = """
CREATE OR REPLACE TABLE dim_date AS
WITH dates AS (
    SELECT trade_date AS d FROM silver.prices_daily
    UNION ALL SELECT published_date FROM silver.news WHERE published_date IS NOT NULL
),
r AS (SELECT min(d) AS d0, max(d) AS d1 FROM dates),
cal AS (SELECT CAST(unnest(generate_series(d0, d1, INTERVAL 1 DAY)) AS DATE) AS d FROM r)
SELECT d AS date_key, year(d) AS year, month(d) AS month, day(d) AS day,
       weekofyear(d) AS iso_week, isodow(d) AS day_of_week, isodow(d) >= 6 AS is_weekend,
       d IN (SELECT trade_date FROM silver.prices_daily WHERE is_valid) AS is_trading_day
FROM cal
"""

FACT_PRICE_SQL = """
CREATE OR REPLACE TABLE fact_price_daily AS
SELECT ma, trade_date AS date_key, open, high, low, close, adj_close, volume, pct_change, is_adjusted
FROM silver.prices_daily WHERE is_valid
"""

FACT_NEWS_SQL = """
CREATE OR REPLACE TABLE fact_news AS
WITH e AS (
    SELECT * FROM silver.news_enriched
    QUALIFY row_number() OVER (PARTITION BY news_id, ma ORDER BY enriched_at DESC, prompt_version DESC) = 1
)
SELECT n.news_id, n.ma, n.published_at, n.published_date AS date_key, n.effective_trade_date,
       n.news_type, n.time_known, n.title, n.url, e.summary, e.sentiment, e.prompt_version
FROM silver.news n LEFT JOIN e ON e.news_id = n.news_id AND e.ma = n.ma
"""


def build_gold() -> dict:
    b = bronze.connect()
    try:
        rows = b.execute("SELECT ma, ten, san, active, ghi_chu FROM watchlist ORDER BY ma").fetchall()
    finally:
        b.close()
    wl = pd.DataFrame(rows, columns=["ma", "ten", "san", "active", "ghi_chu"]).astype(
        {"ma": "object", "ten": "object", "san": "object", "active": "int64", "ghi_chu": "object"})
    os.makedirs(os.path.dirname(GOLD_DB), exist_ok=True)
    con = duckdb.connect(GOLD_DB)
    try:
        con.execute(f"ATTACH '{SILVER_DB}' AS silver (READ_ONLY)")
        try:
            con.register("wl", wl)
            con.execute("CREATE OR REPLACE TABLE dim_ticker AS "
                        "SELECT ma, ten, san, active = 1 AS active, ghi_chu FROM wl")
            con.execute(DIM_DATE_SQL)
            con.execute(FACT_PRICE_SQL)
            con.execute(FACT_NEWS_SQL)
        except duckdb.CatalogException as e:
            raise RuntimeError(f"Chưa có dữ liệu silver, hãy chạy /build-silver trước ({e})")
        q = lambda s: con.execute(s).fetchone()[0]
        return {t: q(f"SELECT count(*) FROM {t}")
                for t in ["dim_ticker", "dim_date", "fact_price_daily", "fact_news"]}
    finally:
        con.close()
