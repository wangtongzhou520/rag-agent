"""产品身份基线：默认自称、可配置项与底层模型不披露约束。"""

from app.framework.config import AgentIdentitySettings
from app.rag.prompt.identity import (
    DEFAULT_DESCRIPTION,
    DEFAULT_NAME,
    DISCLOSURE_RULE,
    identity_prompt,
    with_identity,
)


def test_default_identity_is_product_scoped() -> None:
    text = identity_prompt(AgentIdentitySettings())

    assert DEFAULT_NAME in text
    assert DEFAULT_DESCRIPTION in text
    assert DISCLOSURE_RULE in text
    assert "通义" not in text
    assert "qwen" not in text.lower()


def test_identity_uses_configured_name_and_description() -> None:
    text = identity_prompt(
        AgentIdentitySettings(name="Acme 知识官", description="集团内部制度问答助手")
    )

    assert text.startswith("你是Acme 知识官，集团内部制度问答助手。")
    assert DISCLOSURE_RULE in text


def test_disclose_model_drops_the_non_disclosure_rule() -> None:
    text = identity_prompt(AgentIdentitySettings(disclose_model=True))

    assert DISCLOSURE_RULE not in text
    assert text == f"你是{DEFAULT_NAME}，{DEFAULT_DESCRIPTION}。"


def test_blank_configuration_falls_back_to_product_defaults() -> None:
    text = identity_prompt(AgentIdentitySettings(name="  ", description=""))

    assert DEFAULT_NAME in text
    assert DEFAULT_DESCRIPTION in text


def test_with_identity_prefixes_slot_prompt_and_keeps_empty_body_clean() -> None:
    settings = AgentIdentitySettings(name="Acme 知识官", description="制度问答助手")

    composed = with_identity("仅依据资料回答。", settings)
    assert composed == f"{identity_prompt(settings)}\n仅依据资料回答。"

    assert with_identity("   ", settings) == identity_prompt(settings)
