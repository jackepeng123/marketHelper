import pandas as pd
import os
from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agents.tools.chart_tool import generate_chart

class FileAnalysisInput(BaseModel):
    file_path: str = Field(..., description="上传文件的本地绝对路径")
    need_chart: bool = Field(default=False, description="是否需要根据表格数据画图")
    chart_type: str = Field(default=None, description="图表类型: 'bar'(默认), 'line', 'pie'")

@tool("analyze_sales_file", args_schema=FileAnalysisInput)
def analyze_sales_file(file_path: str, need_chart: bool = False, chart_type: str = None) -> dict:
    """
    读取并分析用户上传的 Excel/CSV 销售报表。
    支持自动生成图表。
    """
    try:
        # ... (前序逻辑不变)
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
            
        # 1. 读取文件
        if file_path.endswith(".xlsx") or file_path.endswith(".xls"):
            df = pd.read_excel(file_path)
        elif file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            return {"error": "Unsupported file format"}
            
        # 2. 列名清洗与筛选
        keep_columns = []
        for col in df.columns:
            c = str(col).strip()
            if "id" in c.lower() or "一级" in c or "二级" in c:
                continue
            keep_columns.append(col)
        df_clean = df[keep_columns].copy()
        
        # 3. 数据清洗 (数值转换)
        for col in df_clean.columns:
            if df_clean[col].dtype == 'object':
                try:
                    df_clean[col] = df_clean[col].astype(str).str.replace('¥', '').str.replace(',', '').str.replace('%', '')
                    df_clean[col] = pd.to_numeric(df_clean[col])
                    if "转化率" in str(col):
                        df_clean[col] = df_clean[col] / 100.0
                except:
                    pass
        
        # 4. 生成摘要
        summary = {
            "total_rows": len(df_clean),
            "columns": list(df_clean.columns)
        }
        sales_col = next((c for c in df_clean.columns if "成交金额" in str(c)), None)
        if sales_col:
            summary["total_revenue"] = float(df_clean[sales_col].sum())
            
        # 5. 图表生成逻辑
        chart_info = {}
        if need_chart:
            # 自动寻找适合画图的列
            # X轴：优先找“商品名称”或“日期”
            x_col = next((c for c in df_clean.columns if "名称" in str(c) or "date" in str(c).lower()), df_clean.columns[0])
            
            # Y轴：优先找“成交金额” -> “销量” -> “转化率” -> 任意数值列
            y_col = next((c for c in df_clean.columns if "成交金额" in str(c)), None)
            if not y_col:
                y_col = next((c for c in df_clean.columns if "成交" in str(c) or "销量" in str(c)), None)
            if not y_col:
                # 找第一个数值类型的列
                for c in df_clean.columns:
                    if pd.api.types.is_numeric_dtype(df_clean[c]):
                        y_col = c
                        break
            
            if x_col and y_col:
                # 排序取 Top 10 (防止柱状图太挤)
                df_sorted = df_clean.sort_values(by=y_col, ascending=False).head(10)
                
                final_chart_type = chart_type if chart_type else "bar"
                
                chart_res = generate_chart.invoke({
                    "chart_type": final_chart_type,
                    "title": f"Top 10 {y_col} by {x_col}",
                    "x_data": df_sorted[x_col].astype(str).tolist(),
                    "y_data": df_sorted[y_col].tolist(),
                    "x_label": x_col,
                    "y_label": y_col
                })
                if chart_res.get("status") == "success":
                    chart_info["chart_url"] = chart_res.get("image_url")
                    chart_info["chart_markdown"] = chart_res.get("markdown")

        markdown_table = df_clean.to_markdown(index=False)
        
        result = {
            "status": "success",
            "file_name": os.path.basename(file_path),
            "summary": summary,
            "data_content": markdown_table,
            "note": "已成功解析表格。",
        }
        result.update(chart_info)
        return result
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
