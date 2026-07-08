"""阶段1：字幕下载 + 文本提取处理器。

对每个视频依次：获取视频信息 → 查询字幕 → 选择语言 → 下载字幕 → 拼接文本。
"""

import logging

from src.api.client import BilibiliClient, APIError
from src.api.subtitles import get_subtitle_text
from src.api.video_info import get_video_info
from src.database import (
    get_video,
    get_videos_by_status,
    increment_retry,
    update_video_status,
)

logger = logging.getLogger(__name__)


def process_pending_videos(
    client: BilibiliClient,
    db_path: str,
    max_retries: int = 3,
) -> dict:
    """对 pending 状态的视频批量下载字幕。

    先获取视频信息（cid），再查询并下载字幕。

    Args:
        client: BilibiliClient 实例
        db_path: 数据库路径
        max_retries: 最大重试次数

    Returns:
        {subtitle_downloaded: int, no_subtitle: int, errors: int}
    """
    videos = get_videos_by_status(db_path, "pending")
    total = len(videos)
    stats = {"subtitle_downloaded": 0, "no_subtitle": 0, "errors": 0}

    if total == 0:
        logger.info("没有待处理的视频")
        return stats

    logger.info(f"开始处理 {total} 个视频的字幕...")

    for i, video in enumerate(videos):
        bvid = video["bvid"]
        title = video["title"] or bvid
        logger.info(f"[{i + 1}/{total}] {title} ({bvid})")

        try:
            result = process_video(client, db_path, bvid, max_retries)
            if result == "subtitle_downloaded":
                stats["subtitle_downloaded"] += 1
            elif result == "no_subtitle":
                stats["no_subtitle"] += 1
            elif result == "error":
                stats["errors"] += 1
        except KeyboardInterrupt:
            logger.info("\n用户中断，进度已保存。下次运行将继续处理")
            raise

    logger.info(
        f"字幕处理完成: 有字幕 {stats['subtitle_downloaded']}, "
        f"无字幕 {stats['no_subtitle']}, 错误 {stats['errors']}"
    )
    return stats


def process_video(
    client: BilibiliClient,
    db_path: str,
    bvid: str,
    max_retries: int = 3,
) -> str:
    """处理单个视频的字幕下载。

    Args:
        client: BilibiliClient 实例
        db_path: 数据库路径
        bvid: 视频 BV 号
        max_retries: 最大重试次数

    Returns:
        "subtitle_downloaded" / "no_subtitle" / "error"
    """
    try:
        # 1. 获取视频信息
        info = get_video_info(client, bvid)
        pages = info.get("pages", [])

        if not pages:
            pages = [{"cid": info.get("cid", 0), "part": "", "duration": info.get("duration", 0)}]

        # 2. 尝试每个分P下载字幕
        all_texts = []
        selected_lan = ""
        selected_lan_doc = ""
        selected_url = ""

        for page in pages:
            cid = page.get("cid", 0)
            if not cid:
                continue

            text, meta = get_subtitle_text(client, bvid, cid)
            if text:
                all_texts.append(text)
                if not selected_lan:
                    selected_lan = meta.get("lan", "") if meta else ""
                    selected_lan_doc = meta.get("lan_doc", "") if meta else ""
                    selected_url = meta.get("subtitle_url", "") if meta else ""

        if all_texts:
            # 有字幕：拼接所有分P文本
            raw_text = "\n\n".join(all_texts)
            update_video_status(
                db_path,
                bvid,
                "subtitle_downloaded",
                raw_subtitle_text=raw_text,
                cid=pages[0].get("cid", 0),
                subtitle_lan=selected_lan,
                subtitle_lan_doc=selected_lan_doc,
                subtitle_url=selected_url,
            )
            logger.info(f"  ✓ 字幕已下载 ({selected_lan_doc or selected_lan}, {len(raw_text)} 字)")
            return "subtitle_downloaded"
        else:
            # 无字幕
            update_video_status(db_path, bvid, "no_subtitle")
            logger.info(f"  - 无可用字幕")
            return "no_subtitle"

    except APIError as e:
        can_retry = increment_retry(db_path, bvid, f"APIError: {e}", max_retries)
        if can_retry:
            logger.warning(f"  API错误 (可重试): {e}")
        else:
            logger.error(f"  API错误已达最大重试次数: {e}")
        return "error"

    except Exception as e:
        can_retry = increment_retry(db_path, bvid, f"{type(e).__name__}: {e}", max_retries)
        if can_retry:
            logger.warning(f"  处理错误 (可重试): {e}")
        else:
            logger.error(f"  处理错误已达最大重试次数: {e}")
        return "error"
