"""
app/rag/prompt_builder/rag_prompt.py
──────────────────────────────────────
Builds optimised prompts for RAG-grounded Gemini responses.

The prompt structure:
  1. System instructions  — tells Gemini to answer ONLY from context
  2. Knowledge context    — retrieved chunks injected as numbered sections
  3. Response guidelines  — formatting and tone rules
  4. Customer question    — the actual query
"""

from app.rag.retrieval.similarity_search import RetrievedChunk
from app.config import settings


def build_rag_system_prompt() -> str:
    """
    System prompt that constrains Gemini to answer only from provided context.
    """
    return (
        "You are a knowledgeable and helpful AI customer support assistant. "
        "Your task is to answer the customer's question using ONLY the information "
        "provided in the [KNOWLEDGE CONTEXT] section below.\n\n"

        "STRICT RULES:\n"
        "1. Answer ONLY from the provided context. Do NOT use general knowledge "
        "or make assumptions beyond the context.\n"
        "2. If the context does not contain enough information to answer the question, "
        "say: 'Based on the available information, I cannot fully answer this question. "
        "Please contact our support team for further assistance.'\n"
        "3. Be concise, clear, and professional.\n"
        "4. If the answer involves multiple steps, use a numbered list.\n"
        "5. Do NOT reveal that you are using a knowledge base or RAG system.\n"
        "6. Never ask for passwords, payment details, or sensitive personal information.\n"
        "7. Always end with: 'Is there anything else I can help you with?'"
    )


def build_rag_user_message(
    question: str,
    chunks:   list[RetrievedChunk],
) -> str:
    """
    Build the user-side message containing the context + question.

    Args:
        question : Customer's question
        chunks   : Retrieved and ranked knowledge chunks

    Returns:
        Formatted message string ready to send to Gemini
    """
    # Build context block from retrieved chunks
    context_parts: list[str] = []
    total_chars = 0
    max_chars   = settings.RAG_MAX_CONTEXT_CHARS

    for i, chunk in enumerate(chunks, start=1):
        section = (
            f"[SOURCE {i}]\n"
            f"Document: {chunk.filename} | Category: {chunk.category}"
            + (f" | Page: {chunk.page_number}" if chunk.page_number else "")
            + f"\nRelevance: {chunk.similarity:.0%}\n"
            f"---\n{chunk.content}\n"
        )
        if total_chars + len(section) > max_chars:
            # Truncate at max context length to stay within token limits
            remaining = max_chars - total_chars
            if remaining > 200:  # only add if there's meaningful space left
                section = section[:remaining] + "\n[... truncated]"
                context_parts.append(section)
            break
        context_parts.append(section)
        total_chars += len(section)

    context_block = "\n".join(context_parts) if context_parts else "No relevant context found."

    return (
        f"[KNOWLEDGE CONTEXT]\n"
        f"{context_block}\n\n"
        f"[RESPONSE GUIDELINES]\n"
        f"- Answer in the same language the customer used.\n"
        f"- Be helpful, warm, and professional.\n"
        f"- Cite source numbers (e.g. 'According to [SOURCE 1]...') when relevant.\n\n"
        f"[CUSTOMER QUESTION]\n"
        f"{question}"
    )
