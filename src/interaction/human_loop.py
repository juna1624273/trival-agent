"""Human-in-the-Loop interaction manager.

Manages multi-turn Q&A interactions, history tracking, and LLM-driven
determination of when to ask the user for more information.
"""

import logging
from typing import Dict, Any, List, Optional

from langchain_core.language_models import BaseChatModel

from src.llm.provider import create_planning_llm
from src.llm.prompts.human_prompt import (
    HUMAN_QUESTION_GENERATION_PROMPT,
    HUMAN_RESPONSE_INTEGRATION_PROMPT,
)
from src.graph.state import HumanInteraction
from src.utils.json_parser import extract_json

logger = logging.getLogger(__name__)


class HumanLoopManager:
    """Manages human-in-the-loop interactions.

    Responsibilities:
    - Determine if user input is needed based on missing information
    - Generate clear, contextual questions for the user
    - Parse and integrate user responses into the planning state
    - Maintain multi-turn Q&A history
    - Detect when sufficient information has been gathered
    """

    def __init__(self, llm: Optional[BaseChatModel] = None, model: str = ""):
        self.llm = llm or create_planning_llm(model=model if model else None)

    async def should_ask_user(
        self,
        missing_fields: List[str],
        current_context: Dict[str, Any],
        history: List[HumanInteraction],
    ) -> bool:
        """Determine if we should ask the user for more information.

        Returns True if:
        - Critical fields are missing (destination, dates, departure city)
        - The LLM judges that it cannot proceed without more info
        - There have been fewer than 5 rounds of interaction
        """
        if not missing_fields:
            return False

        critical_fields = {"出发城市", "出发地", "目的地", "出发日期", "返回日期"}
        has_critical = any(f in critical_fields for f in missing_fields)

        if has_critical:
            return True

        # Max 5 rounds of back-and-forth
        if len(history) >= 5:
            return False

        return True

    async def generate_question(
        self,
        missing_fields: List[str],
        context: Dict[str, Any],
        history: List[HumanInteraction],
    ) -> Dict[str, Any]:
        """Generate a user-friendly question based on missing information.

        Args:
            missing_fields: List of field names that need values
            context: Current planning context
            history: Previous Q&A interactions

        Returns:
            Dict with 'question', 'options', and 'required' fields
        """
        prompt = HUMAN_QUESTION_GENERATION_PROMPT.format(
            missing_fields=", ".join(missing_fields),
            context=str(context),
        )

        # Include history for context
        if history:
            history_text = "\n".join(
                f"Q: {h['question']}\nA: {h.get('response', '')}"
                for h in history[-3:]  # Last 3 interactions
            )
            prompt += f"\n\n之前的对话：\n{history_text}"

        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            return extract_json(response.content if hasattr(response, 'content') else str(response))
        except Exception as e:
            logger.warning(f"Failed to generate question: {e}")
            return {
                "question": f"请补充以下信息：{'、'.join(missing_fields)}",
                "options": [],
                "required": True,
            }

    async def integrate_response(
        self,
        question: str,
        response_text: str,
        user_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse the user's response and extract structured information.

        Args:
            question: The question that was asked
            response_text: The user's answer
            user_profile: Current user profile to update

        Returns:
            Dict with 'extracted_info', 'confidence', 'need_followup', 'followup_question'
        """
        prompt = HUMAN_RESPONSE_INTEGRATION_PROMPT.format(
            question=question,
            response=response_text,
        )

        try:
            llm_response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            extracted = extract_json(
                llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
            )

            # Merge extracted info into user profile
            updated_profile = {**user_profile}
            extracted_info = extracted.get("extracted_info", {})
            updated_profile.update(extracted_info)

            return {
                **extracted,
                "updated_profile": updated_profile,
            }
        except Exception as e:
            logger.warning(f"Failed to integrate response: {e}")
            return {
                "extracted_info": {},
                "confidence": "low",
                "need_followup": False,
                "followup_question": "",
                "updated_profile": user_profile,
            }

    def build_history_summary(self, history: List[HumanInteraction]) -> str:
        """Build a readable summary of the Q&A history."""
        if not history:
            return "尚无对话记录"

        lines = []
        for i, h in enumerate(history, 1):
            q = h.get("question", "")
            r = h.get("response", "等待回复...")
            lines.append(f"第{i}轮: Q: {q} → A: {r}")
        return "\n".join(lines)
