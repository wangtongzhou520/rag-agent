"""产品身份基线：用部署配置定义助手自称，并约束模型不擅自暴露底层实现。

身份是部署级配置（``RAGENT_AGENT__NAME`` / ``RAGENT_AGENT__DESCRIPTION`` /
``RAGENT_AGENT__DISCLOSE_MODEL``），而不是写死在某个 Prompt 槽位里：无论管理员把槽位
内容改成什么，面向用户的回答都会带上这条身份基线。底层模型与供应商默认不对用户披露。
"""

from app.framework.config import AgentIdentitySettings, get_settings

DEFAULT_NAME = "Ragent 知识助手"
DEFAULT_DESCRIPTION = "面向企业知识检索与问答的产品助手"

DISCLOSURE_RULE = (
    "当用户询问你的身份、开发方或底层模型时，只按上述身份介绍自己的能力与用途；"
    "不透露、不猜测、不确认底层模型名称、供应商或接口细节。"
)


def identity_prompt(settings: AgentIdentitySettings | None = None) -> str:
    """渲染身份基线文案；``disclose_model=true`` 时去掉不披露约束。"""

    identity = settings or get_settings().agent
    name = identity.name.strip() or DEFAULT_NAME
    description = identity.description.strip() or DEFAULT_DESCRIPTION
    baseline = f"你是{name}，{description}。"
    return baseline if identity.disclose_model else f"{baseline}{DISCLOSURE_RULE}"


def with_identity(prompt: str, settings: AgentIdentitySettings | None = None) -> str:
    """把身份基线前置到槽位文案之前，槽位内容为空时只返回基线。"""

    baseline = identity_prompt(settings)
    body = prompt.strip()
    return f"{baseline}\n{body}" if body else baseline
