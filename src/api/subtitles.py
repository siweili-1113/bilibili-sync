"""B站字幕 API 模块。"""

import logging

from src.api.client import BilibiliClient

logger = logging.getLogger(__name__)

# 字幕语言优先级
LANG_PRIORITY = ["zh-CN", "zh-Hant", "en"]


def get_subtitle_list(client: BilibiliClient, bvid: str, cid: int) -> list[dict]:
    """获取视频的字幕列表。

    Args:
        client: BilibiliClient 实例
        bvid: 视频 BV 号
        cid: 视频分P的 cid

    Returns:
        字幕列表 [{id, lan, lan_doc, subtitle_url, ...}]
        无字幕时返回空列表
    """
    data = client.get(
        "/x/player/v2",
        params={"bvid": bvid, "cid": cid},
    )
    subtitle_info = data.get("subtitle", {}).get("subtitles", [])
    return subtitle_info


def select_best_subtitle(subtitles: list[dict]) -> dict | None:
    """按语言优先级选择最佳字幕。

    Args:
        subtitles: 字幕列表

    Returns:
        选中的字幕 dict 或 None
    """
    if not subtitles:
        return None

    # 按优先级查找
    for lang in LANG_PRIORITY:
        for sub in subtitles:
            if sub.get("lan", "") == lang:
                logger.debug(f"选中字幕: {sub.get('lan_doc', lang)}")
                return sub

    # 返回第一个可用的
    logger.debug(f"使用默认字幕: {subtitles[0].get('lan_doc', subtitles[0].get('lan', ''))}")
    return subtitles[0]


def download_subtitle(client: BilibiliClient, subtitle_url: str) -> list[dict]:
    """从 CDN 下载字幕 JSON。

    Args:
        client: BilibiliClient 实例
        subtitle_url: 字幕 CDN URL（可能是 // 开头）

    Returns:
        字幕内容列表 [{from, to, content, ...}]
    """
    data = client.download_raw(subtitle_url)
    return data.get("body", [])


def extract_text_from_subtitle(subtitle_body: list[dict]) -> str:
    """从字幕 JSON 提取纯文本（去掉时间戳）。

    Args:
        subtitle_body: 字幕 JSON body 数组

    Returns:
        拼接后的纯文本
    """
    lines = []
    for item in subtitle_body:
        content = item.get("content", "").strip()
        if content:
            lines.append(content)
    return " ".join(lines)


def get_subtitle_text(
    client: BilibiliClient, bvid: str, cid: int
) -> tuple[str | None, dict | None]:
    """获取视频字幕的纯文本（便捷组合方法）。

    组合字幕查询 → 语言选择 → 下载 → 文本提取。

    Args:
        client: BilibiliClient 实例
        bvid: 视频 BV 号
        cid: 视频分P的 cid

    Returns:
        (纯文本, 字幕元信息) 或 (None, None) 表示无字幕
    """
    subtitles = get_subtitle_list(client, bvid, cid)
    if not subtitles:
        return None, None

    best = select_best_subtitle(subtitles)
    if best is None:
        return None, None

    subtitle_url = best.get("subtitle_url", "")
    if not subtitle_url:
        return None, None

    body = download_subtitle(client, subtitle_url)
    text = extract_text_from_subtitle(body)

    meta = {
        "lan": best.get("lan", ""),
        "lan_doc": best.get("lan_doc", ""),
        "subtitle_url": subtitle_url,
    }

    return text, meta
