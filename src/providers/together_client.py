from langchain_together import ChatTogether

from src.config import get_settings


def build_together_chat_model(model_name: str,temperature: float = 0 ) -> ChatTogether:
    settings = get_settings()

    return ChatTogether(
        model= model_name or settings.model,
        temperature=temperature,
        api_key=settings.together_api_key,
    )