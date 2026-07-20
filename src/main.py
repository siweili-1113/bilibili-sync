"""CLI 入口：B站收藏夹/稍后再看 转文字归档工具。

命令：
    sync      - 同步元数据（阶段0）
    process   - 下载字幕 + LLM 处理（阶段1+3+4）
    export    - 导出 Markdown（阶段5）
    review    - 审查处理结果，决定 B站 端去留
    run       - 一键运行全部阶段
    status    - 查看处理进度
"""

import argparse
import logging
import sys
import textwrap

from src.api.client import BilibiliClient
from src.auth import AuthError, validate_cookie
from src.config import AppConfig, load_config
from src.database import get_connection, get_stats, init_db, reset_error_videos
from src.exporter import export_all
from src.llm import LLMProcessor
from src.processor import process_pending_videos
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
    source = getattr(args, "source", "all")
    sync_all(client, config, config.database.path, folder_ids=folder_ids, limit=limit, source=source)


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
        process_pending_videos(config, config.database.path, max_retries=max_retries)

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

            # LLM 返回空内容时回退到原始 ASR 文本
            if not cleaned or not cleaned.strip():
                logger.warning(f"  LLM 返回空内容，回退到原始 ASR 文本")
                cleaned = raw_text
                summary = "(LLM 处理失败，以下为原始语音转录文本)"

            update_video_status(
                config.database.path,
                bvid,
                "llm_processed",
                cleaned_text=cleaned,
                summary=summary,
            )
            logger.info(f"  ✓ 完成")

            # 请求间缓冲，避免 API 波动
            import time
            time.sleep(0.5)

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
    """一键运行：同步 → 逐视频处理 → 实时审查 → 导出。

    每个视频下载音频 → Whisper 转录 → LLM 整理 → 展示摘要等你决定。
    中断后重跑自动从断点继续。
    """
    from src.api.actions import add_to_favorites, ensure_folder, remove_from_watch_later
    from src.asr import transcribe_video
    from src.database import get_connection, get_videos_by_status, increment_retry, update_video_status

    logger.info("=" * 60)
    logger.info("B站收藏夹/稍后再看 → 文字归档工具")
    logger.info("=" * 60)

    # 阶段0: 同步元数据（默认只看稍后再看）
    logger.info("正在同步稍后再看列表...")
    init_db(config.database.path)
    source = getattr(args, "source", "watch_later")
    limit = getattr(args, "limit", None)
    folder_ids = getattr(args, "folders", None) or config.sync.favorite_folder_ids or None

    client = BilibiliClient(
        config.bilibili,
        rate_limit_min=config.sync.rate_limit_min,
        rate_limit_max=config.sync.rate_limit_max,
        max_retries=config.sync.max_retries,
    )
    sync_all(client, config, config.database.path, folder_ids=folder_ids, limit=limit, source=source)

    # 确保收藏夹存在
    has_csrf = bool(config.bilibili.csrf)
    folder_mlid = None
    if has_csrf:
        try:
            folder_mlid = ensure_folder(config)
        except Exception as e:
            logger.warning(f"创建收藏夹失败 ({e})，将跳过 B站 写操作")

    # 逐视频处理
    pending = get_videos_by_status(config.database.path, "pending")
    total = len(pending)

    if total == 0:
        # 检查是否有待审查的视频（上次中断后残留）
        unreviewed = get_videos_by_status(config.database.path, "llm_processed")
        if unreviewed:
            logger.info(f"没有待处理的视频，但有 {len(unreviewed)} 个待审查的视频")
            _interactive_review(config, unreviewed, folder_mlid, has_csrf)
        else:
            logger.info("没有待处理的视频。稍后再看已全部处理完毕！")
        _print_summary(config)
        return

    logger.info(f"共 {total} 个视频待处理，逐个进行...\n")
    sessdata = config.bilibili.sessdata
    user_agent = config.bilibili.user_agent
    llm = LLMProcessor(config.llm)

    processed = []
    for i, video in enumerate(pending):
        bvid = video["bvid"]
        aid = video["aid"]
        title = video["title"] or bvid
        duration = video["duration"] or 0

        print(f"\n{'=' * 50}")
        print(f"[{i + 1}/{total}] {title}")
        print(f"{'=' * 50}")

        # ASR 转录
        logger.info("  🎤 正在转录语音...")
        raw_text = ""
        try:
            raw_text = transcribe_video(bvid, sessdata, user_agent)
        except Exception as e:
            logger.error(f"  ASR 失败: {e}")
            increment_retry(config.database.path, bvid, str(e), config.sync.max_retries)
            continue

        # 低内容跳过
        if len(raw_text) <= 20:
            logger.info(f"  ⏭️ 语音内容过少 ({len(raw_text)} 字)，跳过")
            update_video_status(config.database.path, bvid, "no_subtitle")
            continue

        logger.info(f"  ✅ 转录完成 ({len(raw_text)} 字)")

        # LLM 整理
        logger.info("  📝 正在用 LLM 整理文字...")
        try:
            cleaned, summary = llm.process(raw_text)
            if not cleaned or not cleaned.strip():
                logger.warning("  LLM 返回空内容，保留原始转录文本")
                cleaned = raw_text
                summary = ""
        except Exception as e:
            logger.error(f"  LLM 失败: {e}")
            cleaned = raw_text
            summary = ""

        logger.info(f"  ✅ 整理完成")

        # 展示摘要
        if summary.strip():
            print()
            for line in summary.split("\n"):
                line = line.strip()
                if line:
                    print(f"  {line}")

        # 存库
        update_video_status(
            config.database.path, bvid, "llm_processed",
            raw_subtitle_text=raw_text,
            cleaned_text=cleaned,
            summary=summary,
        )

        # 用户决定
        print()
        actions = []
        if has_csrf and folder_mlid and aid:
            actions.append(("k", "保留+收藏+删稍后再看"))
        if has_csrf and aid:
            actions.append(("d", "从稍后再看删除"))
        actions.append(("s", "跳过"))

        prompt_parts = [f"[{k}] {desc}" for k, desc in actions]
        prompt_parts.append("[n] 处理完退出")
        prompt_parts.append("[q] 立刻退出")
        prompt = "  " + "    ".join(prompt_parts)
        if not has_csrf:
            prompt += "\n  (未配置 CSRF，无法操作 B站。编辑 .env 添加 BILIBILI_CSRF=bili_jct)"

        valid_keys = {k for k, _ in actions} | {"n", "q"}

        while True:
            choice = input(f"{prompt}\n  > ").strip().lower()
            if choice in valid_keys:
                break
            print("  无效输入")

        if choice == "q":
            logger.info("立刻退出，当前视频未处理。下次运行重新转录。")
            break

        if choice == "k":
            from src.exporter import export_video
            export_video(dict(video), config.output.base_dir)
            update_video_status(config.database.path, bvid, "markdown_generated")
            add_to_favorites(config, aid, folder_mlid)
            remove_from_watch_later(config, aid)
            print("  ✅ 已保存笔记 + 收藏 + 从稍后再看删除")
        elif choice == "d":
            remove_from_watch_later(config, aid)
            update_video_status(config.database.path, bvid, "markdown_generated")
            print("  ✅ 已从稍后再看删除")
        elif choice == "s":
            print("  ⏭️ 已跳过")

        if choice == "n":
            logger.info("处理完当前视频，退出。下次运行继续处理剩余视频。")
            break

        import time
        time.sleep(0.3)

    # 检查是否有上一轮中断残留的未审查视频
    unreviewed = get_videos_by_status(config.database.path, "llm_processed")
    if unreviewed:
        logger.info(f"\n还有 {len(unreviewed)} 个上次未审查的视频：")
        _interactive_review(config, unreviewed, folder_mlid, has_csrf)

    logger.info("\n全部完成！")
    _print_summary(config)


