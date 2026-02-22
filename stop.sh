#!/bin/bash
# MarketHelper 停止脚本

set -e

echo "🛑 正在停止 MarketHelper..."
echo "================================"

# 停止所有服务
docker-compose down

echo ""
echo "================================"
echo "✅ 所有服务已停止"
echo ""
echo "💡 提示:"
echo "  - 重新启动: ./start.sh 或 docker-compose up -d"
echo "  - 删除数据卷: docker-compose down -v (⚠️  会删除所有数据!)"
echo "  - 查看停止的容器: docker-compose ps -a"
echo "================================"
