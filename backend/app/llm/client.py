import os
import litellm

MODEL = "openrouter/openai/gpt-oss-120b"

def get_completion(messages: list[dict], response_schema: dict) -> str:
    """Call LiteLLM → OpenRouter with structured output. Returns raw JSON string."""
    response = litellm.completion(
        model=MODEL,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "trading_response",
                "strict": True,
                "schema": response_schema,
            },
        },
        api_key=os.getenv("OPENROUTER_API_KEY"),
        api_base="https://openrouter.ai/api/v1",
        extra_headers={
            "X-Title": "FinAlly Trading Workstation",
            "HTTP-Referer": "https://github.com/finally-trading",
        },
    )
    return response.choices[0].message.content
