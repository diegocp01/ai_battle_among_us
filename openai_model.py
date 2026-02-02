from openai import OpenAI
from pydantic import BaseModel
from typing import Literal, Optional
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

# ─── Structured Response Models ───────────────────────────────────────

class ActionResponse(BaseModel):
    room: str
    action: Literal["do_task", "fake_task", "kill", "wait"]
    target: Optional[str] = None


class DiscussionResponse(BaseModel):
    statement: str


class VoteResponse(BaseModel):
    vote: str
    reason: Optional[str] = None


# ─── Reasoning Config ─────────────────────────────────────────────────

MINIMAL_REASONING_MODELS = {'gpt-5-mini'}
LOW_REASONING_MODELS = {'gpt-5.1-low'}
HIGH_REASONING_MODELS = {'gpt-5.2-high'}


def _get_reasoning_config(model_key):
    key = model_key or ''
    if key in MINIMAL_REASONING_MODELS:
        return False, "minimal"
    elif key in LOW_REASONING_MODELS:
        return True, "low"
    elif key in HIGH_REASONING_MODELS:
        return True, "high"
    else:
        return True, "medium"


def _extract_reasoning(response):
    for item in response.output:
        if getattr(item, "type", None) == "reasoning":
            parts = []
            for s in (item.summary or []):
                if getattr(s, "text", None):
                    parts.append(s.text)
            if parts:
                return "\n".join(parts)
    return None


SYSTEM_PROMPT = """You are an AI playing Among Us, a social deduction game.
You are one of 4 players on a spaceship with 5 rooms: Cafeteria, Electrical, MedBay, Navigation, Reactor.
There is 1 impostor and 3 crewmates. The impostor tries to kill crewmates; crewmates try to find and eject the impostor.
Always respond with valid JSON matching the requested format exactly."""


# ─── API Call Functions ───────────────────────────────────────────────

def call_gpt_action(prompt: str, model: str = "gpt-5.1", model_key: str = None) -> tuple[dict, str | None]:
    """Call GPT for an action decision. Returns (action_dict, reasoning)."""
    show_reasoning, effort = _get_reasoning_config(model_key)

    kwargs = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "text_format": ActionResponse,
    }

    if show_reasoning:
        kwargs["reasoning"] = {"effort": effort, "summary": "auto"}
    else:
        kwargs["reasoning"] = {"effort": "minimal"}

    response = client.responses.parse(**kwargs)
    parsed = response.output_parsed

    result = {
        "room": parsed.room,
        "action": parsed.action,
        "target": parsed.target,
    }

    reasoning = _extract_reasoning(response) if show_reasoning else None
    return result, reasoning


def call_gpt_discussion(prompt: str, model: str = "gpt-5.1", model_key: str = None) -> tuple[dict, str | None]:
    """Call GPT for a discussion statement. Returns (discussion_dict, reasoning)."""
    show_reasoning, effort = _get_reasoning_config(model_key)

    kwargs = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "text_format": DiscussionResponse,
    }

    if show_reasoning:
        kwargs["reasoning"] = {"effort": effort, "summary": "auto"}
    else:
        kwargs["reasoning"] = {"effort": "minimal"}

    response = client.responses.parse(**kwargs)
    parsed = response.output_parsed

    result = {"statement": parsed.statement}
    reasoning = _extract_reasoning(response) if show_reasoning else None
    return result, reasoning


def call_gpt_vote(prompt: str, model: str = "gpt-5.1", model_key: str = None) -> tuple[dict, str | None]:
    """Call GPT for a vote decision. Returns (vote_dict, reasoning)."""
    show_reasoning, effort = _get_reasoning_config(model_key)

    kwargs = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "text_format": VoteResponse,
    }

    if show_reasoning:
        kwargs["reasoning"] = {"effort": effort, "summary": "auto"}
    else:
        kwargs["reasoning"] = {"effort": "minimal"}

    response = client.responses.parse(**kwargs)
    parsed = response.output_parsed

    result = {"vote": parsed.vote, "reason": parsed.reason}
    reasoning = _extract_reasoning(response) if show_reasoning else None
    return result, reasoning
