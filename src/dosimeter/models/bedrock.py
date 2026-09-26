""" invoking our bedrock modal """

from langchain_aws import ChatBedrockConverse
from langchain_core.language_models import BaseChatModel

from ..aws.aws import get_client
from ..config.settings import get_settings
from ..prompts import SYSTEM_PROMPT
from ..redaction import redact


def converse(prompt: str) -> str:
    """ calling our bedrock modal """

    settings = get_settings()
    bedrock = get_client("bedrock-runtime")

    response = bedrock.converse(
        modelId=settings.bedrock_model_id,
        system=[
            {
                "text": SYSTEM_PROMPT,
            }
        ],
        messages=[
            {
                "role": "user",
                # names and dose histories come out before anything reaches the model
                "content": [{"text": redact(prompt)}],
            }
        ],
        inferenceConfig={
            "maxTokens": settings.bounds.default_max_tokens_per_call,
        },
    )

    return response["output"]["message"]["content"][0]["text"]


def get_chat_model(*, temperature: float = 0.0, max_tokens: int | None = None) -> BaseChatModel:
    """ Return a configured bedrock chat model - could be swapped out for any BaseChatModel """

    settings = get_settings()

    return ChatBedrockConverse(
        model=settings.bedrock_model_id,
        region_name=settings.aws_region,
        credentials_profile_name=settings.aws_profile,
        temperature=temperature,
        max_tokens=max_tokens or settings.bounds.default_max_tokens_per_call,
        # content filters on every model call
        guardrail_config={
            "guardrailIdentifier": settings.guardrail_id,
            "guardrailVersion": settings.guardrail_version,
        },
    )
