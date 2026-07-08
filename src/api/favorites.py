"""B站收藏夹 API 模块。"""

import logging

from src.api.client import BilibiliClient

logger = logging.getLogger(__name__)


def get_favorite_folders(client: BilibiliClient, uid: int) -> list[dict]:
    """获取用户创建的所有收藏夹。

    Args:
        client: BilibiliClient 实例
        uid: 用户数字 UID

    Returns:
        收藏夹列表 [{id, fid, title, media_count, ...}]
    """
    data = client.get(
        "/x/v3/fav/folder/created/list-all",
        params={"up_mid": uid},
    )
    folders = data.get("list", [])
    logger.info(f"获取到 {len(folders)} 个收藏夹")
    for f in folders:
        logger.info(f"  [{f.get('id')}] {f.get('title')} ({f.get('media_count', 0)} 个视频)")
    return folders


def get_folder_videos(
    client: BilibiliClient,
    media_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """获取收藏夹内的视频列表（分页）。

    Args:
        client: BilibiliClient 实例
        media_id: 收藏夹 mlid
        page: 页码（从 1 开始）
        page_size: 每页数量（最大 20）

    Returns:
        {medias: [...], has_more: bool}
    """
    data = client.get(
        "/x/v3/fav/resource/list",
        params={
            "media_id": media_id,
            "pn": page,
            "ps": min(page_size, 20),
        },
    )
    return {
        "medias": data.get("medias", []),
        "has_more": data.get("has_more", False),
    }


def iter_folder_videos(
    client: BilibiliClient, media_id: int, limit: int | None = None
):
    """迭代收藏夹内全部视频（自动翻页）。

    Args:
        client: BilibiliClient 实例
        media_id: 收藏夹 mlid
        limit: 最多获取条数（None = 全部）

    Yields:
        视频信息字典（单条 medias 元素）
    """
    page = 1
    fetched = 0
    while True:
        result = get_folder_videos(client, media_id, page=page)
        medias = result["medias"]
        if not medias:
            break
        for media in medias:
            yield media
            fetched += 1
            if limit is not None and fetched >= limit:
                return
        if not result["has_more"]:
            break
        page += 1
