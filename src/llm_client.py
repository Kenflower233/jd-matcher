"""LLM客户端：封装DeepSeek API调用，含重试与异常分类。"""
import time

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from .config import Config
from .usage_limit import PUBLIC_DAILY_LIMITER, PublicQuotaExceeded


class LLMError(Exception):
    """LLM调用失败的统一异常，message面向用户可读。"""


class LLMClient:
    def __init__(self, config: Config) -> None:
        try:
            self._client = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=config.timeout,
                max_retries=0,
            )
        except Exception as e:
            raise LLMError(f"模型客户端初始化失败，请检查API配置：{e}") from e
        self._model = config.model
        self._max_retries = config.max_retries
        self._public_deployment = config.public_deployment
        self._daily_llm_call_limit = config.daily_llm_call_limit

    def chat(self, system_prompt: str, user_prompt: str, json_mode: bool = True) -> str:
        """调用LLM，返回文本内容；失败时抛出LLMError。

        json_mode=True时强制模型输出json（DeepSeek要求提示词中含"json"字样）。
        """
        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = None
        for attempt in range(self._max_retries + 1):
            try:
                if self._public_deployment:
                    PUBLIC_DAILY_LIMITER.reserve(self._daily_llm_call_limit)
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    **kwargs,
                )
                break
            except PublicQuotaExceeded as e:
                raise LLMError(str(e)) from e
            except (APITimeoutError, RateLimitError, APIConnectionError) as e:
                if attempt < self._max_retries:
                    time.sleep(min(2**attempt, 4))
                    continue
                if isinstance(e, APITimeoutError):
                    message = "模型响应超时，请稍后重试"
                elif isinstance(e, RateLimitError):
                    message = "模型请求过于频繁或额度不足，请稍后重试并检查账户额度"
                else:
                    message = "无法连接模型服务，请检查网络或 API 地址后重试"
                raise LLMError(message) from e
            except APIError as e:
                detail = getattr(e, "message", str(e))
                raise LLMError(f"模型API调用失败：{detail}") from e

        if resp is None or not getattr(resp, "choices", None):
            raise LLMError("模型返回结构异常：缺少候选结果，请重试")
        message = getattr(resp.choices[0], "message", None)
        content = getattr(message, "content", None)
        if not content:
            raise LLMError("模型返回了空内容，请重试")
        return content
