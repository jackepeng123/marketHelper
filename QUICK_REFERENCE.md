# ⚡ 快速命令参考

## 🚀 一键部署（3 条命令）

```bash
# 1. 安装 Docker (仅首次)
sudo bash install-docker.sh

# 2. 配置环境变量
cp .env.example .env && nano .env

# 3. 启动服务
bash start.sh
```

访问: http://your-server-ip:7860

---

## 📋 常用命令

### 服务管理
```bash
bash start.sh          # 启动所有服务
bash stop.sh           # 停止所有服务
bash logs.sh           # 查看日志（交互式）
docker-compose restart # 重启服务
docker ps              # 查看运行状态
```

### 日志查看
```bash
docker logs -f markethelper-backend   # 后端日志
docker logs -f markethelper-frontend  # 前端日志
docker logs -f markethelper-postgres  # 数据库日志
docker-compose logs --tail=100        # 所有服务最近 100 条
```

### 数据管理
```bash
bash backup.sh         # 备份数据库
docker-compose down -v # 停止并删除数据（⚠️ 危险）
```

### 资源监控
```bash
docker stats                    # 实时资源使用
df -h                          # 磁盘空间
free -h                        # 内存使用
netstat -tlnp | grep -E '8000|7860'  # 端口占用
```

---

## 🔧 故障排查

### 服务无法启动
```bash
# 1. 查看详细日志
docker logs markethelper-backend

# 2. 检查配置
cat .env

# 3. 重新构建
docker-compose build --no-cache
docker-compose up -d
```

### 端口被占用
```bash
# 查看占用进程
lsof -i :8000
sudo kill -9 <PID>
```

### 网络问题
```bash
# 重建网络
docker-compose down
docker network prune
docker-compose up -d
```

### 清理磁盘空间
```bash
docker system prune -a  # 清理未使用资源
docker volume prune     # 清理未使用卷
```

---

## 🔐 安全配置

### 修改密码
```bash
nano .env
# 修改: POSTGRES_PASSWORD, REDIS_PASSWORD
docker-compose down && docker-compose up -d
```

### 配置防火墙
```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 7860/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

### SSL 证书（Let's Encrypt）
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 📊 访问地址

| 服务 | 地址 | 端口 |
|------|------|------|
| Gradio 前端 | http://IP:7860 | 7860 |
| API 后端 | http://IP:8000 | 8000 |
| API 文档 | http://IP:8000/docs | 8000 |
| Phoenix 监控 | http://IP:6006 | 6006 |

---

## 🆘 紧急操作

### 立即停止所有服务
```bash
docker-compose down
```

### 恢复备份
```bash
# 恢复数据库
tar -xzf backups/markethelper_backup_20260222.tar.gz -C backups/
docker-compose exec -T postgres psql -U postgres markethelper < backups/postgres_20260222.sql
```

### 重置所有数据（⚠️ 危险）
```bash
docker-compose down -v
docker-compose up -d
```

---

## 📱 常用路径

```
/opt/marketHelper/          # 项目目录
/var/lib/docker/volumes/    # Docker 数据卷
/etc/docker/daemon.json     # Docker 配置
/etc/nginx/sites-available/ # Nginx 配置
```

---

**保存此文件以便快速查找命令！📌**
