#!/bin/bash
# MarketHelper 数据备份脚本

set -e

# 创建备份目录
BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"

# 生成时间戳
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "💾 正在备份 MarketHelper 数据..."
echo "================================"

# 备份 PostgreSQL 数据库
echo "📦 备份 PostgreSQL 数据库..."
docker-compose exec -T postgres pg_dump -U postgres markethelper > "$BACKUP_DIR/postgres_${TIMESTAMP}.sql"
echo "✅ PostgreSQL 备份完成: $BACKUP_DIR/postgres_${TIMESTAMP}.sql"

# 备份 Redis 数据 (可选)
echo "📦 备份 Redis 数据..."
docker-compose exec redis redis-cli -a redis123 --rdb "$BACKUP_DIR/redis_${TIMESTAMP}.rdb" SAVE 2>/dev/null || true
echo "✅ Redis 备份完成"

# 压缩备份文件
echo "🗜️  压缩备份文件..."
tar -czf "$BACKUP_DIR/markethelper_backup_${TIMESTAMP}.tar.gz" -C "$BACKUP_DIR" "postgres_${TIMESTAMP}.sql" 2>/dev/null || true
rm -f "$BACKUP_DIR/postgres_${TIMESTAMP}.sql"

echo ""
echo "================================"
echo "✅ 备份完成！"
echo "📁 备份文件: $BACKUP_DIR/markethelper_backup_${TIMESTAMP}.tar.gz"
echo ""
echo "📝 恢复命令:"
echo "  tar -xzf $BACKUP_DIR/markethelper_backup_${TIMESTAMP}.tar.gz -C $BACKUP_DIR"
echo "  docker-compose exec -T postgres psql -U postgres markethelper < $BACKUP_DIR/postgres_${TIMESTAMP}.sql"
echo "================================"
