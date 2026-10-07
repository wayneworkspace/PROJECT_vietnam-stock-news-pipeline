"""API nhỏ cho n8n gọi. Thêm endpoint mới (cào tin, lấy giá...) ở đây."""
import importlib
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ingestion import fetch_news as ingest_news
from ingestion import fetch_prices as ingest_prices
from source import cafef, cafef_price
from storage import bronze
from storage import watchlist as wl
from serving import digest
from transform import enrich, gold, silver

app = FastAPI(title="Stock pyworker")

LIBS = ["duckdb", "pandas", "pyarrow",
        "anthropic", "requests", "dotenv"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/check")
def check():
    result = {}
    for name in LIBS:
        try:
            m = importlib.import_module(name)
            result[name] = getattr(m, "__version__", "ok")
        except Exception as e:
            result[name] = f"LỖI: {e}"
    return result


@app.post("/init-db")
def init_db():
    """Tạo bảng bronze nếu chưa có. Gọi lại an toàn. Silver và gold do /build-silver, /build-gold tạo."""
    return {"bronze": bronze.init_bronze()}


class Ticker(BaseModel):
    ma: str
    ten: Optional[str] = None
    san: Optional[str] = None
    active: bool = True
    ghi_chu: Optional[str] = None


@app.post("/watchlist")
def watchlist(t: Ticker):
    """Thêm hoặc cập nhật một mã trong bảng watchlist (tối đa 10 mã đang theo dõi)."""
    try:
        rows = wl.upsert_watchlist(**t.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"watchlist": rows}


@app.post("/debug/cafef-html")
def debug_cafef_html(ma: str = "FPT"):
    """Lưu HTML trang tin CafeF của 1 mã vào data/debug để viết bộ đọc tin."""
    try:
        return cafef.save_debug_html(ma)
    except Exception as e:
        raise HTTPException(502, f"Không lấy được trang CafeF: {e}")


@app.post("/fetch-news")
def fetch_news():
    """Lấy tin CafeF cho các mã active trong watchlist, ghi raw_data + news + run_log."""
    return ingest_news.run_fetch_news()


@app.post("/enrich-news")
def enrich_news(limit: int = enrich.MAX_PER_RUN):
    """Đọc tin từ bronze, tóm tắt + chấm cảm xúc (-2..+2) bằng Claude Haiku 4.5, ghi kết quả vào bronze."""
    return enrich.run_enrich(limit=limit)


@app.post("/debug/cafef-price")
def debug_cafef_price(ma: str = "FPT", exchange: str = "HOSE"):
    """Lưu JSON giá thô của CafeF vào data/debug để viết bộ đọc giá."""
    try:
        return cafef_price.save_debug_json(ma, exchange)
    except Exception as e:
        raise HTTPException(502, f"Không lấy được giá CafeF: {e}")


@app.post("/fetch-prices")
def fetch_prices(days: int = 30):
    """Lấy giá lịch sử (mặc định 30 ngày gần nhất) cho các mã active, ghi prices + raw_data + run_log."""
    return ingest_prices.run_fetch_prices(days=days)


@app.post("/build-silver")
def build_silver():
    """Dựng lại silver (prices_daily, news) từ bronze. Chạy lại an toàn."""
    return silver.build_silver()


@app.post("/build-gold")
def build_gold():
    """Dựng lại gold (dim_ticker, dim_date, fact_price_daily, fact_news) từ silver."""
    try:
        return gold.build_gold()
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.post("/digest")
def make_digest():
    """Tạo nội dung bản tin sáng (văn bản, dưới 2000 ký tự) từ gold để n8n gửi Discord."""
    try:
        return {"text": digest.build_digest()}
    except RuntimeError as e:
        raise HTTPException(409, str(e))
