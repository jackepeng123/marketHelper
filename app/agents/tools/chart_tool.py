import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import os
import uuid
import platform
from typing import List, Literal, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# -------------------------------------------------------------------------
# 配置字体以支持中文
# -------------------------------------------------------------------------
system = platform.system()
if system == "Darwin":  # macOS
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC']
elif system == "Windows":
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
else:  # Linux
    plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'Droid Sans Fallback']
    
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# -------------------------------------------------------------------------
# 工具输入定义
# -------------------------------------------------------------------------
class ChartInput(BaseModel):
    chart_type: Literal["line", "bar", "pie"] = Field(..., description="图表类型：line(折线图), bar(柱状图), pie(饼图)")
    title: str = Field(..., description="图表标题")
    x_data: List[str] = Field(default=[], description="X轴数据标签（如日期、类别）。对于饼图，这是类别名称。")
    y_data: List[float] = Field(..., description="Y轴数值数据。")
    x_label: Optional[str] = Field(default="", description="X轴名称")
    y_label: Optional[str] = Field(default="", description="Y轴名称")

# -------------------------------------------------------------------------
# 主工具定义
# -------------------------------------------------------------------------
@tool("generate_chart", args_schema=ChartInput)
def generate_chart(chart_type: str, title: str, x_data: List[str], y_data: List[float], x_label: str = "", y_label: str = "") -> dict:
    """
    根据数据生成可视化图表（折线图、柱状图或饼图）。
    """
    try:
        plt.figure(figsize=(10, 6))
        ax = plt.gca() # 获取当前坐标轴
        
        # 颜色配置
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
        
        # 优化 x_data 格式 (简化日期 2026-02-03 -> 02-03)
        formatted_x = []
        for x in x_data:
            if isinstance(x, str) and "-" in x and len(x) >= 10:
                try:
                    # 尝试保留 MM-DD
                    parts = x.split("-")
                    if len(parts) == 3: # YYYY-MM-DD
                        formatted_x.append(f"{parts[1]}-{parts[2]}")
                    else:
                        formatted_x.append(x)
                except:
                    formatted_x.append(x)
            else:
                # 如果字符串过长，截断并加省略号 (仅针对非日期类型)
                s = str(x)
                if len(s) > 8:
                    formatted_x.append(s[:8] + "...")
                else:
                    formatted_x.append(s)
        
        if chart_type == "line":
            plt.plot(formatted_x, y_data, marker='o', linestyle='-', color=colors[0], linewidth=2)
            for a, b in zip(formatted_x, y_data):
                plt.text(a, b, f'{int(b)}', ha='center', va='bottom', fontsize=12) # 标注字号略小一点以免重叠
            plt.grid(True, linestyle='--', alpha=0.7)
            
        elif chart_type == "bar":
            bars = plt.bar(formatted_x, y_data, color=colors[0], alpha=0.8)
            # 柱状图数值标注
            ax.bar_label(bars, fmt='%d', fontsize=12)
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
        elif chart_type == "pie":
            plt.pie(y_data, labels=formatted_x, autopct='%1.1f%%', startangle=90, colors=colors, textprops={'fontsize': 14})
            plt.axis('equal')

        # 标题和标签设置 (16pt)
        plt.title(title, fontsize=20, pad=20)
        if x_label:
            plt.xlabel(x_label, fontsize=16)
        if y_label:
            plt.ylabel(y_label, fontsize=16)
            
        # 刻度设置
        if chart_type != "pie":
            # 修正：设置 ha='right' 以解决旋转后的对齐偏移问题
            plt.xticks(fontsize=14, rotation=45, ha='right') 
            plt.yticks(fontsize=14)
            # Y轴强制整数
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            
        plt.tight_layout()
        
        # 保存图片
        filename = f"chart_{uuid.uuid4().hex[:8]}.png"
        save_dir = "static/charts"
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        filepath = os.path.join(save_dir, filename)
        plt.savefig(filepath, dpi=100)
        plt.close()
        
        # 返回相对路径
        img_url = f"/static/charts/{filename}"
        return {
            "status": "success",
            "image_url": img_url,
            "markdown": f"![{title}]({img_url})"
        }
        
    except Exception as e:
        print(f"Chart Generation Error: {e}")
        return {"status": "error", "message": str(e)}