def _interactive_review(config, videos, folder_mlid, has_csrf):
    """交互审查已处理但未决定的视频。"""
    import textwrap
    from src.api.actions import add_to_favorites, remove_from_watch_later
    from src.database import update_video_status

    total = len(videos)
    for i, v in enumerate(videos):
        title = v["title"] or v["bvid"]
        summary = v["summary"] or ""
        aid = v["aid"]
        bvid = v["bvid"]

        print(f"\n[{i + 1}/{total}] {title}")
        if summary.strip():
            for line in summary.split("\n"):
                line = line.strip()
                if line:
                    print(f"  {line}")

        print()
        actions = []
        if has_csrf and folder_mlid and aid:
            actions.append(("k", "保留+收藏+删稍后再看"))
        if has_csrf and aid:
            actions.append(("d", "从稍后再看删除"))
        actions.append(("s", "跳过"))

        prompt_parts = [f"[{k}] {desc}" for k, desc in actions]
        prompt_parts.append("[n] 处理完退出")
        prompt_parts.append("[q] 立刻退出")
        prompt = "  " + "    ".join(prompt_parts)
        valid_keys = {k for k, _ in actions} | {"n", "q"}

        while True:
            choice = input(f"{prompt}\n  > ").strip().lower()
            if choice in valid_keys:
                break

        if choice == "q":
            break
        elif choice == "k":
            from src.exporter import export_video
            export_video(dict(v), config.output.base_dir)
            update_video_status(config.database.path, bvid, "markdown_generated")
            if has_csrf:
                add_to_favorites(config, aid, folder_mlid)
                remove_from_watch_later(config, aid)
            print("  ✅ 已保存笔记 + 收藏 + 删除")
        elif choice == "d":
            if has_csrf:
                remove_from_watch_later(config, aid)
            update_video_status(config.database.path, bvid, "markdown_generated")
            print("  ✅ 已从稍后再看删除")
        elif choice == "s":
            print("  ⏭️ 跳过")

        if choice == "n":
            break


