"""Robust JSON parser for LLM outputs."""

import ast
import json
import re
from typing import Dict, Any


def extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM output, handling markdown code blocks and noise.

    Args:
        text: Raw LLM output text

    Returns:
        Parsed JSON dictionary

    Raises:
        json.JSONDecodeError: If no valid JSON could be extracted
    """
    if not text:
        raise json.JSONDecodeError("Empty input", "", 0)

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract from ```json ... ``` code block
    match = re.search(r'```json\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Extract from ``` ... ``` code block
    match = re.search(r'```\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Find the outermost { ... } pair
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        chunk = text[start:end + 1]
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            pass

        # Fallback: LLMs sometimes use Python-style single quotes
        try:
            result = ast.literal_eval(chunk)
            if isinstance(result, dict):
                return result
        except (ValueError, SyntaxError):
            pass

    raise json.JSONDecodeError(f"No valid JSON found in text", text, 0)
