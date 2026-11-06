
import csv
import json
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)


BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL = "agnes-3.0-flash"

HUMAN_INTERVENTION_RULES = {
    "客户投诉": "是",
    "退换货": "是",
    "商务订单": "是",
    "物流问题": "否",
    "商品咨询": "否",
    "其他/无法识别": "待确认",
}

ALLOWED_CATEGORIES = [
    "客户投诉",
    "退换货",
    "商务订单",
    "物流问题",
    "商品咨询",
    "其他/无法识别",
]

CSV_FIELDS = [
    "邮件编号",
    "邮件内容",
    "邮件分类",
    "客户核心需求",
    "建议处理方式",
    "是否需要人工介入",
    "分析状态",
]


class MailAssistantGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AI 客户邮件智能助手")
        self.root.geometry("1100x760")
        self.root.minsize(900, 650)

        self.client = None
        self.selected_file = None
        self.emails = []
        self.results = []
        self.is_running = False

        self.create_interface()

    def create_interface(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        style.configure("Treeview", rowheight=27)
        style.configure(
            "Treeview.Heading",
            font=("Microsoft YaHei UI", 9, "bold")
        )

        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        title = ttk.Label(
            main,
            text="AI 客户邮件智能助手",
            font=("Microsoft YaHei UI", 20, "bold"),
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            main,
            text="导入客户邮件，使用 AI 提取需求并生成处理建议",
            font=("Microsoft YaHei UI", 10),
        )
        subtitle.pack(anchor="w", pady=(4, 14))

        # API 设置
        api_frame = ttk.LabelFrame(main, text="AI 接口设置", padding=10)
        api_frame.pack(fill="x", pady=(0, 10))

        api_row = ttk.Frame(api_frame)
        api_row.pack(fill="x")

        ttk.Label(api_row, text="Agnes API Key：").pack(side="left")

        self.api_key_var = tk.StringVar()

        self.api_key_entry = ttk.Entry(
            api_row,
            textvariable=self.api_key_var,
            show="*",
            width=55,
        )
        self.api_key_entry.pack(
            side="left",
            padx=(4, 8),
            fill="x",
            expand=True,
        )

        self.show_key_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            api_row,
            text="显示",
            variable=self.show_key_var,
            command=self.toggle_key,
        ).pack(side="left", padx=(0, 8))

        self.test_button = ttk.Button(
            api_row,
            text="测试连接",
            command=self.test_connection,
        )
        self.test_button.pack(side="left")

        ttk.Label(
            api_frame,
            text="API Key 仅在本次软件运行期间保存在内存中，关闭软件后不会保存。请勿把密钥分享给他人。",
            foreground="#666666",
        ).pack(anchor="w", pady=(7, 0))

        # 邮件文件
        file_frame = ttk.LabelFrame(main, text="客户邮件文件", padding=10)
        file_frame.pack(fill="x", pady=(0, 10))

        file_row = ttk.Frame(file_frame)
        file_row.pack(fill="x")

        self.choose_file_button = ttk.Button(
            file_row,
            text="选择邮件文件（TXT）",
            command=self.choose_file,
        )
        self.choose_file_button.pack(side="left")

        self.file_info_var = tk.StringVar(value="尚未选择文件")

        ttk.Label(
            file_row,
            textvariable=self.file_info_var,
        ).pack(side="left", padx=12, fill="x", expand=True)

        ttk.Label(
            file_frame,
            text="当前版本按 TXT 文件的每个非空行识别一封邮件。",
            foreground="#666666",
        ).pack(anchor="w", pady=(7, 0))

        # 操作按钮和进度条
        action_row = ttk.Frame(main)
        action_row.pack(fill="x", pady=(0, 10))

        self.start_button = ttk.Button(
            action_row,
            text="开始分析",
            command=self.start_analysis,
        )
        self.start_button.pack(side="left")

        self.retry_button = ttk.Button(
            action_row,
            text="重试失败邮件",
            command=self.retry_failed_emails,
            state="disabled",
        )
        self.retry_button.pack(side="left", padx=(8, 0))

        self.export_button = ttk.Button(
            action_row,
            text="导出 CSV",
            command=self.export_result,
            state="disabled",
        )
        self.export_button.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(
            action_row,
            mode="determinate",
            maximum=100,
        )
        self.progress.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(16, 0),
        )

        # 结果表格
        result_frame = ttk.LabelFrame(
            main,
            text="邮件分析结果",
            padding=8,
        )
        result_frame.pack(fill="both", expand=True)

        columns = ("number", "category", "human", "email", "status")

        self.tree = ttk.Treeview(
            result_frame,
            columns=columns,
            show="headings",
            height=11,
        )

        self.tree.heading("number", text="编号")
        self.tree.heading("category", text="邮件分类")
        self.tree.heading("human", text="人工介入")
        self.tree.heading("email", text="邮件内容")
        self.tree.heading("status", text="分析状态")

        self.tree.column(
            "number", width=55, anchor="center", stretch=False
        )
        self.tree.column(
            "category", width=120, anchor="center", stretch=False
        )
        self.tree.column(
            "human", width=90, anchor="center", stretch=False
        )
        self.tree.column("email", width=560, anchor="w")
        self.tree.column(
            "status", width=85, anchor="center", stretch=False
        )

        vertical_scroll = ttk.Scrollbar(
            result_frame,
            orient="vertical",
            command=self.tree.yview,
        )

        horizontal_scroll = ttk.Scrollbar(
            result_frame,
            orient="horizontal",
            command=self.tree.xview,
        )

        self.tree.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set,
        )

        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical_scroll.grid(row=0, column=1, sticky="ns")
        horizontal_scroll.grid(row=1, column=0, sticky="ew")

        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)

        self.tree.bind(
            "<<TreeviewSelect>>",
            self.show_selected_detail,
        )

        # 详细信息区域
        detail_frame = ttk.LabelFrame(
            main,
            text="选中邮件的详细分析",
            padding=8,
        )
        detail_frame.pack(fill="x", pady=(10, 0))

        self.detail_text = tk.Text(
            detail_frame,
            height=7,
            wrap="word",
            font=("Microsoft YaHei UI", 9),
            relief="solid",
            borderwidth=1,
        )

        self.detail_text.pack(fill="x", expand=True)

        self.detail_text.insert(
            "1.0",
            "分析完成后，点击上方表格中的邮件即可查看详细内容。",
        )
        self.detail_text.configure(state="disabled")

        self.status_var = tk.StringVar(value="就绪")

        status_bar = ttk.Label(
            main,
            textvariable=self.status_var,
            anchor="w",
            relief="sunken",
            padding=(6, 4),
        )
        status_bar.pack(fill="x", pady=(10, 0))

    def toggle_key(self):
        self.api_key_entry.configure(
            show="" if self.show_key_var.get() else "*"
        )

    def make_client(self, api_key):
        return OpenAI(
            api_key=api_key,
            base_url=BASE_URL,
            timeout=60,
            max_retries=0,
        )

    # ---------------- API 连接测试 ----------------

    def test_connection(self):
        api_key = self.api_key_var.get().strip()

        if not api_key:
            messagebox.showwarning(
                "缺少 API Key",
                "请先填写 Agnes API Key。",
            )
            return

        if self.is_running:
            return

        self.test_button.configure(state="disabled")
        self.status_var.set("正在测试 AI 连接...")

        threading.Thread(
            target=self.run_connection_test,
            args=(api_key,),
            daemon=True,
        ).start()

    def run_connection_test(self, api_key):
        try:
            client = self.make_client(api_key)

            client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": "请只回复：连接成功",
                    }
                ],
                temperature=0,
                max_tokens=30,
            )

            self.root.after(
                0,
                self.connection_succeeded,
                client,
            )

        except AuthenticationError:
            self.root.after(
                0,
                self.connection_failed,
                "API Key 无效，或当前 Key 没有调用该模型的权限。请检查 Agnes 平台中的密钥和权限。",
            )

        except (APIConnectionError, APITimeoutError):
            self.root.after(
                0,
                self.connection_failed,
                "连接 Agnes API 失败或请求超时。请检查网络后重试。",
            )

        except Exception as exc:
            self.root.after(
                0,
                self.connection_failed,
                f"连接测试失败：{exc}",
            )

    def connection_succeeded(self, client):
        self.client = client
        self.test_button.configure(state="normal")
        self.status_var.set("AI 已连接成功")
        messagebox.showinfo("测试成功", "AI 连接成功！")

    def connection_failed(self, error_message):
        self.test_button.configure(state="normal")
        self.status_var.set("AI 连接失败")
        messagebox.showerror("连接失败", error_message)

    # ---------------- 导入邮件 ----------------

    def choose_file(self):
        file_path = filedialog.askopenfilename(
            title="选择客户邮件 TXT 文件",
            filetypes=[
                ("文本文件", "*.txt"),
                ("所有文件", "*.*"),
            ],
        )

        if not file_path:
            return

        try:
            raw = Path(file_path).read_bytes()
            content = None

            for encoding in ("utf-8-sig", "utf-8", "gbk"):
                try:
                    content = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                raise ValueError("无法识别文件编码")

            emails = [
                line.strip()
                for line in content.splitlines()
                if line.strip()
            ]

            if not emails:
                messagebox.showwarning(
                    "文件为空",
                    "没有在文件中找到非空邮件内容。",
                )
                return

            self.selected_file = file_path
            self.emails = emails
            self.results = []

            self.clear_results_table()

            self.file_info_var.set(
                f"{Path(file_path).name}（{len(emails)} 封邮件）"
            )

            self.status_var.set(
                f"已导入 {len(emails)} 封邮件，可以开始分析。"
            )

            self.progress.configure(value=0)
            self.export_button.configure(state="disabled")
            self.retry_button.configure(state="disabled")

            self.set_detail(
                "文件已导入。点击“开始分析”后，分析结果会显示在这里。"
            )

        except Exception as exc:
            messagebox.showerror(
                "读取失败",
                f"无法读取邮件文件：{exc}",
            )

    def clear_results_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def set_detail(self, content):
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", content)
        self.detail_text.configure(state="disabled")

    # ---------------- 开始分析 ----------------

    def start_analysis(self):
        api_key = self.api_key_var.get().strip()

        if not api_key:
            messagebox.showwarning(
                "缺少 API Key",
                "请先填写 Agnes API Key。",
            )
            return

        if not self.emails:
            messagebox.showwarning(
                "尚未导入邮件",
                "请先选择包含客户邮件的 TXT 文件。",
            )
            return

        if self.is_running:
            return

        try:
            client = self.make_client(api_key)
        except Exception as exc:
            messagebox.showerror(
                "配置错误",
                f"无法创建 API 客户端：{exc}",
            )
            return

        self.client = client
        self.results = []

        self.clear_results_table()
        self.set_detail("正在分析邮件，请稍候……")

        self.progress.configure(
            maximum=len(self.emails),
            value=0,
        )

        self.is_running = True

        self.start_button.configure(state="disabled")
        self.retry_button.configure(state="disabled")
        self.choose_file_button.configure(state="disabled")
        self.test_button.configure(state="disabled")
        self.export_button.configure(state="disabled")

        self.status_var.set(
            f"准备分析 {len(self.emails)} 封邮件..."
        )

        threading.Thread(
            target=self.run_analysis,
            args=(client, list(self.emails)),
            daemon=True,
        ).start()

    def run_analysis(self, client, emails):
        for index, email in enumerate(emails, start=1):
            self.root.after(
                0,
                self.update_progress,
                index - 1,
                len(emails),
                index,
            )

            result = self.analyze_one_email(
                client,
                index,
                email,
            )

            self.root.after(
                0,
                self.add_result,
                result,
            )

            self.root.after(
                0,
                self.update_progress,
                index,
                len(emails),
                index,
            )

        self.root.after(0, self.analysis_finished)

    def update_progress(self, completed, total, current):
        self.progress.configure(value=completed)

        self.status_var.set(
            f"正在分析第 {current}/{total} 封邮件（已完成 {completed}/{total}）..."
        )

    # ---------------- 单封邮件 AI 分析 ----------------

    def analyze_one_email(self, client, number, email):
        prompt = f"""请阅读下面这封客户邮件，并提取结构化信息。

邮件内容：
{email}

请严格按照以下要求：
1. 邮件分类只能从以下类别中选择一个：客户投诉、退换货、商务订单、物流问题、商品咨询、其他/无法识别。
2. 客户核心需求：用简洁中文概括客户最主要想解决的问题。
3. 建议处理方式：提出具体、可执行的客服处理建议；不得编造订单状态、物流信息或公司政策。
4. 如果邮件信息不足，选择“其他/无法识别”，并在建议中说明需要补充什么信息。
5. 只输出一个合法 JSON 对象，不要输出 Markdown、代码围栏或额外解释。

JSON 格式必须是：
{{
  "邮件分类": "上述类别之一",
  "客户核心需求": "...",
  "建议处理方式": "..."
}}"""

        for attempt in range(1, 5):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个严谨的客户邮件分类与信息提取助手。只根据邮件原文判断，不得编造事实。",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    temperature=0,
                    max_tokens=600,
                )

                content = response.choices[0].message.content or ""
                data = self.parse_json_response(content)

                if not isinstance(data, dict):
                    raise ValueError("AI 返回内容不是 JSON 对象")

                category = self.get_field(
                    data,
                    ["邮件分类", "category", "classification"],
                )

                core_need = self.get_field(
                    data,
                    [
                        "客户核心需求",
                        "core_need",
                        "customer_need",
                        "customer_core_need",
                    ],
                )

                suggestion = self.get_field(
                    data,
                    [
                        "建议处理方式",
                        "suggestion",
                        "recommended_action",
                        "handling_suggestion",
                    ],
                )

                if not category or not core_need or not suggestion:
                    raise ValueError(
                        "AI 返回结果缺少邮件分类、核心需求或处理建议字段"
                    )

                category = self.normalize_category(str(category))
                human_intervention = HUMAN_INTERVENTION_RULES[category]

                return {
                    "邮件编号": number,
                    "邮件内容": email,
                    "邮件分类": category,
                    "客户核心需求": str(core_need).strip(),
                    "建议处理方式": str(suggestion).strip(),
                    "是否需要人工介入": human_intervention,
                    "分析状态": "成功",
                }

            except AuthenticationError:
                return self.failed_result(
                    number,
                    email,
                    "API Key 无效或没有调用权限。",
                )

            except (
                APIConnectionError,
                APITimeoutError,
                RateLimitError,
            ) as exc:

                if attempt <= 3:
                    time.sleep(2)
                    continue

                return self.failed_result(
                    number,
                    email,
                    f"连接失败，自动重试 3 次后仍未成功：{exc}",
                )

            except APIStatusError as exc:
                if exc.status_code >= 500 and attempt <= 3:
                    time.sleep(2)
                    continue

                return self.failed_result(
                    number,
                    email,
                    f"API 返回错误（状态码 {exc.status_code}）：{exc}",
                )

            except Exception as exc:
                return self.failed_result(
                    number,
                    email,
                    f"分析失败：{exc}",
                )

        return self.failed_result(
            number,
            email,
            "分析失败：超过最大重试次数。",
        )

    @staticmethod
    def get_field(data, names):
        for name in names:
            value = data.get(name)
            if value is not None and str(value).strip():
                return value
        return ""

    @staticmethod
    def normalize_category(category):
        category = category.strip().replace(" ", "")

        if category in (
            "其他",
            "无法识别",
            "其他问题",
            "其他/无法识别",
        ):
            return "其他/无法识别"

        if category in ALLOWED_CATEGORIES:
            return category

        return "其他/无法识别"

    @staticmethod
    def parse_json_response(content):
        text = content.strip()

        if text.startswith("```"):
            lines = text.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        try:
            return json.loads(text)

        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")

            if start >= 0 and end > start:
                return json.loads(text[start:end + 1])

            raise ValueError("AI 返回内容无法解析为 JSON")

    @staticmethod
    def failed_result(number, email, reason):
        return {
            "邮件编号": number,
            "邮件内容": email,
            "邮件分类": "分析失败",
            "客户核心需求": reason,
            "建议处理方式": "请检查 API Key、网络或接口状态后重新分析。",
            "是否需要人工介入": "待确认",
            "分析状态": "失败",
        }

    # ---------------- 更新结果表格 ----------------

    def add_result(self, result):
        self.results.append(result)

        self.tree.insert(
            "",
            "end",
            iid=str(result["邮件编号"]),
            values=(
                result["邮件编号"],
                result["邮件分类"],
                result["是否需要人工介入"],
                result["邮件内容"],
                result["分析状态"],
            ),
        )

        self.export_button.configure(state="normal")

    def replace_result(self, new_result):
        """用重试后的结果替换原来的结果，不重复添加邮件。"""

        number = new_result["邮件编号"]

        for index, old_result in enumerate(self.results):
            if old_result["邮件编号"] == number:
                self.results[index] = new_result
                break

        self.tree.item(
            str(number),
            values=(
                new_result["邮件编号"],
                new_result["邮件分类"],
                new_result["是否需要人工介入"],
                new_result["邮件内容"],
                new_result["分析状态"],
            ),
        )

        self.show_result_counts()

    def show_selected_detail(self, _event=None):
        selected = self.tree.selection()

        if not selected:
            return

        try:
            number = int(selected[0])

            result = next(
                item
                for item in self.results
                if item["邮件编号"] == number
            )

        except (ValueError, StopIteration):
            return

        detail = (
            f"邮件编号：{result['邮件编号']}\n"
            f"邮件分类：{result['邮件分类']}\n"
            f"客户核心需求：{result['客户核心需求']}\n"
            f"建议处理方式：{result['建议处理方式']}\n"
            f"是否需要人工介入：{result['是否需要人工介入']}\n"
            f"分析状态：{result['分析状态']}\n\n"
            f"邮件原文：\n{result['邮件内容']}"
        )

        self.set_detail(detail)

    # ---------------- 重试失败邮件：新增功能 ----------------

    def retry_failed_emails(self):
        if self.is_running:
            return

        failed_items = [
            item
            for item in self.results
            if item["分析状态"] == "失败"
        ]

        if not failed_items:
            messagebox.showinfo(
                "没有失败邮件",
                "当前没有需要重试的邮件。",
            )
            self.retry_button.configure(state="disabled")
            return

        api_key = self.api_key_var.get().strip()

        if not api_key:
            messagebox.showwarning(
                "缺少 API Key",
                "请先填写 Agnes API Key。",
            )
            return

        try:
            client = self.make_client(api_key)
        except Exception as exc:
            messagebox.showerror(
                "配置错误",
                f"无法创建 API 客户端：{exc}",
            )
            return

        self.client = client
        self.is_running = True

        self.start_button.configure(state="disabled")
        self.retry_button.configure(state="disabled")
        self.choose_file_button.configure(state="disabled")
        self.test_button.configure(state="disabled")
        self.export_button.configure(state="disabled")

        total = len(failed_items)

        self.progress.configure(
            maximum=total,
            value=0,
        )

        self.set_detail(
            f"正在重新分析 {total} 封失败邮件，请稍候……"
        )

        self.status_var.set(
            f"准备重试 {total} 封失败邮件..."
        )

        threading.Thread(
            target=self.run_retry,
            args=(client, failed_items),
            daemon=True,
        ).start()

    def run_retry(self, client, failed_items):
        """后台只重新分析失败邮件。"""

        total = len(failed_items)

        for index, old_result in enumerate(failed_items, start=1):
            number = old_result["邮件编号"]
            email = old_result["邮件内容"]

            self.root.after(
                0,
                self.update_progress,
                index - 1,
                total,
                index,
            )

            new_result = self.analyze_one_email(
                client,
                number,
                email,
            )

            self.root.after(
                0,
                self.replace_result,
                new_result,
            )

            self.root.after(
                0,
                self.update_progress,
                index,
                total,
                index,
            )

        self.root.after(0, self.retry_finished)

    def retry_finished(self):
        self.is_running = False

        self.start_button.configure(state="normal")
        self.choose_file_button.configure(state="normal")
        self.test_button.configure(state="normal")

        success_count = sum(
            1
            for item in self.results
            if item["分析状态"] == "成功"
        )

        failure_count = sum(
            1
            for item in self.results
            if item["分析状态"] == "失败"
        )

        self.status_var.set(
            f"重试完成：成功 {success_count} 封，失败 {failure_count} 封。"
        )

        self.export_button.configure(
            state="normal" if self.results else "disabled"
        )

        self.retry_button.configure(
            state="normal" if failure_count > 0 else "disabled"
        )

        messagebox.showinfo(
            "重试完成",
            f"失败邮件重试已完成！\n\n"
            f"当前总成功：{success_count} 封\n"
            f"当前总失败：{failure_count} 封\n\n"
            f"可以继续重试失败邮件，或导出 CSV。",
        )

    def show_result_counts(self):
        success_count = sum(
            1
            for item in self.results
            if item["分析状态"] == "成功"
        )

        failure_count = sum(
            1
            for item in self.results
            if item["分析状态"] == "失败"
        )

        self.status_var.set(
            f"当前结果：成功 {success_count} 封，失败 {failure_count} 封。"
        )

    # ---------------- 分析结束 ----------------

    def analysis_finished(self):
        self.is_running = False

        self.start_button.configure(state="normal")
        self.choose_file_button.configure(state="normal")
        self.test_button.configure(state="normal")

        success_count = sum(
            1
            for item in self.results
            if item["分析状态"] == "成功"
        )

        failure_count = sum(
            1
            for item in self.results
            if item["分析状态"] == "失败"
        )

        self.status_var.set(
            f"分析完成：成功 {success_count} 封，失败 {failure_count} 封。"
        )

        self.export_button.configure(
            state="normal" if self.results else "disabled"
        )

        self.retry_button.configure(
            state="normal" if failure_count > 0 else "disabled"
        )

        messagebox.showinfo(
            "分析完成",
            f"邮件分析已完成！\n"
            f"成功：{success_count} 封\n"
            f"失败：{failure_count} 封\n\n"
            f"如果有失败邮件，可以点击“重试失败邮件”。",
        )

    # ---------------- 导出 CSV ----------------

    def export_result(self):
        if not self.results:
            messagebox.showwarning(
                "没有结果",
                "目前没有可导出的分析结果。",
            )
            return

        save_path = filedialog.asksaveasfilename(
            title="保存邮件分析结果",
            defaultextension=".csv",
            initialfile="邮件分类结果.csv",
            filetypes=[("CSV 文件", "*.csv")],
        )

        if not save_path:
            return

        try:
            with open(
                save_path,
                "w",
                newline="",
                encoding="utf-8-sig",
            ) as file:

                writer = csv.DictWriter(
                    file,
                    fieldnames=CSV_FIELDS,
                )

                writer.writeheader()
                writer.writerows(self.results)

            self.status_var.set(
                f"CSV 已导出：{save_path}"
            )

            messagebox.showinfo(
                "导出成功",
                f"分析结果已保存到：\n{save_path}",
            )

        except Exception as exc:
            messagebox.showerror(
                "导出失败",
                f"无法导出 CSV：{exc}",
            )


if __name__ == "__main__":
    root = tk.Tk()
    app = MailAssistantGUI(root)
    root.mainloop()
