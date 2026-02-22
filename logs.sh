#!/bin/bash
# MarketHelper 日志查看脚本

echo "📋 MarketHelper 日志查看工具"
echo "================================"
echo ""
echo "请选择要查看的服务日志:"
echo "  1) 所有服务"
echo "  2) Backend (FastAPI)"
echo "  3) Frontend (Gradio)"
echo "  4) PostgreSQL"
echo "  5) Redis"
echo "  6) 退出"
echo ""

read -p "请输入选项 (1-6): " choice

case $choice in
    1)
        echo "🔍 查看所有服务日志 (Ctrl+C 退出)..."
        docker-compose logs -f
        ;;
    2)
        echo "🔍 查看 Backend 日志 (Ctrl+C 退出)..."
        docker-compose logs -f backend
        ;;
    3)
        echo "🔍 查看 Frontend 日志 (Ctrl+C 退出)..."
        docker-compose logs -f frontend
        ;;
    4)
        echo "🔍 查看 PostgreSQL 日志 (Ctrl+C 退出)..."
        docker-compose logs -f postgres
        ;;
    5)
        echo "🔍 查看 Redis 日志 (Ctrl+C 退出)..."
        docker-compose logs -f redis
        ;;
    6)
        echo "👋 退出"
        exit 0
        ;;
    *)
        echo "❌ 无效选项"
        exit 1
        ;;
esac
