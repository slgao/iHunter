import json
import re


def _fix_json_string(text: str) -> str:
    """Fix common LLM JSON mistakes."""
    # Fix invalid escape sequences (e.g. \p, \s)
    text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)
    # Replace literal newlines inside JSON string values with \n
    # Walk char-by-char to only replace newlines that are inside quoted strings
    result = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            result.append(ch)
            escaped = False
        elif ch == '\\' and in_string:
            result.append(ch)
            escaped = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif ch == '\n' and in_string:
            result.append('\\n')
        elif ch == '\r' and in_string:
            result.append('\\r')
        elif ch == '\t' and in_string:
            result.append('\\t')
        else:
            result.append(ch)
    return ''.join(result)


def parse_llm_json(text: str):
    """Extract and parse JSON from LLM output, handling common issues."""
    text = text.strip()

    # Strip markdown code fences
    if "```" in text:
        for part in text.split("```"):
            part = part.strip().removeprefix("json").strip()
            try:
                return json.loads(part)
            except Exception:
                try:
                    return json.loads(_fix_json_string(part))
                except Exception:
                    continue

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try after fixing
    try:
        return json.loads(_fix_json_string(text))
    except json.JSONDecodeError:
        pass

    # Extract first JSON object or array via regex
    for pattern in (r"\[.*\]", r"\{.*\}"):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                try:
                    return json.loads(_fix_json_string(candidate))
                except json.JSONDecodeError:
                    continue

    raise ValueError(f"Could not parse JSON from LLM response:\n{text[:300]}")
