import os
import sys
# 将项目根目录添加到 sys.path，解决 'ModuleNotFoundError: No module named 'app'' 问题
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import glob
from typing import List
from langchain_community.document_loaders import PyMuPDFLoader, UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import create_engine, text
from dotenv import load_dotenv, find_dotenv
import json
import re
from app.core.llm import get_embeddings_model

# 加载环境变量
_ = load_dotenv(find_dotenv())
DB_URL = os.getenv("DATABASE_URL")
# 调小 Chunk Size 以适应千帆 Embedding-V1 的 Token 限制 (约384 Tokens)
CHUNK_SIZE = 350 
OVERLAP_SIZE = 30

def clean_text(text: str) -> str:
    """
    清洗文本：
    1. 去除 NUL (0x00) 字符 (PostgreSQL 不支持)
    2. 去除 Emoji
    3. 去除多余的空白字符和格式噪音
    """
    if not text:
        return ""
    
    # 1. 去除 NUL
    text = text.replace('\x00', '')
    
    # 2. 去除 Emoji
    # 扩大 Emoji 匹配范围
    emoji_pattern = re.compile(
        u"["
        u"\U0001F600-\U0001F64F"  # Emoticons
        u"\U0001F300-\U0001F5FF"  # Symbols & Pictographs
        u"\U0001F680-\U0001F6FF"  # Transport & Map Symbols
        u"\U0001F1E0-\U0001F1FF"  # Flags (iOS)
        u"]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub(r'', text)

    # 3. 格式化清洗
    # 删除字符串开头的空格
    text = re.sub(r'^\s+', '', text)
    # 将多个回车改为一个
    text = re.sub(r'\n+', '\n', text)
    # 删除句子中（以逗号结尾）的意外换行 (中文常见 PDF 解析问题)
    text = re.sub(r'，\n', '，', text)
    text = re.sub(r'。\n', '。', text) # 句号也同理
    
    # 4. 替换连续空白为单个空格 (保留换行符)
    # text = re.sub(r'[ \t]+', ' ', text) 
    
    return text

def remove_urls(text: str) -> str:
    '''
    数据脱敏：去除网址和邮箱
    '''
    # 匹配 http/https 网址
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    text = re.sub(url_pattern, '', text)

    # 匹配邮箱
    email_pattern = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}'
    text = re.sub(email_pattern, '', text)
    return text

def load_documents(source_dir: str) -> List[any]:
    """
    读取指定目录下的所有 .pdf 和 .md 文件
    """
    docs = []
    
    # 1. 读取 PDF
    pdf_files = glob.glob(os.path.join(source_dir, "**/*.pdf"), recursive=True)
    for f in pdf_files:
        try:
            print(f"📖 Loading PDF: {f}")
            loader = PyMuPDFLoader(f)
            pdf_pages = loader.load()
            header_pattern = r"→_→\s+欢迎去各大电商平台选购纸质版南瓜书《机器学习公式详解》\s+←_←"
            
            # 清洗逻辑
            for page in pdf_pages:
                text = page.page_content
                # 1. 去除特定的广告页眉
                text = re.sub(header_pattern, "", text)
                # 2. 基础清洗 (NUL, Emoji, 格式)
                text = clean_text(text)
                # 3. 数据脱敏 (去除网址和邮箱)
                text = remove_urls(text)
                page.page_content = text

            docs.extend(pdf_pages)
            print(f"   -> Loaded {len(pdf_pages)} pages.")
        except Exception as e:
            print(f"⚠️ Failed to load {f}: {e}")

    # 2. 读取 MD
    md_files = glob.glob(os.path.join(source_dir, "**/*.md"), recursive=True)
    for f in md_files:
        try:
            print(f"📖 Loading Markdown: {f}")
            # 使用 UnstructuredMarkdownLoader 以获得更好的解析
            loader = UnstructuredMarkdownLoader(f, encoding="utf-8") 
            md_pages = loader.load()
            
            # 清洗
            for page in md_pages:
                 page.page_content = clean_text(page.page_content)
            
            docs.extend(md_pages)
            print(f"   -> Loaded {len(md_pages)} sections.")
        except Exception as e:
            print(f"⚠️ Failed to load {f}: {e}")
            
    print(f"📂 Total documents loaded: {len(docs)}")
    return docs

def ingest_knowledge(source_dir: str = "knowledge/knowledge_db"):
    """
    核心流程：
    1. 读取文件 (PDF/MD)
    2. 切分文本 (Chunking)
    3. 计算向量 (Embedding)
    4. 存入 Postgres (pgvector)
    """
    if not DB_URL:
        print("❌ Error: DATABASE_URL not set.")
        return

    # 1. 加载
    print(f"🚀 Starting ingestion from: {source_dir}")
    raw_docs = load_documents(source_dir)
    if not raw_docs:
        print("⚠️ No documents found. Please add .pdf or .md files to knowledge/knowledge_db/")
        return

    # 2. 切分
    print("✂️ Splitting documents...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,      
        chunk_overlap=OVERLAP_SIZE,    
        separators=["\n\n", "\n", "。", "！", "？", " ", ""]
    )
    chunks = text_splitter.split_documents(raw_docs)
    print(f"🧩 Generated {len(chunks)} chunks.")

    # 3. Embedding 模型
    print("🧠 Initializing Embedding Model (Qianfan Embedding-V1)...")
    try:
        embeddings_model = get_embeddings_model()
    except Exception as e:
        print(f"❌ Failed to init embedding model: {e}")
        return

    # 4. 存入数据库
    engine = create_engine(DB_URL)
    
    success_count = 0
    
    print("💾 Inserting into PostgreSQL...")
    with engine.connect() as conn:
        for i, chunk in enumerate(chunks):
            content = chunk.page_content
            metadata = chunk.metadata
            source = metadata.get("source", "")
            
            try:
                # 计算向量
                vector = embeddings_model.embed_query(content)
                
                # ⚠️ 注意：千帆 Embedding-V1 维度通常是 384，而我们之前数据库初始化默认为 vector(1536)
                # 如果插入失败，可能需要修改数据库列定义。
                # 检查维度：
                if i == 0:
                    dim = len(vector)
                    print(f"ℹ️ Embedding Dimension: {dim}")
                    if dim != 1536:
                        print(f"⚠️ Warning: Database expects 1536 dims, but model returns {dim}.")
                        print("   Automatic fix: Altering table column to vector({dim})...")
                        conn.execute(text(f"ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector({dim});"))
                        conn.commit()
                
                # 插入 SQL
                sql = text("""
                    INSERT INTO knowledge_chunks (content, embedding, metadata, source)
                    VALUES (:content, :embedding, :metadata, :source)
                """)
                
                conn.execute(sql, {
                    "content": content,
                    "embedding": vector,
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                    "source": source
                })
                
                if (i + 1) % 10 == 0:
                    print(f"   ... Processed {i + 1}/{len(chunks)} chunks")
                    
            except Exception as e:
                print(f"❌ Error inserting chunk {i}: {e}")
                continue
                
            success_count += 1
            
        conn.commit()

    print(f"✅ Ingestion Complete! Inserted {success_count} chunks into 'knowledge_chunks'.")

if __name__ == "__main__":
    # 确保目录存在
    os.makedirs("knowledge/knowledge_db", exist_ok=True)
    ingest_knowledge()
