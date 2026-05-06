"""Prompt templates for Human-in-the-Loop interaction."""

HUMAN_QUESTION_GENERATION_PROMPT = """你需要向用户请求更多信息以继续旅行规划。请根据缺失的信息字段，生成一个清晰、友好的问题。

缺失信息字段：{missing_fields}
当前上下文：{context}

规则：
1. 问题应该具体、明确，用户能直接回答
2. 可以用中文自然语言表达
3. 可以一次性询问多个相关的缺失信息
4. 提供一些示例选项帮助用户理解（如"您偏好高铁还是飞机？"）
5. 问题不超过200字

请以JSON格式输出：
{
  "question": "向用户提出的问题",
  "options": ["可选的提示选项1", "选项2"],
  "required": true
}
"""

HUMAN_RESPONSE_INTEGRATION_PROMPT = """用户回答了之前的问题，请将用户的回复整合到旅行规划中。

用户的问题：{question}
用户的回答：{response}

请提取关键信息并以JSON格式输出：
{
  "extracted_info": {
    "字段名": "提取的值"
  },
  "confidence": "high|medium|low",
  "need_followup": false,
  "followup_question": "如果需要追问，这里填写"
}
"""
