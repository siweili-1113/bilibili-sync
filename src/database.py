"""SQLite 数据库模块：建表、CRUD、状态管理。"""

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bvid TEXT NOT NULL UNIQUE,
    title TEXT,
    uploader TEXT,
    duration INTEGER,
    pub_time INTEGER,
    source TEXT NOT NULL,
    folder_name TEXT,

    -- 字幕元数据
    cid INTEGER,
    subtitle_url TEXT,
    subtitle_lan TEXT,
    subtitle_lan_doc TEXT,

    -- 内容
    raw_subtitle_text TEXT,
    cleaned_text TEXT,
    summary TEXT,

    -- 状态机
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    -- 时间戳
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_videos_bvid ON videos(bvid);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_source ON videos(source);
"""


def init_db(db_path: str) -> None:
    """初始化数据库：建表、创建索引、迁移旧表。

    Args:
        db_path: SQLite 数据库文件路径
    """
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        # 迁移：添加 aid 列（如果不存在）
        cur = conn.execute("PRAGMA table_info(videos)")
        cols = {r[1] for r in cur.fetchall()}
        if "aid" not in cols:
            conn.execute("ALTER TABLE videos ADD COLUMN aid INTEGER")
    logger.info(f"数据库已初始化: {db_path}")


def get_connection(db_path: str) -> sqlite3.Connection:
    """获取数据库连接。

    Args:
        db_path: SQLite 数据库文件路径

    Returns:
        sqlite3.Connection 实例
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def upsert_video(db_path: str, video: dict[str, Any]) -> bool:
    """插入或更新视频记录（以 bvid 为冲突键）。

    只更新非 NULL 的字段，已有记录不会用 NULL 覆盖原有值。

    Args:
        db_path: 数据库路径
        video: 视频数据字典，至少包含 bvid

    Returns:
        True 表示新插入，False 表示更新已有记录
    """
    fields = {
        "aid": video.get("aid"),
        "bvid": video["bvid"],
        "title": video.get("title"),
        "uploader": video.get("uploader"),
        "duration": video.get("duration"),
        "pub_time": video.get("pub_time"),
        "source": video.get("source"),
        "folder_name": video.get("folder_name"),
    }

    with get_connection(db_path) as conn:
        # 先检查是否存在
        existing = conn.execute(
            "SELECT id FROM videos WHERE bvid = ?", (fields["bvid"],)
        ).fetchone()

        if existing:
            # 更新非 NULL 字段
            set_parts = []
            values: list[Any] = []
            for key, val in fields.items():
                if key != "bvid" and val is not None:
                    set_parts.append(f"{key} = ?")
                    values.append(val)
            if set_parts:
                set_parts.append("updated_at = datetime('now')")
                values.append(fields["bvid"])
                conn.execute(
                    f"UPDATE videos SET {', '.join(set_parts)} WHERE bvid = ?",
                    values,
                )
            return False
        else:
            # 插入新记录
            columns = ", ".join(fields.keys())
            placeholders = ", ".join("?" * len(fields))
            conn.execute(
                f"INSERT INTO videos ({columns}) VALUES ({placeholders})",
                list(fields.values()),
            )
            return True


def get_videos_by_status(
    db_path: str, status: str, limit: int | None = None
) -> list[sqlite3.Row]:
    """获取指定状态的视频列表。

    Args:
        db_path: 数据库路径
        status: 状态值
        limit: 最大返回条数

    Returns:
        sqlite3.Row 列表
    """
    query = "SELECT * FROM videos WHERE status = ? ORDER BY id"
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    with get_connection(db_path) as conn:
        return conn.execute(query, (status,)).fetchall()


def get_pending_count(db_path: str, status: str) -> int:
    """获取指定状态的视频数量。

    Args:
        db_path: 数据库路径
        status: 状态值

    Returns:
        视频数量
    """
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE status = ?", (status,)
        ).fetchone()
        return row[0] if row else 0


def update_video_status(
    db_path: str, bvid: str, status: str, **extra_fields: Any
) -> None:
    """更新视频状态及可选额外字段。

    Args:
        db_path: 数据库路径
        bvid: 视频 BV 号
        status: 新状态
        **extra_fields: 额外要更新的字段
    """
    set_parts = ["status = ?", "updated_at = datetime('now')"]
    values: list[Any] = [status]

    for key, val in extra_fields.items():
        set_parts.append(f"{key} = ?")
        values.append(val)

    values.append(bvid)

    with get_connection(db_path) as conn:
        conn.execute(
            f"UPDATE videos SET {', '.join(set_parts)} WHERE bvid = ?",
            values,
        )


def increment_retry(
    db_path: str, bvid: str, error_message: str, max_retries: int
) -> bool:
    """递增重试计数，超过上限则标记为 error。

    Args:
        db_path: 数据库路径
        bvid: 视频 BV 号
        error_message: 错误信息
        max_retries: 最大重试次数

    Returns:
        True 表示可以继续重试，False 表示已达上限
    """
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT retry_count FROM videos WHERE bvid = ?", (bvid,)
        ).fetchone()

        if row is None:
            return False

        new_count = row["retry_count"] + 1
        if new_count >= max_retries:
            conn.execute(
                """UPDATE videos
                   SET retry_count = ?, error_message = ?, status = 'error',
                       updated_at = datetime('now')
                   WHERE bvid = ?""",
                (new_count, error_message, bvid),
            )
            return False
        else:
            conn.execute(
                """UPDATE videos
                   SET retry_count = ?, error_message = ?,
                       updated_at = datetime('now')
                   WHERE bvid = ?""",
                (new_count, error_message, bvid),
            )
            return True


def reset_error_videos(db_path: str) -> int:
    """将所有 error 状态的视频重置为 pending。

    Args:
        db_path: 数据库路径

    Returns:
        重置的视频数量
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """UPDATE videos
               SET status = 'pending', retry_count = 0, error_message = NULL,
                   updated_at = datetime('now')
               WHERE status = 'error'"""
        )
        return cursor.rowcount


def get_stats(db_path: str) -> dict[str, int]:
    """获取各状态的视频数量统计。

    Args:
        db_path: 数据库路径

    Returns:
        {status: count} 字典
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM videos GROUP BY status"
        ).fetchall()
        return {row["status"]: row["cnt"] for row in rows}


def get_video(db_path: str, bvid: str) -> sqlite3.Row | None:
    """获取单个视频记录。

    Args:
        db_path: 数据库路径
        bvid: 视频 BV 号

    Returns:
        sqlite3.Row 或 None
    """
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM videos WHERE bvid = ?", (bvid,)
        ).fetchone()
