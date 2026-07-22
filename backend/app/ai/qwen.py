import base64
import json
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings
from ..models import TransactionRecord
from .prompts.financial_events import (
    build_classification_prompt,
    build_extraction_prompt,
    build_validation_retry_prompt,
)


class Capability(BaseModel):
    reachable: bool
    text_json: bool = False
    vision: bool = False
    vision_attempted: bool = False
    model: str = ""
    message: str = ""


class ExtractedTransaction(BaseModel):
    """银行流水交易记录"""
    model_config = ConfigDict(extra="forbid")

    transaction_time: datetime | None = Field(description="交易时间，无法确认填 null")
    serial_number: str | None = Field(description="交易流水号/订单号")
    payer_account: str | None = Field(description="付款方账号，未看到填 null")
    payer_name: str | None = Field(description="付款方户名，未看到填 null")
    payer_institution: str | None = Field(description="付款方所属机构")
    payer_bank: str | None = Field(description="付款方开户行名称")
    payee_account: str | None = Field(description="收款方账号，未看到填 null")
    payee_name: str | None = Field(description="收款方户名，未看到填 null")
    payee_institution: str | None = Field(description="收款方所属机构")
    payee_bank: str | None = Field(description="收款方开户行名称")
    debit_credit: str | None = Field(description="借贷方向：借=支出/扣款，贷=收入/入账")
    currency: str | None = Field(description="币种，如 CNY、USD")
    amount: float = Field(gt=0, description="交易金额，正数")
    balance_after: float | None = Field(description="交易后余额，无法确定填 null")
    channel: str | None = Field(description="交易渠道，如：柜面、网银、手机银行、POS、ATM")
    summary: str | None = Field(description="摘要/用途/备注，原文照抄")
    region: str | None = Field(description="交易发生地区")
    transaction_type: str | None = Field(description="交易类型，如：转账、消费、取现、汇款")
    event_status: Literal[
        "success", "pending", "failed", "returned", "cancelled", "reversed", "unknown"
    ] | None = Field(description="交易状态，无法确认填 null")
    order_id: str | None = Field(description="支付订单号")
    batch_id: str | None = Field(description="清算批次号")
    merchant_id: str | None = Field(description="商户号")
    merchant_name: str | None = Field(description="商户名称")
    terminal_id: str | None = Field(description="POS或ATM终端号")
    authorization_code: str | None = Field(description="授权码")
    fee: float | None = Field(ge=0, description="手续费")
    related_transaction_id: str | None = Field(description="关联原交易号")
    relation_type: Literal[
        "same_business_event", "settles", "refunds", "reverses",
        "charges_fee", "corroborates",
    ] | None = Field(description="与原交易的关系")


class TransactionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transactions: list[ExtractedTransaction]


class MaterialClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str
    record_type: Literal[
        "bank_transfer", "payment_order", "card_payment", "cash_withdrawal",
        "cash_deposit", "refund", "reversal", "settlement",
        "balance_snapshot", "unknown",
    ]
    confidence: float = Field(ge=0, le=1)


def transaction_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "fundtrace_transactions",
            "strict": True,
            "schema": TransactionBatch.model_json_schema(),
        },
    }


def classification_response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "fundtrace_material_classification",
            "strict": True,
            "schema": MaterialClassification.model_json_schema(),
        },
    }


class QwenAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._state = threading.local()
        self._vision_lock = threading.Lock()
        self._request_slots = threading.BoundedSemaphore(settings.qwen_domain_concurrency)
        self._vision_attempted = False
        self._vision_succeeded = False
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

    @property
    def vision_attempted(self) -> bool:
        with self._vision_lock:
            return self._vision_attempted

    @property
    def vision_succeeded(self) -> bool:
        with self._vision_lock:
            return self._vision_succeeded

    def _mark_vision(self, *, succeeded: bool = False) -> None:
        with self._vision_lock:
            self._vision_attempted = True
            self._vision_succeeded = self._vision_succeeded or succeeded

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.settings.qwen_api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, url: str, *, payload: dict, timeout: float):
        with self._request_slots:
            return httpx.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=timeout,
                trust_env=False,
            )

    @staticmethod
    def _typed_record_updates(item: ExtractedTransaction, record_type: str) -> dict:
        updates = {"record_type": record_type}
        if record_type == "card_payment" and item.merchant_id and not item.payee_account:
            updates.update(
                payee_entity_type="merchant",
                payee_endpoint_id=f"MERCHANT:{item.merchant_id}",
            )
        elif record_type in {"cash_withdrawal", "cash_deposit"} and item.terminal_id:
            side = "payee" if record_type == "cash_withdrawal" else "payer"
            updates[f"{side}_entity_type"] = "atm"
            updates[f"{side}_endpoint_id"] = f"ATM:{item.terminal_id}"
        return updates

    @lru_cache(maxsize=1)
    def _probe_text_capability(self) -> Capability:
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

    def probe(self) -> Capability:
        capability = self._probe_text_capability()
        vision_attempted = self.vision_attempted
        vision_succeeded = self.vision_succeeded
        message = capability.message
        if capability.reachable and vision_succeeded:
            message = "文本JSON接口和图片能力可用"
        elif capability.reachable and vision_attempted:
            message = "文本JSON接口可用；图片调用已尝试但尚未成功"
        return capability.model_copy(update={
            "vision": vision_succeeded,
            "vision_attempted": vision_attempted,
            "message": message,
        })

    def classify(
        self, text: str, image_path: Path | None = None
    ) -> MaterialClassification:
        if not self.enabled:
            raise RuntimeError("内网模型未配置")
        prompt = build_classification_prompt(text)
        content: str | list[dict] = prompt
        if image_path:
            self._mark_vision()
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
        payload = {
                    "model": self.settings.qwen_model,
                    "messages": [{"role": "user", "content": content}],
                    "temperature": 0,
                    "max_tokens": 256,
                    "response_format": classification_response_format(),
                    "chat_template_kwargs": {"enable_thinking": False},
                }
        warnings = []
        last = None
        for attempt in range(1 + self.settings.qwen_schema_retries):
            try:
                response = self._post(
                    f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",
                    payload=payload,
                    timeout=90,
                )
                response.raise_for_status()
                raw = response.json()["choices"][0]["message"]["content"]
                result = MaterialClassification.model_validate(json.loads(raw) if isinstance(raw, str) else raw)
                if image_path:
                    self._mark_vision(succeeded=True)
                return result
            except httpx.HTTPStatusError as exc:
                last = exc
                status = exc.response.status_code
                warnings.append(f"分类第{attempt + 1}次: HTTP {status}")
                if attempt + 1 >= 1 + self.settings.qwen_schema_retries or not (status == 408 or status == 429 or status >= 500):
                    break
            except httpx.HTTPError as exc:
                last = exc
                warnings.append(f"分类第{attempt + 1}次: {type(exc).__name__}")
            except Exception as exc:
                last = exc
                warnings.append(f"分类第{attempt + 1}次: {type(exc).__name__}")
                if attempt + 1 < 1 + self.settings.qwen_schema_retries:
                    correction = build_validation_retry_prompt(str(exc))
                    message_content = payload["messages"][0]["content"]
                    if isinstance(message_content, list):
                        message_content.append({"type": "text", "text": correction})
                    else:
                        payload["messages"][0]["content"] = message_content + "\n" + correction
        self.last_warning = "; ".join(warnings)
        raise RuntimeError(f"材料分类失败: {type(last).__name__}") from last

    def normalize(
        self,
        text: str,
        image_path: Path | None = None,
        record_type: str = "bank_transfer",
    ) -> list[TransactionRecord]:
        if not self.enabled:
            raise RuntimeError("内网模型未配置")
        prompt = build_extraction_prompt(record_type, TransactionBatch.model_json_schema())
        content = []
        if image_path:
            self._mark_vision()
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
        attempts = 1 + self.settings.qwen_schema_retries
        for attempt in range(attempts):
            try:
                response = self._post(
                    f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",
                    payload=payload,
                    timeout=90,
                )
                response.raise_for_status()
                raw = response.json()["choices"][0]["message"]["content"]
                data = json.loads(raw) if isinstance(raw, str) else raw
                batch = TransactionBatch.model_validate(data)
                prompt_version = "v2-strict"
                records = [
                    TransactionRecord.model_validate(
                        {
                            **item.model_dump(),
                            **self._typed_record_updates(item, record_type),
                            **{
                                key: getattr(item, key) or ("CNY" if key == "currency" else "")
                                for key in (
                                    "serial_number", "payer_account", "payer_name",
                                    "payer_institution", "payer_bank", "payee_account",
                                    "payee_name", "payee_institution", "payee_bank",
                                    "debit_credit", "currency", "channel", "summary",
                                    "region", "transaction_type", "event_status",
                                )
                            },
                            "parser_name": "qwen",
                            "model_id": self.settings.qwen_model,
                            "prompt_version": prompt_version,
                            "review_status": "pending",
                            "provenance": "model_suggested",
                        }
                    )
                    for item in batch.transactions
                ]
                if image_path:
                    self._mark_vision(succeeded=True)
                return records
            except httpx.HTTPStatusError as exc:
                last = exc
                msg = f"第{attempt+1}次重试: HTTP {exc.response.status_code}"
                self._state.retry_warnings.append(msg)
                status = exc.response.status_code
                if attempt + 1 < attempts and (status == 408 or status == 429 or status >= 500):
                    continue
                break
            except httpx.HTTPError as exc:
                last = exc
                self._state.retry_warnings.append(
                    f"第{attempt+1}次重试: {type(exc).__name__}"
                )
                if attempt + 1 < attempts:
                    continue
                break
            except Exception as exc:
                last = exc
                self._state.retry_warnings.append(
                    f"第{attempt+1}次重试: {type(exc).__name__}"
                )
                if attempt + 1 < attempts:
                    correction = build_validation_retry_prompt(str(exc))
                    message_content = payload["messages"][0]["content"]
                    if isinstance(message_content, list):
                        message_content.append({"type": "text", "text": correction})
                    else:
                        payload["messages"][0]["content"] = message_content + "\n" + correction
        self.last_warning = "; ".join(self._state.retry_warnings[-3:])
        raise RuntimeError(f"模型解析失败: {type(last).__name__}")

    @property
    def retry_warnings(self) -> list[str]:
        return getattr(self._state, "retry_warnings", [])
