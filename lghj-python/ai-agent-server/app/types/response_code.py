"""统一响应码枚举。

复现自原 Java 类：
    ai-agent-scaffoid-feng/ai-agent-scaffoid-feng-types/src/main/java/cn/feng/types/enums/ResponseCode.java

码值与文案严格照抄原 Java，禁止改动。
"""

from enum import Enum


class ResponseCode(str, Enum):
    """响应码枚举（code, info）。"""

    SUCCESS = "0000"          # 成功
    UN_ERROR = "0001"         # 未知失败
    ILLEGAL_PARAMETER = "0002"  # 非法参数
    NOT_FOUND_METHOD = "0003"   # 不存在的方法

    E0001 = "E0001"           # 智能体ID不存在
    E0002 = "E0002"           # 智能体MCP配置不在可加载范围

    @property
    def info(self) -> str:
        """响应码对应的文案（对应原 Java 的 getInfo()）。"""
        return _INFO_MAP[self.value]


# 文案映射（照抄原 Java 枚举构造参数中的中文描述）
_INFO_MAP: dict[str, str] = {
    ResponseCode.SUCCESS.value: "成功",
    ResponseCode.UN_ERROR.value: "未知失败",
    ResponseCode.ILLEGAL_PARAMETER.value: "非法参数",
    ResponseCode.NOT_FOUND_METHOD.value: "不存在的方法",
    ResponseCode.E0001.value: "智能体ID不存在",
    ResponseCode.E0002.value: "智能体MCP配置不在可加载范围",
}
