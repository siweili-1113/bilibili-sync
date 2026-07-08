"""CLI 入口：B站收藏夹/稍后再看 转文字归档工具。

命令：
    sync      - 同步元数据（阶段0）
    process   - 下载字幕 + LLM 处理（阶段1+3+4）
    export    - 导出 Markdown（阶段5）
    run       - 一键运行全部阶段
    status    - 查看处理进度
"""

import argparse
import logging
import sys

from src.api.client import BilibiliClient
from src.auth import AuthError, validate_cookie
from src.config import AppConfig, load_config
from src.database import get_stats, init_db, reset_error_videos
from src.exporter import export_all
from src.llm import LLMProcessor
from src.processor import process_pending_videos, process_video
from src.sync import sync_all
from src.utils import setup_logging

logger = logging.getLogger(__name__)


def cmd_sync(args: argparse.Namespace, config: AppConfig) -> None:
    """同步元数据（阶段0）。"""
    init_db(config.database.path)

    client = BilibiliClient(
        config.bilibili,
        rate_limit_min=config.sync.rate_limit_min,
        rate_limit_max=config.sync.rate_limit_max,
        max_retries=config.sync.max_retries,
    )

    folder_ids = args.folders or config.sync.favorite_folder_ids or None
    limit = getattr(args, "limit", None)
    sync_all(client, config, config.database.path, folder_ids=folder_ids, limit=limit)


def cmd_process(args: argparse.Namespace, config: AppConfig) -> None:
    """下载字幕 + LLM 处理（阶段1+3+4）。"""
    init_db(config.database.path)

    client = BilibiliClient(
        config.bilibili,
        rate_limit_min=config.sync.rate_limit_min,
        rate_limit_max=config.sync.rate_limit_max,
        max_retries=config.sync.max_retries,
    )

    max_retries = config.sync.max_retries

    # Phase 1: 下载字幕
    if args.skip_subtitles:
        logger.info("跳过字幕下载阶段")
    else:
        logger.info("=" * 50)
        logger.info("阶段1: 字幕下载")
        process_pending_videos(client, config.database.path, max_retries=max_retries)

    # Phase 3+4: LLM 处理
    if args.skip_llm:
        logger.info("跳过 LLM 处理阶段")
    else:
        logger.info("\n" + "=" * 50)
        logger.info("阶段3+4: LLM 文本整理 + 摘要")
        process_llm(config)


def process_llm(config: AppConfig) -> None:
    """对 subtitle_downloaded 状态的视频进行 LLM 处理。"""
    from src.database import get_videos_by_status, increment_retry, update_video_status

    videos = get_videos_by_status(config.database.path, "subtitle_downloaded")
    total = len(videos)

    if total == 0:
        logger.info("没有待 LLM 处理的视频（状态需为 subtitle_downloaded）")
        return

    logger.info(f"共 {total} 个视频待 LLM 处理")

    try:
        llm = LLMProcessor(config.llm)
    except Exception as e:
        logger.error(f"LLM 初始化失败: {e}")
        return

    for i, video in enumerate(videos):
        bvid = video["bvid"]
        title = video["title"] or bvid
        raw_text = video["raw_subtitle_text"] or ""

        logger.info(f"[{i + 1}/{total}] LLM处理: {title}")

        try:
            cleaned, summary = llm.process(raw_text)
            update_video_status(
                config.database.path,
                bvid,
                "llm_processed",
                cleaned_text=cleaned,
                summary=summary,
            )
            logger.info(f"  ✓ 完成")
        except KeyboardInterrupt:
            logger.info("\n用户中断，进度已保存")
            raise
        except Exception as e:
            max_retries = config.sync.max_retries
            can_retry = increment_retry(
                config.database.path, bvid, str(e), max_retries
            )
            if can_retry:
                logger.warning(f"  LLM处理失败 (可重试): {e}")
            else:
                logger.error(f"  LLM处理失败已达最大重试: {e}")


def cmd_export(args: argparse.Namespace, config: AppConfig) -> None:
    """导出 Markdown（阶段5）。"""
    init_db(config.database.path)
    export_all(config.database.path, config.output.base_dir)


