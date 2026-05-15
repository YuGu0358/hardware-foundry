"""ReferenceSearchAgent — finds similar products via Tavily and summarises takeaways.

Runs once at the start of a project (before Clarifier) so its findings can
seed the conversation. Gracefully no-ops if `TAVILY_API_KEY` is unset.
"""

from __future__ import annotations

import json
import os
from typing import Any, ClassVar

import structlog
from foundry_agent_base import (
    AgentContext,
    BaseAgent,
    ProductState,
    ReferenceProduct,
    StateUpdate,
)
from pydantic import BaseModel, ValidationError
from tavily import TavilyClient

from foundry_agent_reference_search.prompts import SUMMARIZE_SYSTEM_PROMPT, user_prompt

logger = structlog.get_logger()

_MAX_TAVILY_RESULTS = 8
_TARGET_PRODUCTS = 5


class _SummarizeOutput(BaseModel):
    """Internal schema for parsing the LLM summarization step."""

    products: list[ReferenceProduct]


class ReferenceSearchAgent(BaseAgent):
    """Tavily web search → Claude Sonnet summarization → 3-5 ReferenceProducts."""

    name: ClassVar[str] = "reference_search"
    model: ClassVar[str] = "agent:sonnet"

    async def run(self, state: ProductState, ctx: AgentContext) -> StateUpdate:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            logger.warning("reference_search.no_tavily_key", run_id=ctx.run_id)
            return {"reference_findings": []}

        try:
            raw_results = self._search(api_key, state.raw_input)
        except Exception as exc:
            logger.warning("reference_search.tavily_failed", error=str(exc))
            return {"reference_findings": []}

        if not raw_results:
            return {"reference_findings": []}

        search_blob = self._format_results(raw_results)
        try:
            raw = await self.llm(
                messages=[
                    {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(state.raw_input, search_blob)},
                ],
                temperature=0.2,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            parsed = _SummarizeOutput.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("reference_search.parse_failed", error=str(exc))
            return {"reference_findings": []}

        products = parsed.products[:_TARGET_PRODUCTS]
        logger.info("reference_search.done", count=len(products))
        return {"reference_findings": products}

    @staticmethod
    def _search(api_key: str, raw_input: str) -> list[dict[str, Any]]:
        client = TavilyClient(api_key=api_key)
        query = f"{raw_input} similar products design review specifications"
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=_MAX_TAVILY_RESULTS,
            include_answer=False,
        )
        results = response.get("results", []) if isinstance(response, dict) else []
        return [r for r in results if isinstance(r, dict)]

    @staticmethod
    def _format_results(results: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for idx, r in enumerate(results, start=1):
            title = r.get("title", "?")
            url = r.get("url", "?")
            content = r.get("content", "")[:600]
            lines.append(f"[{idx}] {title}\nURL: {url}\n{content}\n")
        return "\n".join(lines)
