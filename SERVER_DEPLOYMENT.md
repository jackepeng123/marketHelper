# 🌐 云服务器部署指南

本指南专门针对**全新的云服务器**部署 MarketHelper。

## 📋 前置要求

### 服务器配置
- **操作系统**: Ubuntu 20.04/22.04 LTS
- **CPU**: 2 核心或以上
- **内存**: 4GB 或以上（推荐 8GB）
- **磁盘**: 20GB 可用空间
- **网络**: 公网 IP，开放以下端口

### 需要开放的端口
在云服务器控制台（安全组/防火墙）中开放：
- **7860**: Gradio 前端（Web UI）
- **8000**: FastAPI 后端（API）
- **6006**: Phoenix 监控（可选，仅内网访问更安全）
- **22**: SSH（远程管理）

---

## 🚀 快速部署（3 步完成）

### 第 1 步：上传项目到服务器

#### 方法 A：使用 Git（推荐）
```bash
# 在服务器上执行
cd /opt  # 或其他你喜欢的目录
git clone <your-repo-url> marketHelper
cd marketHelper
```

#### 方法 B：使用 SCP 上传
```bash
# 在本地执行
cd /path/to/marketHelper
tar -czf marketHelper.tar.gz .
scp marketHelper.tar.gz root@your-server-ip:/opt/

# 在服务器上执行
ssh root@your-server-ip
cd /opt
mkdir -p marketHelper
tar -xzf marketHelper.tar.gz -C marketHelper
cd marketHelper
```

#### 方法 C：使用 FTP/SFTP 工具
使用 FileZilla、WinSCP 等工具上传整个项目文件夹。

---

### 第 2 步：安装 Docker

在服务器上执行：

```bash
# 进入项目目录
cd /opt/marketHelper  # 或你的项目路径

# 运行自动安装脚本
sudo bash install-docker.sh
```

脚本会自动完成：
- ✅ 安装 Docker Engine
- ✅ 安装 Docker Compose
- ✅ 配置国内镜像加速器
- ✅ 启动 Docker 服务
- ✅ 测试 Docker 运行

**预计耗时**: 3-5 分钟

---

### 第 3 步：配置并启动服务

```bash
# 1. 配置环境变量
cp .env.example .env
nano .env  # 或使用 vim .env

# 必须填写的配置:
# DEEPSEEK_API_KEY=your_key_here
# 其他 API Keys 根据需要填写

# 2. 一键启动所有服务
bash start.sh

# 等待服务启动（约 1-2 分钟）
```

---

## ✅ 验证部署

### 检查服务状态
```bash
docker ps

# 应该看到 5 个正在运行的容器:
# - markethelper-postgres
# - markethelper-redis
# - markethelper-backend
# - markethelper-frontend
```

### 访问服务

| 服务 | 访问地址 | 说明 |
|------|---------|------|
| **前端界面** | http://your-server-ip:7860 | Gradio Web UI |
| **API 文档** | http://your-server-ip:8000/docs | Swagger 文档 |
| **监控面板** | http://your-server-ip:6006 | Phoenix（建议仅内网） |

### 查看日志
```bash
# 查看所有服务日志
bash logs.sh

# 或手动查看
docker logs -f markethelper-backend
docker logs -f markethelper-frontend
```

---

## 🔒 生产环境安全加固

### 1. 修改默认密码
编辑 `.env` 文件：
```bash
POSTGRES_PASSWORD=your_strong_password_123!
REDIS_PASSWORD=your_redis_password_456!
```

重启服务：
```bash
bash stop.sh
bash start.sh
```

### 2. 配置 Nginx 反向代理（推荐）

#### 安装 Nginx
```bash
sudo apt update
sudo apt install nginx -y
```

#### 配置反向代理
```bash
sudo nano /etc/nginx/sites-available/markethelper
```

添加以下配置：
```nginx
# 前端服务
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名

    # 如果有 SSL 证书，使用 HTTPS
    # listen 443 ssl;
    # ssl_certificate /path/to/cert.pem;
    # ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:7860;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}

# API 服务
server {
    listen 80;
    server_name api.your-domain.com;  # API 子域名

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/markethelper /etc/nginx/sites-enabled/
sudo nginx -t  # 测试配置
sudo systemctl reload nginx
```

#### 修改 docker-compose.yml 端口绑定
```yaml
services:
  backend:
    ports:
      - "127.0.0.1:8000:8000"  # 只监听本地
  frontend:
    ports:
      - "127.0.0.1:7860:7860"  # 只监听本地
```

