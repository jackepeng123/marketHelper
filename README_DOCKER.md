# 🚀 MarketHelper - Docker 快速部署

智能营销助手的 Docker 一键部署方案。

## ⚡ 快速开始

### 1. 前置要求
- Docker 20.10+
- Docker Compose 2.0+

### 2. 部署步骤

```bash
# 1. 配置环境变量
cp .env.example .env
nano .env  # 填入必要的 API Keys

# 2. 一键启动
./start.sh

# 或使用 Docker Compose
docker-compose up -d --build
```

### 3. 访问服务

| 服务 | 地址 | 说明 |
|------|------|------|
| 🎨 前端界面 | http://localhost:7860 | Gradio Web UI |
| 🔌 API 后端 | http://localhost:8000 | FastAPI REST API |
| 📚 API 文档 | http://localhost:8000/docs | Swagger UI |
| 📊 监控面板 | http://localhost:6006 | Phoenix 监控 |

## 📋 常用命令

```bash
# 启动服务
./start.sh

# 停止服务
./stop.sh

# 查看日志
./logs.sh

# 备份数据
./backup.sh

# 手动管理
docker-compose ps           # 查看状态
docker-compose logs -f      # 查看日志
docker-compose restart      # 重启服务
docker-compose down -v      # 停止并删除数据
```

## 🏗️ 服务架构

```
┌─────────────────────────────────────┐
│         Docker Network              │
│                                     │
│  PostgreSQL ──┐                     │
│               ├──> Backend (API)    │
│  Redis     ──┘         │            │
│                        │            │
│                   Frontend (UI)     │
│                        │            │
│                   Phoenix           │
└─────────────────────────────────────┘
```

## 🔧 环境变量配置

必须配置的变量 (在 `.env` 文件中):

```bash
# AI API Keys
DEEPSEEK_API_KEY=sk-xxx        # DeepSeek API 密钥

# 数据库 (可选,有默认值)
POSTGRES_PASSWORD=postgres123   # PostgreSQL 密码
REDIS_PASSWORD=redis123         # Redis 密码
```

完整配置参考: `.env.example`

## 📖 详细文档

更多详细信息请查看:
- [完整部署指南](DEPLOYMENT.md) - 详细的配置、故障排查、维护指南
- [环境变量说明](.env.example) - 所有可配置的环境变量

## ⚠️ 注意事项

1. **生产环境**: 请修改默认密码 (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`)
2. **API Keys**: 必须配置 `DEEPSEEK_API_KEY` 才能正常使用
3. **端口占用**: 确保端口 5432, 6379, 8000, 7860, 6006 未被占用
4. **数据持久化**: 数据保存在 Docker 卷中,删除卷会丢失数据

## 🐛 故障排查

### 端口冲突
```bash
# 查看占用端口的进程
lsof -i :8000

# 修改 docker-compose.yml 中的端口映射
```

### 服务无法启动
```bash
# 查看详细日志
docker-compose logs backend

# 重新构建
docker-compose build --no-cache
```

### 数据库连接失败
```bash
# 检查数据库是否就绪
docker-compose exec postgres pg_isready

# 重启服务
docker-compose restart backend
```

更多问题请查看 [DEPLOYMENT.md](DEPLOYMENT.md#常见问题)

## 📦 数据备份与恢复

```bash
# 备份
./backup.sh

# 恢复
tar -xzf backups/markethelper_backup_YYYYMMDD_HHMMSS.tar.gz -C backups/
docker-compose exec -T postgres psql -U postgres markethelper < backups/postgres_YYYYMMDD_HHMMSS.sql
```

## 🛠️ 开发模式

如需在开发时热重载代码:

```bash
# 修改 docker-compose.yml，添加 volumes 挂载
volumes:
  - ./app:/app/app
  - ./server_redis.py:/app/server_redis.py

# 使用开发模式启动
docker-compose up
```

## 📞 支持

遇到问题? 
- 查看 [详细文档](DEPLOYMENT.md)
- 提交 Issue

---

**享受智能营销的乐趣！🎉**
