"""Ingestion: lấy giá lịch sử cho các mã active, chỉ ghi vào bronze (raw_data + run_log + JSON theo ngày).
Nếu nguồn điều chỉnh giá một ngày thì bản mới được thêm vào raw_data (chỉ thêm, không sửa);
tầng silver lấy bản mới nhất cho mỗi (mã, ngày)."""
import hashlib
import json
import os
import time
import uuid
from datetime import datetime

from config import RAW_DIR, VN_TZ
from source import cafef_price
from storage import bronze, watchlist

ADAPTER_VERSION = "cafef-price-v1"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_fetch_prices(days: int = 30, delay_s: float = 2.0, provider=None) -> dict:
    started = datetime.now(VN_TZ)
    now = started.strftime("%Y-%m-%d %H:%M:%S")
    run_id = f"fetch-prices-{started:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    os.makedirs(RAW_DIR, exist_ok=True)
    bronze.init_bronze()
    con = bronze.connect()
    summary = {"run_id": run_id, "tickers": {}, "errors": {}}
    try:
        bronze.log_start(con, run_id, "fetch-prices")
        tickers = watchlist.active_tickers(con)
        total_in = total_new = 0
        for i, (ma, san) in enumerate(tickers):
            if i:
                time.sleep(delay_s)
            try:
                records = cafef_price.fetch_all_records(ma, san, days, provider=provider,
                                                        delay_s=min(delay_s, 1.0))
            except Exception as e:
                summary["errors"][ma] = str(e)
                continue
            rows = cafef_price.parse_prices(records)
            new = 0
            for p in rows:
                payload = json.dumps(p["raw"], ensure_ascii=False, sort_keys=True)
                if bronze.insert_raw(
                        con, run_id, "cafef", "price", ma, payload,
                        _sha(f"{ma}|{p['trade_date']}|{payload}"), now, now[:10],
                        request_params=json.dumps({"days": days, "exchange": san}),
                        adapter_version=ADAPTER_VERSION):
                    new += 1
            con.commit()
            summary["tickers"][ma] = {"fetched": len(rows), "new": new}
            total_in += len(rows)
            total_new += new
            fn = os.path.join(RAW_DIR, f"cafef_price_{ma}_{now[:10]}.json")
            with open(fn, "w", encoding="utf-8") as f:
                json.dump({"ma": ma, "fetched_at": now, "records": records}, f, ensure_ascii=False, indent=2)
            summary["tickers"][ma]["file"] = os.path.basename(fn)
        status = "error" if summary["errors"] and not summary["tickers"] else "ok"
        bronze.log_end(con, run_id, status, total_in, total_new,
                       json.dumps(summary["errors"], ensure_ascii=False) if summary["errors"] else None)
        summary["status"] = status
        return summary
    finally:
        con.close()
