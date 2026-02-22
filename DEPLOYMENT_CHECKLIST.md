# ✅ 服务器部署检查清单

## 📦 部署前准备

### 本地准备
- [ ] 确认所有代码已提交到 Git 仓库
- [ ] 准备好所有必需的 API Keys
- [ ] 检查 `.env.example` 配置是否完整

### 服务器准备
- [ ] 购买云服务器（推荐：阿里云/腾讯云/AWS）
  - 操作系统: Ubuntu 20.04/22.04 LTS
  - 配置: 2核4GB 起（推荐 4核8GB）
  - 磁盘: 20GB+ 系统盘
- [ ] 获取服务器公网 IP
- [ ] 配置 SSH 密钥登录
- [ ] 在安全组/防火墙开放端口:
  - 22 (SSH)
  - 80 (HTTP - 可选)
  - 443 (HTTPS - 可选)
  - 7860 (Gradio 前端)
  - 8000 (API 后端)
  - 6006 (Phoenix 监控 - 可选)

---

## 🚀 部署步骤

### Step 1: 上传项目到服务器
```bash
# 方法 A: 使用 Git（推荐）
ssh root@your-server-ip
cd /opt
git clone <your-repo-url> marketHelper
cd marketHelper

# 方法 B: 使用 SCP
# 在本地执行
tar -czf marketHelper.tar.gz .
scp marketHelper.tar.gz root@your-server-ip:/opt/
# 在服务器上解压
ssh root@your-server-ip
cd /opt && mkdir marketHelper
tar -xzf marketHelper.tar.gz -C marketHelper
cd marketHelper
```
- [ ] 项目文件已上传到服务器

---

### Step 2: 安装 Docker
```bash
# 在服务器上执行
sudo bash install-docker.sh
```
- [ ] Docker 安装成功
- [ ] Docker Compose 安装成功
- [ ] Docker 服务已启动
- [ ] 镜像加速器配置成功

验证命令：
```bash
docker --version
docker compose version
systemctl status docker
```

---

### Step 3: 配置环境变量
```bash
cp .env.example .env
nano .env  # 或 vim .env
```

**必须配置的变量**:
- [ ] `DEEPSEEK_API_KEY` - DeepSeek AI 密钥
- [ ] `POSTGRES_PASSWORD` - 数据库密码（修改默认值）
- [ ] `REDIS_PASSWORD` - Redis 密码（修改默认值）

**可选配置** (根据功能需求):
- [ ] `AMAP_KEY` - 高德地图
- [ ] `QWEATHER_KEY` - 和风天气
- [ ] `CLIENT_KEY`, `CLIENT_SECRET` - 抖音开放平台
- [ ] 其他 API Keys

---

### Step 4: 启动服务
```bash
bash start.sh
```
- [ ] 所有镜像构建成功
- [ ] PostgreSQL 容器启动成功
- [ ] Redis 容器启动成功
- [ ] Backend 容器启动成功
- [ ] Frontend 容器启动成功

验证命令：
```bash
docker ps
# 应该看到 4 个 Up 状态的容器
```

---

### Step 5: 测试访问
- [ ] 前端界面可访问: `http://your-server-ip:7860`
- [ ] API 文档可访问: `http://your-server-ip:8000/docs`
- [ ] Phoenix 监控可访问: `http://your-server-ip:6006` (可选)
- [ ] 测试发送一条消息，检查是否正常响应

---

## 🔒 安全加固（生产环境必做）

### 基础安全
- [ ] 修改了 `POSTGRES_PASSWORD` 默认密码
- [ ] 修改了 `REDIS_PASSWORD` 默认密码
- [ ] 配置了防火墙 (ufw)
- [ ] 禁用了 root 密码登录，只允许 SSH 密钥

### 进阶安全（推荐）
- [ ] 配置了 Nginx 反向代理
- [ ] 申请并配置了 SSL 证书 (HTTPS)
- [ ] 容器端口只监听 127.0.0.1（不直接暴露）
- [ ] 配置了 fail2ban 防止暴力破解

---

## 🔧 运维配置

### 开机自启动
- [ ] 配置了 systemd 服务
- [ ] 测试了服务器重启后自动启动

### 备份策略
- [ ] 配置了定时备份（cron）
- [ ] 测试了备份脚本
- [ ] 确定了备份存储位置

### 监控告警
- [ ] 配置了服务健康检查
- [ ] 设置了磁盘空间告警
- [ ] 配置了日志轮转

---

## 📊 性能优化（可选）

- [ ] 配置了 Nginx gzip 压缩
- [ ] 优化了 PostgreSQL 连接池
- [ ] 配置了 Redis 内存限制
- [ ] 使用了 CDN 加速（如有域名）

---

## 📝 文档记录

- [ ] 记录了服务器 IP 和登录信息
- [ ] 记录了所有密码（安全存储）
- [ ] 记录了域名配置（如有）
- [ ] 编写了团队内部操作文档

---

## 🧪 压力测试（可选）

- [ ] 测试了并发用户数
- [ ] 测试了长时间运行稳定性
- [ ] 测试了异常重启恢复

---

## ✅ 最终验证

### 功能测试
- [ ] 对话功能正常
- [ ] 意图识别正常
- [ ] 工具调用正常
- [ ] 图表生成正常
- [ ] 历史记录持久化正常

### 性能测试
- [ ] 响应速度满足要求
- [ ] 内存使用正常（不泄漏）
- [ ] CPU 使用正常

### 可靠性测试
- [ ] 服务器重启后自动恢复
- [ ] 容器异常退出后自动重启
- [ ] 数据备份恢复测试成功

---

## 🎉 部署完成！

所有检查项通过后，部署完成！

### 下一步
1. 通知团队服务已上线
2. 分享访问地址
3. 开始监控服务运行状态
4. 定期检查日志和备份

### 常用管理命令
```bash
# 查看服务状态
docker ps

# 查看日志
bash logs.sh

# 重启服务
docker-compose restart

# 停止服务
bash stop.sh

# 备份数据
bash backup.sh

# 查看资源使用
docker stats
```

---

**祝您部署顺利！🚀**
