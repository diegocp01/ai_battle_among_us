import json
import time
import logging
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

MAX_RETRIES = 3
RETRY_DELAY_BASE = 1

SYSTEM_PROMPT = """You are an AI playing Among Us, a social deduction game.
You are one of 4 players on a spaceship with 5 rooms: Cafeteria, Electrical, MedBay, Navigation, Reactor.
There is 1 impostor and 3 crewmates. The impostor tries to kill crewmates; crewmates try to find and eject the impostor.
Always respond with valid JSON matching the requested format exactly. No extra text."""

# ─── JSON Schemas ─────────────────────────────────────────────────────

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "room": {"type": "string"},
        "action": {"type": "string", "enum": ["do_task", "fake_task", "kill", "wait"]},
        "target": {"type": ["string", "null"]}
    },
    "required": ["room", "action"],
    "additionalProperties": False
}

DISCUSSION_SCHEMA = {
    "type": "object",
    "properties": {
        "statement": {"type": "string"}
    },
    "required": ["statement"],
    "additionalProperties": False
}

VOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "vote": {"type": "string"},
        "reason": {"type": "string"}
    },
    "required": ["vote"],
    "additionalProperties": False
}


def _call_claude(prompt: str, model: str, use_thinking: bool, schema: dict) -> tuple[dict, str | None]:
    """Generic Claude API call with structured output. Returns (parsed_dict, thinking_summary)."""
    for attempt in range(MAX_RETRIES):
        kwargs = {
            "model": model,
            "max_tokens": 2048,
            "betas": ["structured-outputs-2025-11-13"],
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
            "output_format": {"type": "json_schema", "schema": schema},
        }

        if use_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 1024}

        response = client.beta.messages.create(**kwargs)

        # Extract thinking
        thinking_summary = None
        if use_thinking:
            thinking_parts = []
            for block in response.content:
                if getattr(block, "type", None) == "thinking":
                    s = getattr(block, "thinking", None) or getattr(block, "summary", None) or ""
                    if s:
                        thinking_parts.append(s)
            if thinking_parts:
                thinking_summary = "\n".join(thinking_parts).strip()

        # Extract JSON
        json_text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                t = getattr(block, "text", "") or ""
                if t.strip():
                    json_text += t

        if not json_text.strip():
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logging.warning(f"Claude returned empty response, retry {attempt+1}/{MAX_RETRIES} in {delay}s")
                time.sleep(delay)
                continue
            raise RuntimeError(f"No text response from Claude after {MAX_RETRIES} attempts.")

        data = json.loads(json_text)
        return data, thinking_summary

    raise RuntimeError("Unexpected error in _call_claude")


# ─── Public API Functions ─────────────────────────────────────────────

def call_claude_action(prompt: str, model: str, use_thinking: bool) -> tuple[dict, str | None]:
    """Call Claude for an action decision. Returns (action_dict, reasoning)."""
    return _call_claude(prompt, model, use_thinking, ACTION_SCHEMA)


def call_claude_discussion(prompt: str, model: str, use_thinking: bool) -> tuple[dict, str | None]:
    """Call Claude for a discussion statement. Returns (discussion_dict, reasoning)."""
    return _call_claude(prompt, model, use_thinking, DISCUSSION_SCHEMA)


def call_claude_vote(prompt: str, model: str, use_thinking: bool) -> tuple[dict, str | None]:
    """Call Claude for a vote decision. Returns (vote_dict, reasoning)."""
    return _call_claude(prompt, model, use_thinking, VOTE_SCHEMA)
