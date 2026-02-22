-- MarketHelper 数据库初始化脚本

-- 创建 Phoenix schema (如果不存在)
CREATE SCHEMA IF NOT EXISTS phoenix;

-- 设置默认搜索路径
ALTER DATABASE markethelper SET search_path TO public, phoenix;

-- 授予权限
GRANT ALL PRIVILEGES ON SCHEMA phoenix TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA phoenix TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA phoenix TO postgres;

-- 提示信息
DO $$
BEGIN
    RAISE NOTICE '✅ MarketHelper 数据库初始化完成';
    RAISE NOTICE '📊 Phoenix schema 已创建';
END $$;
