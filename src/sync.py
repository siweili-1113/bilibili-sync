"""阶段0：元数据同步编排器。

同步收藏夹和稍后再看的全部视频元数据到本地 SQLite。
"""

import logging
import time

from src.api.client import BilibiliClient
from src.api.favorites import get_favorite_folders, iter_folder_videos
from src.api.watch_later import iter_watch_later
from src.config import AppConfig
from src.database import get_connection, get_pending_count, upsert_video

logger = logging.getLogger(__name__)


def sync_all(
    client: BilibiliClient,
    config: AppConfig,
    db_path: str,
    folder_ids: list[int] | None = None,
    limit: int | None = None,
    source: str = "all",
) -> dict:
    """执行全量元数据同步（收藏夹 + 稍后再看）。

    Args:
        client: BilibiliClient 实例
        config: AppConfig 实例
        db_path: 数据库路径
        folder_ids: 指定同步的收藏夹 ID 列表，None 表示同步全部
        limit: 最多同步条数（None = 全部），用于测试
        source: 同步来源 — "all" / "favorites" / "watch_later"

    Returns:
        {total_new, total_updated, favorites: {folder_name: {new, updated}}, watch_later: {new, updated}}
    """
    uid = config.bilibili.uid
    stats = {"total_new": 0, "total_updated": 0, "favorites": {}, "watch_later": {}}

    def _total() -> int:
        return stats["total_new"] + stats["total_updated"]

    def _at_limit() -> bool:
        return limit is not None and _total() >= limit

    # 1. 同步收藏夹
    if source in ("all", "favorites"):
        logger.info("=" * 50)
        logger.info("开始同步收藏夹...")
        folders = get_favorite_folders(client, uid)

        if folder_ids:
            folders = [f for f in folders if f.get("id") in folder_ids]
            if not folders:
                logger.warning(f"未找到指定的收藏夹 ID: {folder_ids}")

        for folder in folders:
            if _at_limit():
                logger.info(f"已达到 limit {limit}，停止同步")
                break

            media_id = folder.get("id", 0)
            folder_name = folder.get("title", f"收藏夹_{media_id}")
            logger.info(f"\n--- 收藏夹: {folder_name} (mlid={media_id}) ---")

            new = 0
            updated = 0
            remaining = limit - _total() if limit is not None else None
            for video in iter_folder_videos(client, media_id, limit=remaining):
                result = _upsert_favorite_video(db_path, video, media_id, folder_name)
                if result == "new":
                    new += 1
                else:
                    updated += 1

            stats["favorites"][folder_name] = {"new": new, "updated": updated}
            stats["total_new"] += new
            stats["total_updated"] += updated
            logger.info(f"  新增: {new}, 更新: {updated}")

    # 2. 同步稍后再看
    if source in ("all", "watch_later") and not _at_limit():
        logger.info("\n" + "=" * 50)
        logger.info("开始同步稍后再看...")
        wl_new = 0
        wl_updated = 0
        remaining = limit - _total() if limit is not None else None
        for video in iter_watch_later(client, limit=remaining):
            result = _upsert_watch_later_video(db_path, video)
            if result == "new":
                wl_new += 1
            else:
                wl_updated += 1

        stats["watch_later"] = {"new": wl_new, "updated": wl_updated}
        stats["total_new"] += wl_new
        stats["total_updated"] += wl_updated
        logger.info(f"  新增: {wl_new}, 更新: {wl_updated}")

    logger.info("\n" + "=" * 50)
    logger.info(f"同步完成: 共新增 {stats['total_new']} 个视频, 更新 {stats['total_updated']} 个")

    # 检查是否有待处理视频
    pending = get_pending_count(db_path, "pending")
    if pending > 0:
        logger.info(f"当前有 {pending} 个视频处于 'pending' 状态，可运行 'process' 命令开始字幕下载")
    elif pending == 0 and stats["total_new"] == 0:
        logger.info("没有新的视频需要处理")

    return stats


def _upsert_favorite_video(
    db_path: str,
    video: dict,
    media_id: int,
    folder_name: str,
) -> str:
    """将收藏夹视频写入数据库。

    Args:
        db_path: 数据库路径
        video: 收藏夹 API 返回的单条视频数据
        media_id: 收藏夹 mlid
        folder_name: 收藏夹名称

    Returns:
        "new" 或 "updated"
    """
    pub_time = video.get("pubtime", 0)
    # B站 pubtime 可能是毫秒时间戳
    if pub_time and pub_time > 10_000_000_000:
        pub_time = pub_time // 1000

    record = {
        "aid": video.get("id") or video.get("aid", 0),
        "bvid": video.get("bvid", ""),
        "title": video.get("title", ""),
        "uploader": video.get("upper", {}).get("name", ""),
        "duration": video.get("duration", 0),
        "pub_time": pub_time,
        "source": f"favorite:{media_id}",
        "folder_name": folder_name,
    }
    is_new = upsert_video(db_path, record)
    return "new" if is_new else "updated"


def _upsert_watch_later_video(
    db_path: str,
    video: dict,
) -> str:
    """将稍后再看视频写入数据库。

    Args:
        db_path: 数据库路径
        video: 稍后再看 API 返回的单条视频数据

    Returns:
        "new" 或 "updated"
    """
    pub_time = video.get("pubdate", 0)
    if pub_time and pub_time > 10_000_000_000:
        pub_time = pub_time // 1000

    record = {
        "aid": video.get("id") or video.get("aid", 0),
        "bvid": video.get("bvid", ""),
        "title": video.get("title", ""),
        "uploader": video.get("owner", {}).get("name", ""),
        "duration": video.get("duration", 0),
        "pub_time": pub_time,
        "source": "watch_later",
        "folder_name": "稍后再看",
    }
    is_new = upsert_video(db_path, record)
    return "new" if is_new else "updated"