### 3. 配置防火墙
```bash
# 安装 ufw
sudo apt install ufw -y

# 配置规则
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS

# 如果不使用 Nginx，直接开放应用端口
sudo ufw allow 7860/tcp
sudo ufw allow 8000/tcp

# 启用防火墙
sudo ufw enable
sudo ufw status
```

### 4. 设置 SSL 证书（使用 Let's Encrypt）
```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx -y

# 自动配置 SSL
sudo certbot --nginx -d your-domain.com -d api.your-domain.com

# 自动续期测试
sudo certbot renew --dry-run
```

---

## 🔧 服务管理

### 常用命令
```bash
# 启动服务
bash start.sh

# 停止服务
bash stop.sh

# 重启服务
docker-compose restart

# 查看日志
bash logs.sh

# 备份数据
bash backup.sh
```

### 开机自启动
```bash
# 创建 systemd 服务
sudo nano /etc/systemd/system/markethelper.service
```

添加以下内容：
```ini
[Unit]
Description=MarketHelper Docker Services
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/marketHelper
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=root

[Install]
WantedBy=multi-user.target
```

启用自启动：
```bash
sudo systemctl daemon-reload
sudo systemctl enable markethelper.service
sudo systemctl start markethelper.service
```

---

## 📊 监控与维护

### 1. 查看资源使用
```bash
# 查看容器资源占用
docker stats

# 查看磁盘使用
df -h
du -sh /var/lib/docker
```

### 2. 日志管理
日志已配置自动轮转（最大 10MB，保留 3 个文件）

```bash
# 查看日志大小
docker inspect markethelper-backend | grep LogPath

# 清理旧日志
docker system prune -a --volumes
```

### 3. 定期备份
```bash
# 添加定时任务
crontab -e

# 每天凌晨 2 点备份
0 2 * * * cd /opt/marketHelper && bash backup.sh >> /var/log/markethelper-backup.log 2>&1
```

### 4. 监控服务状态
```bash
# 创建健康检查脚本
cat > /opt/check-markethelper.sh <<'EOF'
#!/bin/bash
if ! curl -f http://localhost:8000/docs > /dev/null 2>&1; then
    echo "$(date): Backend is down, restarting..."
    cd /opt/marketHelper && docker-compose restart backend
fi
EOF

chmod +x /opt/check-markethelper.sh

# 添加定时检查（每 5 分钟）
crontab -e
# 添加: */5 * * * * /opt/check-markethelper.sh
```

---

## 🐛 故障排查

### 服务无法启动
```bash
# 查看详细日志
docker logs markethelper-backend
docker logs markethelper-frontend

# 检查端口占用
netstat -tlnp | grep -E '8000|7860|5432|6379'

# 检查容器状态
docker ps -a
```

### 内存不足
```bash
# 查看内存使用
free -h

# 限制容器内存（修改 docker-compose.yml）
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G
```

### 磁盘空间不足
```bash
# 清理无用镜像和容器
docker system prune -a

# 清理日志
truncate -s 0 /var/lib/docker/containers/*/*-json.log
```

### 网络问题
```bash
# 重建 Docker 网络
docker-compose down
docker network prune
docker-compose up -d
```

---

## 📈 性能优化

### 1. 数据库优化
编辑 `docker-compose.yml`，添加 PostgreSQL 配置：
```yaml
postgres:
  environment:
    POSTGRES_SHARED_BUFFERS: 256MB
    POSTGRES_EFFECTIVE_CACHE_SIZE: 1GB
    POSTGRES_MAX_CONNECTIONS: 100
```

### 2. Redis 优化
```yaml
redis:
  command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
```

### 3. 应用优化
- 启用 Nginx gzip 压缩
- 配置 CDN 加速静态资源
- 使用 Redis 缓存频繁查询

---

## 🆙 更新升级

### 更新应用代码
```bash
# 拉取最新代码
git pull

# 重新构建并重启
docker-compose build
docker-compose up -d
```

### 更新 Docker 镜像
```bash
# 拉取最新基础镜像
docker-compose pull

# 重建服务
docker-compose up -d --build
```

---

## 📞 技术支持

遇到问题？
1. 查看 [完整部署文档](DEPLOYMENT.md)
2. 查看日志: `bash logs.sh`
3. 提交 Issue 到 GitHub

---

**部署成功！开始使用您的智能营销助手吧！🎉**
