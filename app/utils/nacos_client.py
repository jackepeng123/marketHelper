import os
import nacos
import logging
import httpx
from urllib.parse import urlparse

# 配置日志
logger = logging.getLogger(__name__)

# Nacos 配置
NACOS_SERVER_ADDR = os.getenv("NACOS_SERVER_ADDR")
NACOS_NAMESPACE = os.getenv("NACOS_NAMESPACE", "") # Default to public/empty
NACOS_USERNAME = os.getenv("NACOS_USERNAME", "")
NACOS_PASSWORD = os.getenv("NACOS_PASSWORD", "")

class NacosConfig:
    _instance = None
    _client = None
    _cache = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NacosConfig, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        try:
            # 尝试初始化 SDK 客户端
            # 注意：如果 NACOS_NAMESPACE 为 "public"，SDK 可能需要空字符串
            namespace = NACOS_NAMESPACE
            if namespace == "public":
                namespace = ""
                
            self._client = nacos.NacosClient(
                server_addresses=NACOS_SERVER_ADDR,
                namespace=namespace,
                username=NACOS_USERNAME,
                password=NACOS_PASSWORD
            )
            logger.info(f"✅ Nacos SDK Client initialized at {NACOS_SERVER_ADDR}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to init Nacos SDK: {e}. Will fallback to HTTP API.")
            self._client = None

    def _get_config_via_http(self, data_id: str, group: str) -> str:
        """
        SDK 连接失败时的 HTTP API 兜底方案
        """
        try:
            # 构造 URL
            base_url = NACOS_SERVER_ADDR
            if not base_url.startswith("http"):
                base_url = f"http://{base_url}"
            
            url = f"{base_url}/nacos/v1/cs/configs"
            params = {
                "dataId": data_id,
                "group": group,
            }
            
            # 处理 Namespace (Tenant)
            # Nacos API: 如果是 public，不需要传 tenant 参数
            if NACOS_NAMESPACE and NACOS_NAMESPACE != "public":
                 params["tenant"] = NACOS_NAMESPACE
            
            # 简单的鉴权处理 (如果服务端开启)
            # 这里暂时忽略 accessToken 逻辑，因为报错显示未开启鉴权
            
            logger.info(f"Trying HTTP fallback for {data_id}...")
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    content = resp.text
                    if content:
                        logger.info(f"✅ HTTP Fallback success for {data_id}")
                        return content
                else:
                    logger.warning(f"HTTP Fallback failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"HTTP Fallback error: {e}")
        return None

    def get_config(self, data_id: str, group: str = "DEFAULT_GROUP") -> str:
        """
        获取配置。优先使用 SDK，失败则尝试 HTTP API，最后返回 None。
        """
        content = None
        
        # 1. 尝试 SDK
        if self._client:
            try:
                content = self._client.get_config(data_id, group)
            except Exception as e:
                logger.warning(f"SDK get_config failed: {e}")
        
        # 2. 如果 SDK 失败或未初始化，尝试 HTTP API
        if not content:
            content = self._get_config_via_http(data_id, group)
            
        if content:
            return content
            
        return None

# 默认提示词字典 (Fallback)
DEFAULT_PROMPTS = {
    "intent_classification_prompt": """You are an intent classifier. Analyze the user's query within the conversation context and return ONLY one of the following labels:
- "chat": For casual greetings, simple questions, or requests that don't need data analysis or external knowledge.
- "analysis": For requests related to marketing analysis, sales data, market trends, business advice, OR specific how-to questions/operational guides (knowledge retrieval).

Return ONLY the label.""",

    "available_tools_prompt": """可用工具：
- search_knowledge_base: 内部知识库检索（args: query）。
  * 用于回答名词解释、操作指南、平台规则等问题（如“抖音怎么上架”）。
- manus_market_research: 外部深度市场调研（args: query, depth）。
  * 用于查询市场趋势、竞品分析、行业报告等外部信息。
  * depth 可选: 'quick'。
- get_context_info: 环境上下文（天气、节假日、位置）（args: city, date, forecast_days）
- analyze_sales_file: Excel/CSV 表格文件分析（args: file_path, need_chart, chart_type）。
  * 仅在检测到用户上传了文件（提示中包含 'User uploaded a file at...'）时，或者用户明确要求分析当前上传的表格时调用此工具。
  * 不要因为历史消息里有文件就重复调用，除非用户当前意图是分析它。
  * 支持 need_chart 和 chart_type 参数。
- get_douyin_verify_records: 抖音验券历史查询（args: date）。
  * date: YYYY-MM-DD，默认为昨日。
- get_douyin_comments: 抖音商品评价查询（args: product_name）。
  * 用于查询特定商品的最新评价（最近90天）。
- get_douyin_sales_report: 抖音周期性销售报表（args: start_date, end_date, need_chart）。
  * 用于查询一段时间（如上周、上个月）的销售汇总和趋势。need_chart 默认为 True。
""",

    "tool_planner_system_prompt": """你是一个工具选择器。根据用户问题，从下列工具中选择需要调用的工具，并为每个工具给出参数。

要求：
1) 只输出严格 JSON，不要输出任何其它文字。
2) tools 是数组，每个元素包含 name 和 args。
3) 每个工具最多调用一次。
4) 如果用户明确排除某因素，不要选择对应工具。
5) 【重要 - 避免重复调用】：
   - 在决定调用工具前，必须仔细检查 CONTEXT (对话历史)。
   - 如果用户的问题是基于历史数据进行的追问（例如“为什么这么低？”、“有什么改进建议？”），且相关数据（如销售报表、评论）已经在历史对话中给出，则 **不要** 再次调用工具。返回空数组 [] 即可。
   - 只有当用户明确要求新的时间段、新的数据、或历史记录中缺少回答当前问题所需的数据时，才调用工具。
   - 如果历史记录中已经有图表，且用户没有要求画新图，不要重复生成图表。

JSON 格式示例：
{{"tools":[{{"name":"get_douyin_sales_report","args":{{"start_date":"2024-01-01", "end_date": "2024-01-07", "need_chart": true}}}},{{"name":"get_context_info","args":{{"city":"上海", "forecast_days": "15d"}}}}]}}
""",

    "final_response_system_prompt": """你是一名资深的零售营销专家。你将收到用户问题与工具返回的数据。
要求：
1) 只输出最终报告，不要输出思考过程，不要自问自答，不要反问用户。
2) 不要调用任何工具。
3) 输出为纯文本，不要使用 Markdown 标记（例如 ##、**、- 等），但图表链接除外。
4) 【重要】如果工具返回了图片 URL (chart_url)，必须在报告末尾以 Markdown 图片格式 `![Chart](url)` 独立一行展示。
   - 如果本轮对话没有调用工具，或者工具没有返回新的图片，**严禁** 复制历史消息中的旧图片链接。
   - 只有当 `chart_url` 出现在下方的“工具返回数据”中时，才允许展示。
5) 仅在回答针对过去销量的归因分析类问题时，如果你发现销售数据（如 get_douyin_sales_report 返回的数据）在某些具体日期有异常波动（如暴跌或暴涨），且目前缺乏那几天的天气数据，才请在报告结尾主动建议用户：“我注意到 [日期] 的销量有异常波动，是否需要我查询那几天的历史天气以进行归因分析？”。对于未来策划类问题，不要输出此建议。
6) 请注意，系统目前仅支持查询过去 10 天内的历史天气。不要建议用户查询超过 10 天前的历史数据。
""",

    "knowledge_query_rewrite_prompt": """你是一个专业的搜索引擎查询优化器。请将用户的原始查询改写为更清晰、更准确、更适合向量检索的形式。

【改写策略参考】
1. 口语化表达规范化：将“这个APP咋用”改写为“APP使用指南”
2. 冗长查询精炼化：去除冗余描述，提取核心实体和意图
3. 拼写错误纠正：自动修正明显的错别字
4. 术语缩写扩展：如将“HRBP”扩展或解释为“人力资源业务合作伙伴”
5. 符号描述语义化：将“倒三角符号”改写为具体的数学术语“nabla算子”或“梯度”

【要求】
- 保持原意，不要过度发散。
- 如果包含代词（如“它”），尝试基于常识还原指代对象。
- 只输出改写后的查询语句，不要输出任何解释、分析或引号。

用户原始查询: "{query}"
改写后的查询:
"""
}

def get_prompt(prompt_key: str) -> str:
    """
    获取 Prompt。优先从 Nacos 获取，失败则使用默认值。
    """
    nacos_config = NacosConfig()
    content = nacos_config.get_config(prompt_key)
    if content:
        return content
    return DEFAULT_PROMPTS.get(prompt_key, "")
