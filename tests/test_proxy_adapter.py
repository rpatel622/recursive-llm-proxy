from rlm_proxy.adapter import forwarded_llm_kwargs, split_query_context
from rlm_proxy.models import ChatMessage


def test_split_query_context_uses_last_user_message() -> None:
    messages = [
        ChatMessage(role="system", content="Use the supplied record."),
        ChatMessage(role="user", content="Record: A=7"),
        ChatMessage(role="assistant", content="Understood."),
        ChatMessage(role="user", content="What is A?"),
    ]

    query, context = split_query_context(messages, "external")

    assert query == "What is A?"
    assert context.startswith("external\n\n")
    assert '"content":"Record: A=7"' in context
    assert '"content":"What is A?"' not in context


def test_forwarded_llm_kwargs_drops_proxy_fields() -> None:
    values = forwarded_llm_kwargs(
        {
            "temperature": 0.1,
            "max_tokens": 50,
            "messages": [],
            "model": "public-name",
            "stream": True,
            "rlm": {"max_depth": 2},
        }
    )
    assert values == {"temperature": 0.1, "max_tokens": 50}
