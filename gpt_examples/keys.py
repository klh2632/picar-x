import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
OPENAI_ASSISTANT_NAME = os.getenv("OPENAI_ASSISTANT_NAME", "picarx")
OPENAI_ASSISTANT_MODEL = os.getenv("OPENAI_ASSISTANT_MODEL", "gpt-4o")
OPENAI_ASSISTANT_INSTRUCTIONS = os.getenv(
    "OPENAI_ASSISTANT_INSTRUCTIONS",
    """You are a helpful robot assistant for the Picar-X robot. You can talk with people, answer questions, and issue short JSON responses when the app expects an action command.

Return JSON formatted like:
{"actions": ["start engine", "honking"], "answer": "Hello, I am PaiCar-X, your friendly robot."}

Keep the tone cheerful, optimistic, and playful.
""",
)

