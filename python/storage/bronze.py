"""Bronze: SQLite (OLTP) giữ dữ liệu thô, kết quả AI và nhật ký vận hành:
raw_data, news_enriched, run_log, cost_log, watchlist.
Silver và gold luôn dựng lại được từ bronze.
Không bật WAL vì file nằm trên thư mục Windows gắn vào Docker (WAL có thể lỗi trên kiểu ổ này)."""
import os
import sqlite3
from datetime import datetime

from config import BRONZE_DB, VN_TZ

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS raw_data (
        raw_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id          TEXT NOT NULL,
        source          TEXT NOT NULL,        -- cafef...
        data_type       TEXT NOT NULL,        -- news | price
        ma              TEXT NOT NULL,
        request_params  TEXT,                 -- JSON
        payload         TEXT NOT NULL,        -- JSON nguyên gốc
        payload_hash    TEXT NOT NULL,
        url             TEXT,
        published_at    TEXT,
        fetched_at      TEXT NOT NULL,
        fetch_date      TEXT NOT NULL,
        apify_run_id    TEXT,
        adapter_version TEXT,
        UNIQUE (source, data_type, ma, payload_hash)
    )""",
    """CREATE TABLE IF NOT EXISTS news_enriched (
        news_id        TEXT NOT NULL,         -- 16 ký tự đầu của payload_hash (băm url)
        ma             TEXT NOT NULL,
        summary        TEXT,
        sentiment      INTEGER CHECK (sentiment BETWEEN -2 AND 2),
        model          TEXT,
        prompt_version TEXT NOT NULL,
        enriched_at    TEXT NOT NULL,
        PRIMARY KEY (news_id, ma, prompt_version)
    )""",
    """CREATE TABLE IF NOT EXISTS watchlist (
        ma       TEXT PRIMARY KEY,
        ten      TEXT,
        san      TEXT,                        -- HOSE | HNX | UPCOM
        active   INTEGER NOT NULL DEFAULT 1,
        ghi_chu  TEXT,
        added_at TEXT NOT NULL DEFAULT (datetime('now', '+7 hours'))
    )""",
    """CREATE TABLE IF NOT EXISTS run_log (
        run_id      TEXT PRIMARY KEY,
        workflow    TEXT,
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        status      TEXT,                     -- running | ok | error
        rows_in     INTEGER,
        rows_out    INTEGER,
        error       TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS cost_log (
        run_id        TEXT PRIMARY KEY,
        model         TEXT NOT NULL,
        input_tokens  INTEGER,
        output_tokens INTEGER,
        est_usd       REAL,                   -- ước tính, cần đối chiếu bảng giá
        created_at    TEXT NOT NULL
    )""",
]


def now_vn() -> str:
    return datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def connect():
    os.makedirs(os.path.dirname(BRONZE_DB), exist_ok=True)
    return sqlite3.connect(BRONZE_DB, timeout=30)


def init_bronze() -> list:
    con = connect()
    try:
        for stmt in SCHEMA:
            con.execute(stmt)
        con.commit()
        return [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY 1").fetchall()]
    finally:
        con.close()


def log_start(con, run_id: str, workflow: str):
    con.execute("INSERT INTO run_log (run_id, workflow, started_at, status) VALUES (?, ?, ?, 'running')",
                [run_id, workflow, now_vn()])
    con.commit()


def log_end(con, run_id: str, status: str, rows_in: int, rows_out: int, error=None):
    con.execute("UPDATE run_log SET finished_at=?, status=?, rows_in=?, rows_out=?, error=? "
                "WHERE run_id=?", [now_vn(), status, rows_in, rows_out, error, run_id])
    con.commit()


def insert_raw(con, run_id, source, data_type, ma, payload, payload_hash, fetched_at, fetch_date,
               request_params=None, url=None, published_at=None, adapter_version=None,
               apify_run_id=None) -> bool:
    """Chỉ thêm. Trả True nếu là dòng mới, False nếu đã có (cùng source, data_type, ma, payload_hash)."""
    cur = con.execute(
        """INSERT OR IGNORE INTO raw_data (run_id, source, data_type, ma, request_params, payload,
               payload_hash, url, published_at, fetched_at, fetch_date, apify_run_id, adapter_version)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [run_id, source, data_type, ma, request_params, payload, payload_hash, url, published_at,
         fetched_at, fetch_date, apify_run_id, adapter_version])
    return cur.rowcount == 1
