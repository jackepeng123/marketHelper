# 使用 Python 3.11 slim 版本作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    lsof \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    redis \
    psycopg[binary] \
    psycopg-pool \
    sse-starlette \
    httpx \
    gradio \
    arize-phoenix \
    openinference-instrumentation-langchain

# 复制应用代码
COPY . .

# 创建静态文件目录
RUN mkdir -p static/charts

# 暴露端口
# 8000: FastAPI 后端
# 7860: Gradio 前端
# 6006: Phoenix 监控
EXPOSE 8000 7860 6006

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# 默认启动后端服务
CMD ["python", "server_redis.py"]
