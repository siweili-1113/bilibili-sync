"""B站稍后再看 API 模块。"""

import logging

from src.api.client import BilibiliClient

logger = logging.getLogger(__name__)


def get_watch_later_videos(
    client: BilibiliClient,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """获取稍后再看列表（分页）。

    Args:
        client: BilibiliClient 实例
        page: 页码（从 1 开始）
        page_size: 每页数量（最大 50）

    Returns:
        {list: [...], has_more: bool}
    """
    data = client.get(
        "/x/v2/history/toview",
        params={
            "pn": page,
            "ps": min(page_size, 50),
        },
    )
    return {
        "list": data.get("list", []),
        "has_more": data.get("page", {}).get("pn", page)
        < data.get("page", {}).get("total", 0) // min(page_size, 50) + 1,
    }


def iter_watch_later(
    client: BilibiliClient,
):
    """迭代稍后再看全部视频（自动翻页）。

    Args:
        client: BilibiliClient 实例

    Yields:
        视频信息字典（单条 list 元素）
    """
    page = 1
    total_count = None
    fetched = 0

    while True:
        result = get_watch_later_videos(client, page=page)
        videos = result["list"]
        if not videos:
            break
        for video in videos:
            yield video
            fetched += 1

        # 从第一页获取总数
        if page == 1:
            # 稍后再看不直接返回 total，通过 has_more 判断
            pass

        if not result["has_more"]:
            break
        page += 1

    logger.info(f"稍后再看共获取 {fetched} 个视频")
