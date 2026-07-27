"""
app/prompts
────────────
Production-ready prompt template library.

Quick-start
───────────
# 1. Use the registry (recommended)
from app.prompts import PromptRegistry

system, user = PromptRegistry.build(
    "billing",
    customer_name="Jane",
    issue="I was charged twice.",
)

# 2. Import a specific prompt class
from app.prompts import BillingPrompt

system = BillingPrompt.system()
user   = BillingPrompt.user(customer_name="Jane", issue="Double charge")

# 3. List all categories
from app.prompts import CATEGORIES
print(CATEGORIES)
"""

from .base             import BasePrompt
from .customer_support import CustomerSupportPrompt
from .refund           import RefundPrompt
from .billing          import BillingPrompt
from .technical        import TechnicalPrompt
from .account_recovery import AccountRecoveryPrompt
from .complaint        import ComplaintPrompt
from .greetings        import GreetingsPrompt
from .escalation       import EscalationPrompt
from .unknown          import UnknownPrompt
from .registry         import PromptRegistry, CATEGORIES

__all__ = [
    # Base
    "BasePrompt",
    # Prompt classes
    "CustomerSupportPrompt",
    "RefundPrompt",
    "BillingPrompt",
    "TechnicalPrompt",
    "AccountRecoveryPrompt",
    "ComplaintPrompt",
    "GreetingsPrompt",
    "EscalationPrompt",
    "UnknownPrompt",
    # Registry
    "PromptRegistry",
    "CATEGORIES",
]
