"""Small curated Responses/Codex model menu; account access can differ.

Identifiers: https://developers.openai.com/api/docs/models
This is a configuration menu, not a claim of account-specific availability.
"""

DEFAULT_MODEL = "gpt-6-astra"
MODELS = [
    {"id": "gpt-6-astra", "name": "GPT-6 Astra", "default": True},
    {"id": "gpt-5.6-sol", "name": "GPT-5.6 Sol"},
    {"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra"},
    {"id": "gpt-5.6-luna", "name": "GPT-5.6 Luna"},
    {"id": "gpt-5.3-codex", "name": "GPT-5.3 Codex"},
]
