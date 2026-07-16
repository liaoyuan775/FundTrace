import json
from pathlib import Path
import base64
import httpx
from functools import lru_cache
from pydantic import BaseModel

from .config import Settings
from .models import TransactionRecord


class Capability(BaseModel):
    reachable: bool
    text_json: bool=False
    vision: bool=False
    model: str=""
    message: str=""


class QwenAdapter:
    def __init__(self,settings:Settings):self.settings=settings
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
        prompt="将银行或支付流水转换为JSON，返回对象包含transactions数组。字段使用 transaction_time, serial_number, payer_account, payer_name, payer_bank, payee_account, payee_name, payee_bank, amount, balance_after, channel, summary, region。无法确定的字符串填空，禁止编造。"
        content=[]
        if image_path:
            encoded=base64.b64encode(image_path.read_bytes()).decode();content=[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":f"data:image/{image_path.suffix.lstrip('.')};base64,{encoded}"}}]
        else: content=f"{prompt}\n原始内容：\n{text[:50000]}"
        payload={"model":self.settings.qwen_model,"messages":[{"role":"user","content":content}],"temperature":0,"max_tokens":4096,"response_format":{"type":"json_object"},"chat_template_kwargs":{"enable_thinking":False}}
        last=None
        for _ in range(2):
            try:
                response=httpx.post(f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",headers=self._headers(),json=payload,timeout=90,trust_env=False);response.raise_for_status()
                data=json.loads(response.json()["choices"][0]["message"]["content"])
                return [TransactionRecord.model_validate({**item,"parser_name":"qwen","model_id":self.settings.qwen_model,"prompt_version":"v1","review_status":"pending","provenance":"model_suggested"}) for item in data.get("transactions",[])]
            except Exception as exc:last=exc
        raise RuntimeError(f"模型解析失败: {type(last).__name__}")