def cmd_status(args: argparse.Namespace, config: AppConfig) -> None:
    """查看数据库统计。"""
    init_db(config.database.path)
    _print_summary(config)


def cmd_review(args: argparse.Namespace, config: AppConfig) -> None:
    """审查处理完成的稍后再看视频，决定 B站 端去留。"""
    from src.api.actions import add_to_favorites, ensure_folder, remove_from_watch_later

    init_db(config.database.path)

    if not config.bilibili.csrf:
        logger.error("未配置 BILIBILI_CSRF，无法执行写操作。请在 .env 中设置 BILIBILI_CSRF=bili_jct")
        sys.exit(1)

    # 获取待审查视频（llm_processed 或 markdown_generated 状态的稍后再看）
    conn = get_connection(config.database.path)
    videos = conn.execute(
        "SELECT * FROM videos WHERE source='watch_later' AND status IN ('llm_processed','markdown_generated') ORDER BY id"
    ).fetchall()

    if not videos:
        logger.info("没有待审查的稍后再看视频。请先运行 process 命令。")
        return

    folder_mlid = ensure_folder(config)
    total = len(videos)
    logger.info(f"共 {total} 个视频待审查\n")

    for i, v in enumerate(videos):
        aid = v["aid"]
        bvid = v["bvid"]
        title = v["title"] or bvid
        summary = v["summary"] or ""
        # 只展示标签和短句部分，不展示完整文本
        summary_preview = textwrap.shorten(summary, width=300, placeholder="...")

        print(f"[{i + 1}/{total}] {title}")
        if summary_preview.strip():
            # 缩进显示摘要
            for line in summary_preview.split("\n"):
                line = line.strip()
                if line:
                    print(f"  {line}")
        print()

        while True:
            choice = input("  [d] 从稍后再看删除    [f] 收藏+删除    [s] 跳过    [q] 退出\n  > ").strip().lower()
            if choice in ("d", "f", "s", "q"):
                break
            print("  无效输入，请选择 d/f/s/q")

        if choice == "q":
            logger.info("已退出审查")
            break
        elif choice == "s":
            continue
        elif choice == "f":
            if add_to_favorites(config, aid, folder_mlid):
                remove_from_watch_later(config, aid)
                print("  ✅ 已收藏并从稍后再看删除\n")
            else:
                print("  ❌ 收藏失败，跳过\n")
        elif choice == "d":
            if remove_from_watch_later(config, aid):
                print("  ✅ 已从稍后再看删除\n")
            else:
                print("  ❌ 删除失败\n")

    logger.info("审查完成")


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
    sync_parser.add_argument(
        "--source",
        choices=["all", "favorites", "watch_later"],
        default="all",
        help="同步来源（默认: all）",
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

    # review
    subparsers.add_parser("review", help="审查稍后再看，决定 B站 端去留")

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
    run_parser.add_argument(
        "--source",
        choices=["all", "favorites", "watch_later"],
        default="watch_later",
        help="同步来源（默认: watch_later）",
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
        "review": cmd_review,
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
