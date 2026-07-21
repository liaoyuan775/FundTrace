import base64
import json
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings
from ..models import TransactionRecord


class Capability(BaseModel):
    reachable: bool
    text_json: bool = False
    vision: bool = False
    model: str = ""
    message: str = ""


class ExtractedTransaction(BaseModel):
    """银行流水交易记录"""
    model_config = ConfigDict(extra="forbid")

    transaction_time: datetime = Field(description="交易时间，格式 YYYY-MM-DD HH:MM:SS")
    serial_number: str = Field(description="交易流水号/订单号")
    payer_account: str = Field(description="付款方账号")
    payer_name: str = Field(description="付款方户名")
    payer_institution: str = Field(description="付款方所属机构，如：支付宝、微信、工商银行")
    payer_bank: str = Field(description="付款方开户行名称")
    payee_account: str = Field(description="收款方账号")
    payee_name: str = Field(description="收款方户名")
    payee_institution: str = Field(description="收款方所属机构")
    payee_bank: str = Field(description="收款方开户行名称")
    debit_credit: str = Field(description="借贷方向：借=支出/扣款，贷=收入/入账")
    currency: str = Field(description="币种，如 CNY、USD，未注明填 CNY")
    amount: float = Field(gt=0, description="交易金额，正数")
    balance_after: float | None = Field(description="交易后余额，无法确定填 null")
    channel: str = Field(description="交易渠道，如：柜面、网银、手机银行、POS、ATM")
    summary: str = Field(description="摘要/用途/备注，原文照抄")
    region: str = Field(description="交易发生地区")
    transaction_type: str = Field(description="交易类型，如：转账、消费、取现、汇款")


class TransactionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transactions: list[ExtractedTransaction]


def transaction_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "fundtrace_transactions",
            "strict": True,
            "schema": TransactionBatch.model_json_schema(),
        },
    }


class QwenAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._state = threading.local()
        self.last_schema_mode = "strict"
        self.last_warning = ""

    @property
    def last_schema_mode(self):
        return getattr(self._state, "schema_mode", "strict")

    @last_schema_mode.setter
    def last_schema_mode(self, value):
        self._state.schema_mode = value

    @property
    def last_warning(self):
        return getattr(self._state, "warning", "")

    @last_warning.setter
    def last_warning(self, value):
        self._state.warning = value

    @property
    def enabled(self):
        return bool(
            self.settings.qwen_base_url
            and self.settings.qwen_api_key
            and "LOCAL_SECRET_CONFIGURED" not in self.settings.qwen_api_key
        )

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.settings.qwen_api_key}",
            "Content-Type": "application/json",
        }

    @lru_cache(maxsize=1)
    def probe(self) -> Capability:
        if not self.enabled:
            return Capability(
                reachable=False,
                model=self.settings.qwen_model,
                message="未配置可用的内网模型密钥",
            )
        try:
            response = httpx.get(
                f"{self.settings.qwen_base_url.rstrip('/')}/models",
                headers=self._headers(),
                timeout=3,
                trust_env=False,
            )
            response.raise_for_status()
            return Capability(
                reachable=True,
                text_json=True,
                model=self.settings.qwen_model,
                message="文本JSON接口可用；图片能力将在首次图片解析时探测",
            )
        except Exception as exc:
            return Capability(
                reachable=False,
                model=self.settings.qwen_model,
                message=type(exc).__name__,
            )

    def normalize(
        self, text: str, image_path: Path | None = None
    ) -> list[TransactionRecord]:
        if not self.enabled:
            raise RuntimeError("内网模型未配置")
        contract = json.dumps(
            TransactionBatch.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        prompt = f"""将银行或支付流水记录转换为标准交易数组。

<重要原则>
- 材料中可能只有部分字段信息，无法确定的字段一律填空字符串 ""，不要编造
- 余额无法确定填 null，不要从其他字段推算
- 只提取你看到的，不要补充缺失字段
</重要原则>

<字段说明>
transaction_time:  交易时间，格式 YYYY-MM-DD HH:MM:SS。注意图片中可能是"2024年1月15日 14:30"这类中文格式，需转换为 ISO 格式
serial_number:     交易流水号/订单号，原文照抄，不要修改格式
payer_account:     付款方账号，去除空格和特殊字符
payer_name:        付款方户名
payer_institution: 付款方所属机构（如：支付宝、微信、工商银行）
payer_bank:        付款方开户行名称
payee_account:     收款方账号，去除空格和特殊字符
payee_name:        收款方户名
payee_institution: 收款方所属机构
payee_bank:        收款方开户行名称
debit_credit:      借贷方向："借"=支出/扣款，"贷"=收入/入账。不确定时填空
currency:          币种，如 CNY、USD。材料未注明填 CNY
amount:            交易金额，正数。如果是负数或括弧表示支出，取其绝对值
balance_after:     交易后余额。材料中无余额信息则填 null
channel:           交易渠道（如：柜面、网银、手机银行、POS、ATM、跨行）
summary:           摘要/用途/备注，原文照抄
region:            交易发生地区
transaction_type:  交易类型（如：转账、消费、取现、汇款、收款、还款）。不确定填空
</字段说明>

<输出要求>
- 每笔交易输出一条记录，不要合并或汇总
- 无论材料是图片、表格还是文本，提取规则相同
- 严格按以下 JSON Schema 输出，不要添加 Schema 中不存在的字段
</输出要求>

{contract}"""
        content = []
        if image_path:
            encoded = base64.b64encode(image_path.read_bytes()).decode()
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{image_path.suffix.lstrip('.')};base64,{encoded}"
                    },
                },
            ]
        else:
            content = f"{prompt}\n原始内容：\n{text[:50000]}"
        payload = {
            "model": self.settings.qwen_model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 4096,
            "response_format": transaction_response_format(),
            "chat_template_kwargs": {"enable_thinking": False},
        }
        self.last_schema_mode = "strict"
        self.last_warning = ""
        self._state.retry_warnings = []
        last = None
        for attempt in range(3):
            try:
                response = httpx.post(
                    f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=90,
                    trust_env=False,
                )
                response.raise_for_status()
                raw = response.json()["choices"][0]["message"]["content"]
                data = json.loads(raw) if isinstance(raw, str) else raw
                batch = TransactionBatch.model_validate(data)
                prompt_version = (
                    "v2-strict" if self.last_schema_mode == "strict" else "v2-json-object"
                )
                return [
                    TransactionRecord.model_validate(
                        {
                            **item.model_dump(),
                            "parser_name": "qwen",
                            "model_id": self.settings.qwen_model,
                            "prompt_version": prompt_version,
                            "review_status": "pending",
                            "provenance": "model_suggested",
                        }
                    )
                    for item in batch.transactions
                ]
            except httpx.HTTPStatusError as exc:
                last = exc
                msg = f"第{attempt+1}次重试: HTTP {exc.response.status_code}"
                self._state.retry_warnings.append(msg)
                if attempt == 0 and exc.response.status_code in {400, 404, 415, 422}:
                    payload["response_format"] = {"type": "json_object"}
                    self.last_schema_mode = "json_object"
                    self.last_warning = (
                        f"服务端不支持严格JSON Schema，已降级: HTTP {exc.response.status_code}"
                    )
                    continue
            except Exception as exc:
                last = exc
                self._state.retry_warnings.append(
                    f"第{attempt+1}次重试: {type(exc).__name__}"
                )
        self.last_warning = "; ".join(self._state.retry_warnings[-3:])
        raise RuntimeError(f"模型解析失败: {type(last).__name__}")

    @property
    def retry_warnings(self) -> list[str]:
        return getattr(self._state, "retry_warnings", [])
