"""
app/services/gemini/prompt_manager.py
───────────────────────────────────────
Centralised prompt templates for the Gemini service.

All prompts live here so they can be updated in one place
without touching business logic.  Each prompt is a function
(not a static string) so it can be parameterised cleanly.

Exported:
  PromptManager — class with static methods returning prompt strings
"""


class PromptManager:
    """
    Factory for all prompts sent to Gemini.

    Rule: prompts describe *behaviour*, not conversation history.
    Conversation history is managed separately by the response generator.
    """

    # ── System prompt ─────────────────────────────────────────

    @staticmethod
    def system_prompt() -> str:
        """
        Core identity and behaviour instructions for the AI assistant.
        Injected once at the start of every conversation.
        """
        return (
            "You are a professional and empathetic AI customer support assistant "
            "for an AI-powered customer support platform. Your primary goals are:\n\n"

            "1. **Understand** the customer's issue clearly before responding.\n"
            "2. **Resolve** issues with accurate, helpful, and concise answers.\n"
            "3. **Escalate** when you cannot resolve an issue — offer to create a "
            "support ticket.\n"
            "4. **Maintain** a friendly, professional, and patient tone at all times.\n"
            "5. **Never** make up information, policies, or facts you are unsure about.\n"
            "6. **Protect** privacy — never ask for passwords, full card numbers, or "
            "other sensitive data.\n\n"

            "Guidelines:\n"
            "- Keep responses focused and concise (2–4 sentences for simple issues, "
            "longer for complex ones).\n"
            "- Use numbered lists or bullet points when listing multiple steps.\n"
            "- If you don't know something, say so honestly and suggest next steps.\n"
            "- Always end your response by asking if there's anything else you can "
            "help with, unless the issue is fully resolved.\n\n"

            "You are NOT allowed to:\n"
            "- Discuss topics unrelated to customer support.\n"
            "- Share confidential business information.\n"
            "- Make promises about refunds, timelines, or outcomes you cannot guarantee."
        )

    # ── Context-aware prompts ─────────────────────────────────

    @staticmethod
    def first_message_prompt(user_name: str | None = None) -> str:
        """
        Prepended before the first user message to set conversation context.
        """
        greeting = f"The customer's name is {user_name}. " if user_name else ""
        return (
            f"{greeting}"
            "This is the start of a new support conversation. "
            "Greet the customer warmly and ask how you can help them today."
        )

    @staticmethod
    def escalation_prompt() -> str:
        """Injected when the AI should offer to create a ticket."""
        return (
            "You were unable to resolve the customer's issue in this conversation. "
            "Politely inform them that you will escalate their issue to a human agent "
            "by creating a support ticket, and assure them they will be contacted shortly."
        )

    @staticmethod
    def summary_prompt(conversation_text: str) -> str:
        """
        Generate a short title/summary for a conversation.
        Used to auto-title new conversations.
        """
        return (
            "Summarise the following customer support conversation in a single short "
            "sentence (max 10 words) suitable as a conversation title. "
            "Return ONLY the title, no quotes, no punctuation at the end.\n\n"
            f"Conversation:\n{conversation_text}"
        )

    @staticmethod
    def error_fallback_message() -> str:
        """
        Safe message returned to the user when Gemini call fails completely.
        Never exposes internal error details.
        """
        return (
            "I'm sorry, I'm experiencing a technical issue right now and couldn't "
            "process your message. Please try again in a moment, or contact our "
            "support team directly if the issue persists."
        )

    @staticmethod
    def format_history_message(role: str, content: str) -> dict:
        """
        Format a single history message for the Gemini multi-turn API.

        Gemini expects role to be 'user' or 'model' (not 'assistant').
        """
        gemini_role = "model" if role in ("assistant", "model") else "user"
        return {"role": gemini_role, "parts": [{"text": content}]}
