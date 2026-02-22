#!/bin/bash
# MarketHelper 启动脚本

set -e

echo "🚀 正在启动 MarketHelper..."
echo "================================"

# 检查 .env 文件是否存在
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env 文件，正在从模板创建..."
    cp .env.example .env
    echo "✅ 已创建 .env 文件，请编辑并填入必要的 API Keys"
    echo "📝 编辑命令: nano .env"
    exit 1
fi

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行，请先启动 Docker"
    exit 1
fi

# 构建并启动服务
echo "📦 正在构建 Docker 镜像..."
docker-compose build

echo ""
echo "🔄 正在启动所有服务..."
docker-compose up -d

echo ""
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo ""
echo "📊 服务状态检查:"
docker-compose ps

echo ""
echo "================================"
echo "✅ MarketHelper 启动完成！"
echo ""
echo "🌐 访问地址:"
echo "  - Gradio 前端:    http://localhost:7860"
echo "  - FastAPI 后端:   http://localhost:8000"
echo "  - API 文档:       http://localhost:8000/docs"
echo "  - Phoenix 监控:   http://localhost:6006"
echo ""
echo "📝 查看日志: docker-compose logs -f"
echo "🛑 停止服务: ./stop.sh 或 docker-compose down"
echo "================================"
