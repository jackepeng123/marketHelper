#!/bin/bash
# Docker 自动安装脚本 (Ubuntu 20.04/22.04)
# 使用阿里云镜像加速

set -e

echo "========================================"
echo "🐳 Docker 自动安装脚本"
echo "========================================"
echo ""

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then 
    echo "❌ 请使用 root 权限运行此脚本"
    echo "💡 使用命令: sudo bash install-docker.sh"
    exit 1
fi

# 检查是否已安装 Docker
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    echo "✅ Docker 已安装: $DOCKER_VERSION"
    read -p "是否要重新安装? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "跳过安装，退出脚本"
        exit 0
    fi
fi

echo "📦 步骤 1/6: 更新系统软件包..."
apt-get update -qq

echo "📦 步骤 2/6: 安装必要的依赖..."
apt-get install -y -qq \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common

echo "🔑 步骤 3/6: 添加 Docker 官方 GPG 密钥..."
# 使用阿里云镜像
curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo "📝 步骤 4/6: 添加 Docker APT 仓库..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "🔄 步骤 5/6: 更新软件包索引..."
apt-get update -qq

echo "⬇️  步骤 6/6: 安装 Docker Engine..."
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo ""
echo "✅ Docker 安装完成！"
echo ""

# 启动 Docker 服务
echo "🚀 启动 Docker 服务..."
systemctl start docker
systemctl enable docker

# 配置 Docker 镜像加速器
echo "⚡ 配置 Docker 镜像加速器..."
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
EOF

echo "🔄 重启 Docker 服务以应用配置..."
systemctl daemon-reload
systemctl restart docker

# 验证安装
echo ""
echo "========================================"
echo "✅ Docker 安装成功！"
echo "========================================"
echo ""
docker --version
docker compose version
echo ""

# 测试 Docker
echo "🧪 测试 Docker 运行..."
if docker run --rm hello-world > /dev/null 2>&1; then
    echo "✅ Docker 测试成功！"
else
    echo "⚠️  Docker 测试失败，但已安装完成"
fi

echo ""
echo "========================================"
echo "📝 常用命令:"
echo "  - 查看 Docker 状态: systemctl status docker"
echo "  - 查看 Docker 信息: docker info"
echo "  - 查看运行容器: docker ps"
echo "  - 查看镜像列表: docker images"
echo ""
echo "🎉 下一步: 运行 ./start.sh 启动 MarketHelper"
echo "========================================"
