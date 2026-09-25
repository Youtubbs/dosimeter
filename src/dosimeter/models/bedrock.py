"""invoking our bedrock modal"""

from ..aws.config import BEDROCK_MODEL_ID, BEDROCK_MAX_TOKENS
from ..aws.aws import get_client
from ..prompts import SYSTEM_PROMPT


def converse(prompt: str) -> str:
    """calling our bedrock modal"""

    bedrock = get_client("bedrock-runtime")

    response = bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        system=[
            {
                "text": SYSTEM_PROMPT,
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        inferenceConfig={
            "maxTokens": BEDROCK_MAX_TOKENS,
        },
    )

    return response["output"]["message"]["content"][0]["text"]
