"""阶段5：Markdown 文件生成。

将处理完成的视频导出为 Obsidian 兼容的 Markdown 文件。
"""

import logging
import os
from pathlib import Path
from typing import Any

from src.database import get_videos_by_status, update_video_status
from src.utils import escape_yaml_value, format_duration, format_pub_time, sanitize_filename

logger = logging.getLogger(__name__)


def export_all(
    db_path: str,
    output_base_dir: str,
) -> dict:
    """导出所有 llm_processed 状态的视频为 Markdown 文件。

    Args:
        db_path: 数据库路径
        output_base_dir: 输出根目录

    Returns:
        {exported: int, errors: int}
    """
    videos = get_videos_by_status(db_path, "llm_processed")
    total = len(videos)
    stats = {"exported": 0, "errors": 0}

    if total == 0:
        logger.info("没有待导出的视频（状态需为 llm_processed）。")
        logger.info("提示：先运行 'process' 命令下载字幕并完成 LLM 处理。")
        return stats

    logger.info(f"开始导出 {total} 个视频...")

    for i, video in enumerate(videos):
        bvid = video["bvid"]
        title = video["title"] or bvid
        logger.info(f"[{i + 1}/{total}] 导出: {title}")

        try:
            file_path = export_video(dict(video), output_base_dir)
            update_video_status(db_path, bvid, "markdown_generated")
            stats["exported"] += 1
            logger.info(f"  → {file_path}")
        except Exception as e:
            logger.error(f"  导出失败: {e}")
            stats["errors"] += 1

    logger.info(f"导出完成: 成功 {stats['exported']}, 失败 {stats['errors']}")
    return stats


def export_video(video: dict[str, Any], output_base_dir: str) -> str:
    """导出单个视频为 Markdown 文件。

    Args:
        video: 视频数据字典（sqlite3.Row 转 dict）
        output_base_dir: 输出根目录

    Returns:
        生成的文件路径
    """
    bvid = video.get("bvid", "")
    title = video.get("title", bvid)
    uploader = video.get("uploader", "")
    duration = video.get("duration", 0)
    pub_time = video.get("pub_time", 0)
    source = video.get("source", "")
    folder_name = video.get("folder_name", "")
    cleaned_text = video.get("cleaned_text", "") or ""
    summary = video.get("summary", "") or ""

    # 确定子目录
    if source and source.startswith("favorite:"):
        subdir = f"收藏夹/{sanitize_filename(folder_name, max_length=100)}"
    else:
        subdir = "稍后再看"

    # 输出目录
    output_dir = Path(output_base_dir) / subdir
    output_dir.mkdir(parents=True, exist_ok=True)

    # 文件名（处理重名）
    safe_title = sanitize_filename(title)
    file_path = output_dir / f"{safe_title}.md"

    # 如果文件已存在，追加 bvid 后缀
    if file_path.exists():
        file_path = output_dir / f"{safe_title}_BV{bvid}.md"

    # 构建内容
    url = f"https://www.bilibili.com/video/{bvid}"
    content = _build_markdown(
        bvid=bvid,
        title=title,
        uploader=uploader,
        duration=format_duration(duration),
        pub_time=format_pub_time(pub_time),
        source=f"{subdir}" if folder_name else "稍后再看",
        url=url,
        summary=summary,
        transcript=cleaned_text,
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return str(file_path)


def _build_markdown(
    bvid: str = "",
    title: str = "",
    uploader: str = "",
    duration: str = "00:00",
    pub_time: str = "",
    source: str = "",
    url: str = "",
    summary: str = "",
    transcript: str = "",
) -> str:
    """构建 Markdown 文件内容。

    Args:
        bvid: 视频 BV 号
        title: 视频标题
        uploader: UP主名称
        duration: 时长字符串
        pub_time: 发布时间字符串
        source: 来源描述
        url: B站链接
        summary: 内容摘要
        transcript: 完整文字记录

    Returns:
        Markdown 字符串
    """
    # YAML frontmatter
    frontmatter_lines = [
        "---",
        f"bvid: {bvid}",
        f"title: {escape_yaml_value(title)}",
        f"uploader: {escape_yaml_value(uploader)}",
        f"duration: \"{duration}\"",
        f"pub_time: \"{pub_time}\"",
        f"source: {escape_yaml_value(source)}",
        f"url: {url}",
        "tags:",
        "  - bilibili",
        "  - subtitle",
        "---",
    ]

    # 正文
    body_lines = [
        "",
        f"# {title}",
        "",
        "## 内容概括",
        "",
        summary if summary else "（暂无摘要）",
        "",
        "## 完整文字记录",
        "",
        transcript if transcript else "（暂无文字记录）",
        "",
        f"> 来源: [{url}]({url})  ",
        f"> UP主: {uploader}  ",
        f"> 视频时长: {duration}  ",
        f"> 发布时间: {pub_time}  ",
        f"> 归档时间: {_now_str()}  ",
        "",
    ]

    return "\n".join(frontmatter_lines) + "\n".join(body_lines)


def _now_str() -> str:
    """获取当前时间字符串。"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
