
import os
import sys
import csv
import time
import traceback
from pathlib import Path
from openai import OpenAI, APIConnectionError, APITimeoutError


# ==============================
# 1. 确定项目运行目录
# ==============================

if getattr(sys, "frozen", False):
    folder = Path(sys.executable).parent
else:
    folder = Path(__file__).parent

input_file = folder / "客户邮件.txt"
output_file = folder / "邮件分类结果.csv"


# ==============================
# 2. API 配置
# ==============================

api_key = os.getenv("AGNES_API_KEY")

if not api_key:
    print("\n没有读取到 API Key！")
    print("请检查 Windows 环境变量 AGNES_API_KEY 是否设置。")
    input("\n按回车退出...")
    raise SystemExit

client = OpenAI(
    api_key=api_key,
    base_url="https://apihub.agnes-ai.com/v1",
    timeout=60,
    max_retries=0
)

MODEL = "agnes-3.0-flash"


# ==============================
# 3. AI 邮件分析（自动重试）
# ==============================

def analyze_email(content):

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):

        try:

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": """
你是一名专业的电商客服邮件助手。

阅读客户邮件，提取以下三项信息：
1. 邮件分类
2. 客户核心需求
3. 建议处理方式

邮件分类只能选择：
客户投诉、退换货、物流问题、商务订单、商品咨询、其他。

严格按照下面格式返回，每项单独一行：

邮件分类：...
客户核心需求：...
建议处理方式：...

不要编造邮件中没有的信息。
"""
                    },
                    {
                        "role": "user",
                        "content": content
                    }
                ],
                temperature=0
            )

            result = response.choices[0].message.content or ""

            data = {
                "邮件分类": "其他",
                "客户核心需求": "未提取",
                "建议处理方式": "未提供"
            }

            for line in result.splitlines():

                line = line.strip()

                if "：" in line:
                    key, value = line.split("：", 1)

                elif ":" in line:
                    key, value = line.split(":", 1)

                else:
                    continue

                key = key.strip()
                value = value.strip()

                if key in data:
                    data[key] = value

            return data

        except (APIConnectionError, APITimeoutError) as e:

            print(f"连接异常，第 {attempt} 次尝试失败：{e}")

            if attempt < max_attempts:
                print("等待 2 秒后自动重试...")
                time.sleep(2)
            else:
                print("已经达到最大重试次数。")
                raise


# ==============================
# 4. 人工介入规则
# ==============================

def determine_human_intervention(category):

    rules = {
        "客户投诉": "是",
        "退换货": "是",
        "商务订单": "是",
        "物流问题": "否",
        "商品咨询": "否",
        "其他": "待确认"
    }

    return rules.get(category, "待确认")


# ==============================
# 5. 主程序
# ==============================

def main():

    print("=" * 45)
    print("          AI 客户邮件智能助手")
    print("=" * 45)

    print("\n正在读取客户邮件...")

    if not input_file.exists():
        print("\n错误：找不到客户邮件.txt")
        print("请将客户邮件.txt放在程序同一个文件夹中。")
        return

    with open(input_file, "r", encoding="utf-8-sig") as file:

        emails = [
            line.strip()
            for line in file
            if line.strip()
        ]

    if not emails:
        print("\n错误：客户邮件.txt 是空的。")
        return

    print(f"成功读取 {len(emails)} 封邮件。")

    results = []

    # ==============================
    # 6. 逐封分析
    # ==============================

    for number, content in enumerate(emails, start=1):

        print(f"\n正在分析第 {number} 封邮件...")
        print("-" * 45)

        try:

            data = analyze_email(content)

            human_needed = determine_human_intervention(
                data["邮件分类"]
            )

            print("邮件分类：", data["邮件分类"])
            print("客户核心需求：", data["客户核心需求"])
            print("建议处理方式：", data["建议处理方式"])
            print("是否需要人工介入：", human_needed)

            results.append({
                "邮件编号": number,
                "邮件内容": content,
                **data,
                "是否需要人工介入": human_needed
            })

        except Exception as e:

            print("本封邮件分析失败：", e)

            results.append({
                "邮件编号": number,
                "邮件内容": content,
                "邮件分类": "分析失败",
                "客户核心需求": "",
                "建议处理方式": "",
                "是否需要人工介入": "待确认"
            })

    # ==============================
    # 7. 导出 CSV
    # ==============================

    columns = [
        "邮件编号",
        "邮件内容",
        "邮件分类",
        "客户核心需求",
        "建议处理方式",
        "是否需要人工介入"
    ]

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=columns
        )

        writer.writeheader()
        writer.writerows(results)

    success_count = sum(
        1 for r in results
        if r["邮件分类"] != "分析失败"
    )

    failed_count = len(results) - success_count

    print("\n" + "=" * 45)
    print("AI 邮件分析完成！")
    print(f"共处理 {len(emails)} 封邮件。")
    print(f"成功分析 {success_count} 封。")
    print(f"分析失败 {failed_count} 封。")
    print(f"\n结果文件：{output_file}")
    print("=" * 45)


# ==============================
# 8. 程序入口
# ==============================

if __name__ == "__main__":

    try:
        main()

    except Exception:
        print("\n程序发生错误：")
        traceback.print_exc()

    input("\n按回车键退出...")
