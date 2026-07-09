"""阶段1：文本获取处理器。

流程：yt-dlp 下载音频 → faster-whisper 本地转录 → 存库。
B站字幕系统不稳定，直接走 ASR 路径。
"""

import logging

from src.asr import transcribe_video
from src.config import AppConfig
from src.database import (
    get_videos_by_status,
    increment_retry,
    update_video_status,
)

logger = logging.getLogger(__name__)


def process_pending_videos(
    config: AppConfig,
    db_path: str,
    max_retries: int = 3,
) -> dict:
    """对 pending 状态的视频批量 ASR 转录。

    Args:
        config: AppConfig 实例
        db_path: 数据库路径
        max_retries: 最大重试次数

    Returns:
        {subtitle_downloaded: int, errors: int}
    """
    videos = get_videos_by_status(db_path, "pending")
    total = len(videos)
    stats = {"subtitle_downloaded": 0, "errors": 0}

    if total == 0:
        logger.info("没有待处理的视频")
        return stats

    logger.info(f"开始 ASR 处理 {total} 个视频...")
    sessdata = config.bilibili.sessdata
    user_agent = config.bilibili.user_agent

    for i, video in enumerate(videos):
        bvid = video["bvid"]
        title = video["title"] or bvid
        duration = video["duration"] or 0
        logger.info(f"[{i + 1}/{total}] {title} ({bvid}, {duration}s)")

        try:
            raw_text = transcribe_video(bvid, sessdata, user_agent)
            if raw_text:
                update_video_status(
                    db_path,
                    bvid,
                    "subtitle_downloaded",
                    raw_subtitle_text=raw_text,
                    subtitle_lan="asr-zh",
                    subtitle_lan_doc="Whisper ASR",
                )
                stats["subtitle_downloaded"] += 1
                logger.info(f"  ✓ ASR 转录完成 ({len(raw_text)} 字)")
            else:
                update_video_status(db_path, bvid, "no_subtitle")
                logger.info(f"  - 转录结果为空")
        except KeyboardInterrupt:
            logger.info("\n用户中断，进度已保存。下次运行将继续处理")
            raise
        except Exception as e:
            can_retry = increment_retry(db_path, bvid, f"{type(e).__name__}: {e}", max_retries)
            if can_retry:
                logger.warning(f"  ASR 错误 (可重试): {e}")
            else:
                logger.error(f"  ASR 错误已达最大重试: {e}")
            stats["errors"] += 1

    logger.info(
        f"ASR 处理完成: 成功 {stats['subtitle_downloaded']}, "
        f"错误 {stats['errors']}"
    )
    return stats
