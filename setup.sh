#!/bin/bash
# ============================================
# B站收藏夹/稍后再看 → 文字归档工具
# 一键环境安装脚本
# ============================================
set -e

echo "========================================"
echo " B站同步工具 - 环境安装"
echo "========================================"
echo ""

# 检查 Python 版本
PYTHON=""
for py in python3.11 python3.12 python3.10 python3; do
    if command -v $py &> /dev/null; then
        ver=$($py --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        if [ "$(echo "$ver >= 3.10" | bc 2>/dev/null || echo 0)" = "1" ] || [ "${ver%.*}" -ge 10 ] 2>/dev/null; then
            PYTHON=$py
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ 未找到 Python >= 3.10，请先安装 Python"
    echo "   brew install python@3.11"
    exit 1
fi

echo "✅ Python: $($PYTHON --version)"

# 选择 pip 镜像
echo ""
echo "选择 pip 镜像源:"
echo "  1) 清华镜像 (国内推荐)"
echo "  2) 官方源 (海外)"
read -p "请选择 [1]: " mirror_choice
mirror_choice=${mirror_choice:-1}

if [ "$mirror_choice" = "1" ]; then
    PIP_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
    HF_ENDPOINT="https://hf-mirror.com"
    echo "   使用清华镜像"
else
    PIP_INDEX="https://pypi.org/simple"
    HF_ENDPOINT="https://huggingface.co"
    echo "   使用官方源"
fi

# 创建虚拟环境
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo ""
    echo ">>> 创建虚拟环境..."
    $PYTHON -m venv "$VENV_DIR"
    echo "   ✅ 已创建 $VENV_DIR"
else
    echo "   ⏭️  $VENV_DIR 已存在，跳过"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 安装依赖
echo ""
echo ">>> 安装依赖..."
pip install --upgrade pip -q
pip install -e "." -i "$PIP_INDEX"
echo "   ✅ 依赖安装完成"

# 复制配置文件
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo ">>> 已创建 .env 配置文件，请编辑填入你的信息:"
    echo "   nano .env"
    echo ""
    echo "   必填项:"
    echo "   1. BILIBILI_SESSDATA - 从浏览器 Cookie 获取"
    echo "   2. LLM_API_KEY       - DeepSeek/OpenAI API Key"
else
    echo "   ⏭️  .env 已存在，跳过"
fi

# 设置 HF 镜像环境变量
echo ""
echo ">>> HuggingFace 镜像: $HF_ENDPOINT"
echo "   (Whisper 模型首次运行自动下载 ~500MB)"

echo ""
echo "========================================"
echo " ✅ 安装完成！"
echo ""
echo " 下一步:"
echo "   1. 编辑 .env 填入配置: nano .env"
echo "   2. 测试连接: $PYTHON -m src.main status"
echo "   3. 试跑 5 个视频: $PYTHON -m src.main run --limit 5"
echo ""
echo " 清理环境: ./cleanup.sh"
echo "========================================"
