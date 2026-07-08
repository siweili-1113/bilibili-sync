"""B站视频信息 API 模块。"""

import logging

from src.api.client import BilibiliClient

logger = logging.getLogger(__name__)


def get_video_info(client: BilibiliClient, bvid: str) -> dict:
    """获取视频基本信息，包括 cid 和分P信息。

    Args:
        client: BilibiliClient 实例
        bvid: 视频 BV 号

    Returns:
        {
            bvid: str,
            title: str,
            owner: {mid, name, face},
            cid: int,        # 主 cid（单P视频用这个）
            pages: [{cid, part, duration}],  # 多P视频所有分页
            duration: int,   # 总时长（秒）
            pubdate: int,    # 发布时间戳
            ...
        }
    """
    data = client.get("/x/web-interface/view", params={"bvid": bvid})

    pages = data.get("pages", [])
    owner = data.get("owner", {})
    stat = data.get("stat", {})

    logger.info(f"视频信息: [{bvid}] {data.get('title', '')} ({len(pages)}P)")

    return {
        "bvid": data.get("bvid", bvid),
        "title": data.get("title", ""),
        "owner": {
            "mid": owner.get("mid", 0),
            "name": owner.get("name", ""),
        },
        "cid": data.get("cid", 0),
        "pages": [
            {
                "cid": p.get("cid", 0),
                "part": p.get("part", ""),
                "duration": p.get("duration", 0),
            }
            for p in pages
        ],
        "duration": data.get("duration", 0),
        "pubdate": data.get("pubdate", 0),
        "desc": data.get("desc", ""),
    }
