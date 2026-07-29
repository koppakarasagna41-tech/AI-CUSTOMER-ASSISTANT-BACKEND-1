"""
app/services/llm/prompt_builder.py
────────────────────────────────
Builds a single provider-agnostic prompt from conversation history.
"""

from typing import Iterable

from app.services.gemini.prompt_manager import PromptManager


def build_chat_prompt(
    user_message: str,
    history: Iterable[dict],
    user_name: str | None = None,
) -> str:
    system_prompt = PromptManager.system_prompt()
    if user_name:
        system_prompt += "\n\n" + PromptManager.first_message_prompt(user_name)

    conversation_lines = []
    for item in history:
        role = item.get("role", "user")
        speaker = "Assistant" if role in ("assistant", "model") else "User"
        conversation_lines.append(f"{speaker}: {item.get('content', '').strip()}")

    if conversation_lines:
        system_prompt += "\n\n" + "\n".join(conversation_lines)

    prompt = f"{system_prompt}\n\nUser: {user_message.strip()}\nAssistant:"
    return prompt