def cmd_run(args: argparse.Namespace, config: AppConfig) -> None:
    """一键运行全部阶段。"""
    logger.info("=" * 60)
    logger.info("B站收藏夹/稍后再看 → 文字归档工具")
    logger.info("=" * 60)
    limit = getattr(args, "limit", None)
    if limit:
        logger.info(f"测试模式：最多处理 {limit} 条")

    # 阶段0: 同步元数据
    logger.info("\n>>> 阶段0: 同步元数据")
    cmd_sync(args, config)

    # 阶段1: 字幕下载 + LLM
    logger.info("\n>>> 阶段1: 字幕下载 + LLM处理")
    cmd_process(args, config)

    # 阶段5: 导出
    logger.info("\n>>> 阶段5: 导出 Markdown")
    cmd_export(args, config)

    _print_summary(config)


def cmd_status(args: argparse.Namespace, config: AppConfig) -> None:
    """查看数据库统计。"""
    init_db(config.database.path)
    _print_summary(config)


def _print_summary(config: AppConfig) -> None:
    """打印数据库统计信息。"""
    stats = get_stats(config.database.path)
    print("\n" + "=" * 40)
    print("数据库统计")
    print("=" * 40)
    status_labels = {
        "pending": "待处理（元数据已同步）",
        "metadata_synced": "元数据已同步",
        "subtitle_downloaded": "字幕已下载（待LLM处理）",
        "llm_processed": "LLM处理完成（待导出）",
        "markdown_generated": "已完成",
        "no_subtitle": "无字幕（跳过）",
        "error": "处理失败",
    }
    for status, label in status_labels.items():
        count = stats.get(status, 0)
        if count > 0:
            print(f"  {label}: {count}")
    total = sum(stats.values())
    print(f"\n  总计: {total} 个视频")
    print("=" * 40)


def main() -> None:
    """CLI 入口函数。"""
    parser = argparse.ArgumentParser(
        prog="bilibili-sync",
        description="B站收藏夹/稍后再看 转文字归档工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  bilibili-sync status              # 查看进度
  bilibili-sync sync                # 同步元数据
  bilibili-sync process             # 下载字幕 + LLM处理
  bilibili-sync export              # 导出 Markdown
  bilibili-sync run                 # 一键运行全部
  bilibili-sync sync --folders 123  # 只同步指定收藏夹
  bilibili-sync process --skip-llm  # 只下载字幕，不做LLM处理
        """,
    )

    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径（默认: config.yaml）",
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # sync
    sync_parser = subparsers.add_parser("sync", help="同步元数据（阶段0）")
    sync_parser.add_argument(
        "--folders",
        type=int,
        nargs="+",
        help="指定收藏夹 mlid（不指定则同步全部）",
    )
    sync_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多同步条数（用于测试，默认全部）",
    )

    # process
    process_parser = subparsers.add_parser("process", help="下载字幕 + LLM 处理（阶段1+3+4）")
    process_parser.add_argument(
        "--skip-subtitles",
        action="store_true",
        help="跳过字幕下载，只做 LLM 处理",
    )
    process_parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="跳过 LLM 处理，只下载字幕",
    )
    process_parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="重试所有 error 状态的视频",
    )

    # export
    subparsers.add_parser("export", help="导出 Markdown（阶段5）")

    # run
    run_parser = subparsers.add_parser("run", help="一键运行全部阶段")
    run_parser.add_argument(
        "--folders",
        type=int,
        nargs="+",
        help="指定收藏夹 mlid",
    )
    run_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理条数（用于测试，默认全部）",
    )

    # status
    subparsers.add_parser("status", help="查看处理进度")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 加载配置
    config = load_config(args.config)

    # 配置日志
    setup_logging(
        level=config.logging.level,
        log_file=config.logging.file if config.logging.file else None,
    )

    # 验证 Cookie（status 命令除外）
    if args.command != "status":
        try:
            config.bilibili.uid = validate_cookie(config.bilibili)
        except AuthError as e:
            logger.error(str(e))
            sys.exit(1)

    # 重试错误视频
    if getattr(args, "retry_errors", False):
        count = reset_error_videos(config.database.path)
        if count > 0:
            logger.info(f"已重置 {count} 个错误视频为 pending 状态")

    # 执行命令
    commands = {
        "sync": cmd_sync,
        "process": cmd_process,
        "export": cmd_export,
        "run": cmd_run,
        "status": cmd_status,
    }

    try:
        commands[args.command](args, config)
    except KeyboardInterrupt:
        logger.info("\n程序已中断，进度已保存。下次运行将继续处理。")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序异常退出: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
