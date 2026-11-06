
import os
from openai import OpenAI

api_key = os.getenv("AGNES_API_KEY")

if not api_key:
    print("没有读取到 API Key，请检查环境变量。")
    input("按回车退出...")
    raise SystemExit

try:
    client = OpenAI(
        api_key=api_key,
        base_url="https://apihub.agnes-ai.com/v1"
    )

    print("正在连接 Agnes AI...")

    models = client.models.list()

    print("\n连接成功！当前可用模型：")

    for model in models.data:
        print("-", model.id)

except Exception as e:
    print("\n连接失败：")
    print(e)

input("\n按回车退出...")
