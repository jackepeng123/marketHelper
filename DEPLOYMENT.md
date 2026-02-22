# 🚀 MarketHelper Docker 部署指南

本文档提供完整的 Docker 部署方案，包含 Redis、PostgreSQL 和应用服务。

## 📋 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [服务架构](#服务架构)
- [常见问题](#常见问题)
- [维护指南](#维护指南)

---

## 系统要求

### 硬件要求
- **CPU**: 2 核心或以上
- **内存**: 4GB 或以上 (推荐 8GB)
- **磁盘空间**: 10GB 可用空间

### 软件要求
- **Docker**: 20.10+ 
- **Docker Compose**: 2.0+
- **操作系统**: Linux / macOS / Windows (with WSL2)

### 检查 Docker 版本
```bash
docker --version
docker-compose --version
```

---

## 快速开始

### 1. 克隆项目 (如果还未克隆)
```bash
git clone <your-repo-url>
cd marketHelper
```

### 2. 配置环境变量
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入必要的 API Keys
nano .env  # 或使用其他编辑器
```

**⚠️ 重要**: 请务必填写以下必需的环境变量：
- `DEEPSEEK_API_KEY`: DeepSeek AI API 密钥
- 其他第三方 API 密钥（根据功能需求）

### 3. 一键启动所有服务
```bash
# 构建并启动所有服务
docker-compose up -d --build

# 查看启动日志
docker-compose logs -f
```

### 4. 验证服务状态
```bash
# 检查所有服务是否正常运行
docker-compose ps

# 应该看到以下服务都处于 "Up" 状态:
# - markethelper-postgres
# - markethelper-redis
# - markethelper-backend
# - markethelper-frontend
```

### 5. 访问服务

| 服务 | 地址 | 说明 |
|------|------|------|
| **Gradio 前端** | http://localhost:7860 | 智能营销助手 Web UI |
| **FastAPI 后端** | http://localhost:8000 | REST API 接口 |
| **API 文档** | http://localhost:8000/docs | Swagger 交互式文档 |
| **Phoenix 监控** | http://localhost:6006 | LLM 调用链路追踪 |
| **PostgreSQL** | localhost:5432 | 数据库 (外部访问) |
| **Redis** | localhost:6379 | 缓存 (外部访问) |

---

## 配置说明

### 环境变量详解

#### 数据库配置
```bash
POSTGRES_DB=markethelper          # 数据库名称
POSTGRES_USER=postgres            # 数据库用户名
POSTGRES_PASSWORD=postgres123     # 数据库密码 (生产环境请修改!)
DATABASE_URL=postgresql://...     # 完整连接字符串
```

#### Redis 配置
```bash
REDIS_PASSWORD=redis123           # Redis 密码 (生产环境请修改!)
REDIS_URL=redis://:redis123@redis:6379
```

#### API Keys
请在 `.env` 文件中填写您的真实密钥：
- `DEEPSEEK_API_KEY`: DeepSeek AI
- `AMAP_KEY`: 高德地图
- `QWEATHER_KEY`: 和风天气
- `MANUS_API_KEY`: Manus
- `CLIENT_KEY`, `CLIENT_SECRET`: 抖音开放平台
- 等等...

#### Phoenix 监控配置
```bash
PHOENIX_AUTO_START=1              # 自动启动 Phoenix (1=启动, 0=禁用)
PHOENIX_PORT=6006                 # Phoenix Web UI 端口
PHOENIX_GRPC_PORT=4317            # Phoenix gRPC 端口
```

---

## 服务架构

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                        │
│                (markethelper-network)                    │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  PostgreSQL  │  │    Redis     │  │   Backend    │ │
│  │   :5432      │  │   :6379      │  │   :8000      │ │
│  │              │  │              │  │  (FastAPI)   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│         │                  │                 │          │
│         └──────────────────┴─────────────────┘          │
│                            │                            │
│                  ┌──────────────┐                       │
│                  │   Frontend   │                       │
│                  │   :7860      │                       │
│                  │  (Gradio)    │                       │
│                  └──────────────┘                       │
│                            │                            │
│                  ┌──────────────┐                       │
│                  │   Phoenix    │                       │
│                  │   :6006      │                       │
│                  │ (Monitoring) │                       │
│                  └──────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

### 服务说明

1. **PostgreSQL**: 
   - 用途: 存储对话历史、状态检查点
   - 数据持久化: `markethelper-postgres-data` 卷

2. **Redis**: 
   - 用途: 流式消息队列、缓存
   - 数据持久化: `markethelper-redis-data` 卷

3. **Backend (FastAPI)**:
   - 核心 API 服务
   - LangGraph Agent 执行引擎
   - 集成 Phoenix 监控

4. **Frontend (Gradio)**:
   - 用户交互界面
   - 实时流式对话
   - 图表可视化

5. **Phoenix**:
   - LLM 调用链路追踪
   - 性能监控
   - 调试工具

---

## 常用命令

### 服务管理
```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启服务
docker-compose restart

# 查看服务状态
docker-compose ps

# 查看服务日志
docker-compose logs -f [service_name]
```

### 单独控制服务
```bash
# 只启动后端
docker-compose up -d backend

# 重启前端
docker-compose restart frontend

# 查看 PostgreSQL 日志
docker-compose logs -f postgres
```

### 数据管理
```bash
# 备份 PostgreSQL 数据库
docker-compose exec postgres pg_dump -U postgres markethelper > backup.sql

# 恢复数据库
docker-compose exec -T postgres psql -U postgres markethelper < backup.sql

# 连接到 PostgreSQL
docker-compose exec postgres psql -U postgres -d markethelper

# 连接到 Redis CLI
docker-compose exec redis redis-cli -a redis123
```

### 容器管理
```bash
# 进入容器 Shell
docker-compose exec backend bash
docker-compose exec postgres bash

# 查看容器资源使用
docker stats

# 清理未使用的资源
docker system prune -a
```

---

## 常见问题

### 1. 端口冲突
**问题**: `Error: bind: address already in use`

**解决方案**:
```bash
# 查看占用端口的进程
lsof -i :8000  # 或其他端口号

# 修改 docker-compose.yml 中的端口映射
ports:
  - "8001:8000"  # 将宿主机端口改为 8001
```

### 2. 数据库连接失败
**问题**: `FATAL: password authentication failed`

**解决方案**:
1. 检查 `.env` 文件中的数据库密码是否正确
2. 确保 `DATABASE_URL` 使用了正确的密码
3. 重启服务:
```bash
docker-compose down
docker-compose up -d
```

### 3. Redis 连接失败
**问题**: `Error connecting to Redis`

**检查方案**:
```bash
# 1. 确认 Redis 容器正在运行
docker-compose ps redis

# 2. 测试 Redis 连接
docker-compose exec redis redis-cli -a redis123 ping
# 应该返回: PONG

# 3. 检查 server_redis.py 中的 REDIS_URL
# 确保使用容器名称 "redis" 而非 "localhost"
```

### 4. 内存不足
**问题**: 容器频繁重启或 OOM (Out of Memory)

**解决方案**:
```yaml
# 在 docker-compose.yml 中限制资源
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

### 5. 构建失败
**问题**: 依赖安装失败

**解决方案**:
```bash
# 清理缓存后重新构建
docker-compose build --no-cache backend

# 如果是网络问题，可以使用国内镜像
# 在 Dockerfile 中添加:
# RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 维护指南

### 定期备份
```bash
# 创建备份脚本 backup.sh
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec postgres pg_dump -U postgres markethelper > "backup_${DATE}.sql"
echo "Backup completed: backup_${DATE}.sql"

# 添加执行权限
chmod +x backup.sh

# 设置定时任务 (crontab)
0 2 * * * /path/to/backup.sh
```

### 日志管理
```bash
# 限制日志大小 (在 docker-compose.yml 中)
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### 更新服务
```bash
# 1. 拉取最新代码
git pull

# 2. 重新构建镜像
docker-compose build

# 3. 滚动更新 (避免停机)
docker-compose up -d --no-deps --build backend
docker-compose up -d --no-deps --build frontend
```

### 监控与告警
1. 访问 Phoenix 监控面板: http://localhost:6006
2. 查看 LLM 调用链路和性能指标
3. 设置告警规则 (可集成 Prometheus + Grafana)

---

## 生产环境建议

### 安全加固
1. **修改默认密码**:
   - PostgreSQL: `POSTGRES_PASSWORD`
   - Redis: `REDIS_PASSWORD`

2. **关闭外部端口**:
   ```yaml
   # 只暴露必要的端口给外网
   ports:
     - "127.0.0.1:5432:5432"  # 仅本地访问
   ```

3. **使用 HTTPS**:
   - 配置 Nginx 反向代理
   - 申请 SSL 证书 (Let's Encrypt)

4. **环境变量管理**:
   - 使用 Docker Secrets 或 Vault
   - 不要将 `.env` 提交到 Git

### 性能优化
1. **数据库连接池**: 已在代码中使用 `AsyncConnectionPool`
2. **Redis 持久化**: 已启用 AOF (Append-Only File)
3. **容器资源限制**: 根据负载调整内存和 CPU 限制
4. **日志级别**: 生产环境设置为 `WARNING` 或 `ERROR`

### 高可用部署
1. **数据库主从复制**: 配置 PostgreSQL Replication
2. **Redis 集群**: 使用 Redis Sentinel 或 Cluster
3. **负载均衡**: 使用 Nginx 或 Traefik
4. **容器编排**: 迁移到 Kubernetes (可选)

---

## 故障排查

### 查看完整日志
```bash
# 所有服务日志
docker-compose logs --tail=100 -f

# 特定服务日志
docker-compose logs -f backend

# 导出日志到文件
docker-compose logs > debug.log
```

### 容器健康检查
```bash
# 查看健康状态
docker inspect markethelper-backend | grep -A 10 Health

# 手动执行健康检查
docker-compose exec backend curl -f http://localhost:8000/docs
```

### 网络诊断
```bash
# 进入容器测试网络连通性
docker-compose exec backend ping postgres
docker-compose exec backend ping redis

# 查看 DNS 解析
docker-compose exec backend nslookup postgres
```

---

## 联系与支持

如有问题，请:
1. 查看 [常见问题](#常见问题) 章节
2. 查看日志: `docker-compose logs`
3. 提交 Issue 到 GitHub 仓库

---

## 附录

### 完整的 Docker Compose 配置
详见项目根目录的 `docker-compose.yml` 文件。

### 环境变量完整列表
详见项目根目录的 `.env.example` 文件。

---

**部署愉快！🎉**
