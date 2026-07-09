#!/bin/bash
# B站同步工具 - ASR 环境清理脚本
# 卸载所有 ASR 相关依赖，删除下载的模型

set -e

echo "=== B站同步工具 ASR 环境清理 ==="
echo ""

# 查找正确的 Python（优先 venv，其次 python3.11，最后 python3）
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3.11 &> /dev/null; then
    PYTHON="python3.11"
else
    PYTHON="python3"
fi

PIP="$PYTHON -m pip"

# 1. 卸载 pip 包
echo ">>> 卸载 pip 包（使用 $PYTHON）..."
PACKAGES="faster-whisper ctranslate2 onnxruntime huggingface-hub tokenizers av"
for pkg in $PACKAGES; do
    $PIP uninstall -y "$pkg" 2>/dev/null && echo "   已卸载 $pkg" || echo "   $pkg 未安装，跳过"
done
# 系统 Python 可能需要 --break-system-packages
$PIP uninstall --break-system-packages -y $PACKAGES 2>/dev/null || true
echo "  完成"

# 2. 删除 Whisper 模型和 HF 缓存
echo ">>> 删除 HuggingFace 缓存..."
rm -rf ~/.cache/huggingface/
echo "  完成"

# 3. 删除临时音频文件（如果有残留）
echo ">>> 清理临时音频..."
rm -f /tmp/bilibili_asr_*.m4a /tmp/bilibili_asr_*.mp3 /tmp/bilibili_asr_*.webm /tmp/bilibili_cookie_*.txt 2>/dev/null || true
echo "  完成"

# 4. 删除项目本地 .db 和 output
echo ">>> 清理项目数据..."
rm -f bilibili_sync.db bilibili_sync.log 2>/dev/null || true
rm -rf output/ 2>/dev/null || true
echo "  完成"

echo ""
echo "=== 清理完成 ==="
