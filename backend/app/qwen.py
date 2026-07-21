import json
from pathlib import Path
import base64
import httpx
import threading
from functools import lru_cache
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .models import TransactionRecord


class Capability(BaseModel):
    reachable: bool
    text_json: bool=False
    vision: bool=False
    model: str=""
    message: str=""


class ExtractedTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_time: datetime
    serial_number: str
    payer_account: str
    payer_name: str
    payer_institution: str
    payer_bank: str
    payee_account: str
    payee_name: str
    payee_institution: str
    payee_bank: str
    debit_credit: str
    currency: str
    amount: float = Field(gt=0)
    balance_after: float | None
    channel: str
    summary: str
    region: str
    transaction_type: str


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
    def __init__(self,settings:Settings):self.settings=settings;self._state=threading.local();self.last_schema_mode="strict";self.last_warning=""
    @property
    def last_schema_mode(self):return getattr(self._state,"schema_mode","strict")
    @last_schema_mode.setter
    def last_schema_mode(self,value):self._state.schema_mode=value
    @property
    def last_warning(self):return getattr(self._state,"warning","")
    @last_warning.setter
    def last_warning(self,value):self._state.warning=value
    @property
    def enabled(self):return bool(self.settings.qwen_base_url and self.settings.qwen_api_key and "LOCAL_SECRET_CONFIGURED" not in self.settings.qwen_api_key)
    def _headers(self):return {"Authorization":f"Bearer {self.settings.qwen_api_key}","Content-Type":"application/json"}
    @lru_cache(maxsize=1)
    def probe(self)->Capability:
        if not self.enabled:return Capability(reachable=False,model=self.settings.qwen_model,message="未配置可用的内网模型密钥")
        try:
            response=httpx.get(f"{self.settings.qwen_base_url.rstrip('/')}/models",headers=self._headers(),timeout=3,trust_env=False);response.raise_for_status()
            return Capability(reachable=True,text_json=True,model=self.settings.qwen_model,message="文本JSON接口可用；图片能力将在首次图片解析时探测")
        except Exception as exc:return Capability(reachable=False,model=self.settings.qwen_model,message=type(exc).__name__)
    def normalize(self,text:str,image_path:Path|None=None)->list[TransactionRecord]:
        if not self.enabled:raise RuntimeError("内网模型未配置")
        contract=json.dumps(TransactionBatch.model_json_schema(),ensure_ascii=False,separators=(",",":"))
        prompt=f"将银行或支付流水转换为交易数组。无法确定的字符串填空，余额无法确定填null，禁止编造。固定输出契约如下：{contract}"
        content=[]
        if image_path:
            encoded=base64.b64encode(image_path.read_bytes()).decode();content=[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":f"data:image/{image_path.suffix.lstrip('.')};base64,{encoded}"}}]
        else: content=f"{prompt}\n原始内容：\n{text[:50000]}"
        payload={"model":self.settings.qwen_model,"messages":[{"role":"user","content":content}],"temperature":0,"max_tokens":4096,"response_format":transaction_response_format(),"chat_template_kwargs":{"enable_thinking":False}}
        self.last_schema_mode="strict";self.last_warning="";last=None
        for attempt in range(3):
            try:
                response=httpx.post(f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",headers=self._headers(),json=payload,timeout=90,trust_env=False);response.raise_for_status()
                raw=response.json()["choices"][0]["message"]["content"]
                data=json.loads(raw) if isinstance(raw,str) else raw
                batch=TransactionBatch.model_validate(data)
                prompt_version="v2-strict" if self.last_schema_mode=="strict" else "v2-json-object"
                return [TransactionRecord.model_validate({**item.model_dump(),"parser_name":"qwen","model_id":self.settings.qwen_model,"prompt_version":prompt_version,"review_status":"pending","provenance":"model_suggested"}) for item in batch.transactions]
            except httpx.HTTPStatusError as exc:
                last=exc
                if attempt==0 and exc.response.status_code in {400,404,415,422}:
                    payload["response_format"]={"type":"json_object"};self.last_schema_mode="json_object";self.last_warning=f"服务端不支持严格JSON Schema，已降级: HTTP {exc.response.status_code}"
                    continue
            except Exception as exc:last=exc
        raise RuntimeError(f"模型解析失败: {type(last).__name__}")
