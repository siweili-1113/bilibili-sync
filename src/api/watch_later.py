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
        {list: [...], has_more: bool, total: int}
    """
    ps = min(page_size, 50)
    data = client.get(
        "/x/v2/history/toview",
        params={
            "pn": page,
            "ps": ps,
        },
    )
    video_list = data.get("list", [])
    page_info = data.get("page", {})

    # toview 接口可能返回 page.total，也可能不返回
    total = page_info.get("total", 0)
    if total > 0:
        has_more = page * ps < total
    else:
        # 无 total 字段时，用返回数量判断是否还有下一页
        has_more = len(video_list) >= ps

    return {
        "list": video_list,
        "has_more": has_more,
        "total": total,
    }


def iter_watch_later(
    client: BilibiliClient,
    limit: int | None = None,
):
    """迭代稍后再看全部视频（自动翻页）。

    Args:
        client: BilibiliClient 实例
        limit: 最多获取条数（None = 全部）

    Yields:
        视频信息字典（单条 list 元素）
    """
    page = 1
    fetched = 0

    while True:
        result = get_watch_later_videos(client, page=page)
        videos = result["list"]
        if not videos:
            break

        for video in videos:
            yield video
            fetched += 1
            if limit is not None and fetched >= limit:
                logger.info(f"稍后再看达到限制 {limit} 条，停止")
                return

        if not result["has_more"]:
            break
        page += 1

    logger.info(f"稍后再看共获取 {fetched} 个视频")
