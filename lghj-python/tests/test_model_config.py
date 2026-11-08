"""多模型选择（cc-switch 风格）契约自测。

覆盖：
- /api/user/model-config/{list,save,delete,activate}（JWT，api_key 打码回显）
- /api/internal/model-config（X-Internal-Token，明文 key 仅服务间可见）
- 未配置/非数字 userId → data=null（8091 走默认模型客户端的降级路径）
"""

from __future__ import annotations

import uuid

from conftest import INTERNAL_TOKEN, MAIN, make_suffix


def _payload(name: str, key: str | None = None) -> dict:
    return {
        "name": name,
        "baseUrl": "https://api.deepseek.com",
        "apiKey": key or f"sk-mcfg-test-{uuid.uuid4().hex[:12]}",
        "model": "deepseek-chat",
        "completionsPath": "/v1/chat/completions",
    }


def _save(client: httpx_client, headers: dict, payload: dict):
    return client.post(f"{MAIN}/api/user/model-config/save", json=payload, headers=headers).json()


# httpx.Client 类型仅作注解用途（避免重复构造）
from httpx import Client as httpx_client  # noqa: E402


def test_model_config_crud_and_masking(client: httpx_client, make_user) -> None:
    """列表打码 / 同名 upsert / activate 单一激活 / delete / 404 码。"""
    user = make_user("mcfg")
    headers = user["headers"]
    key_a = f"sk-mcfg-a-{make_suffix()}-abcd1234"

    # 初始为空列表
    body = client.get(f"{MAIN}/api/user/model-config/list", headers=headers).json()
    assert body["code"] == 200 and body["data"] == [], body

    # 保存两条
    assert _save(client, headers, _payload("主力", key_a))["code"] == 200
    assert _save(client, headers, _payload("备用"))["code"] == 200

    # 列表：打码 + 均未激活 + camelCase 字段
    body = client.get(f"{MAIN}/api/user/model-config/list", headers=headers).json()
    items = body["data"]
    assert len(items) == 2, body
    first = next(i for i in items if i["name"] == "主力")
    assert first["isActive"] == 0
    assert "****" in first["apiKey"], first
    assert key_a not in first["apiKey"] and first["apiKey"].endswith("1234"), first
    assert {"id", "name", "baseUrl", "apiKey", "model", "completionsPath", "isActive"} <= set(first)

    # 同名再保存 = 覆盖更新，不新增
    assert _save(client, headers, _payload("主力"))["code"] == 200
    body = client.get(f"{MAIN}/api/user/model-config/list", headers=headers).json()
    assert len(body["data"]) == 2

    # 激活「备用」→ 仅其 isActive=1
    r = client.post(f"{MAIN}/api/user/model-config/activate",
                    params={"name": "备用"}, headers=headers).json()
    assert r["code"] == 200, r
    items = client.get(f"{MAIN}/api/user/model-config/list", headers=headers).json()["data"]
    active_names = [i["name"] for i in items if i["isActive"] == 1]
    assert active_names == ["备用"], items

    # 激活/删除不存在的配置 → 60001
    for act in ("activate", "delete"):
        r = client.post(f"{MAIN}/api/user/model-config/{act}",
                        params={"name": "不存在"}, headers=headers).json()
        assert r["code"] == 60001, (act, r)

    # 删除后列表减一
    r = client.post(f"{MAIN}/api/user/model-config/delete",
                    params={"name": "主力"}, headers=headers).json()
    assert r["code"] == 200, r
    assert len(client.get(f"{MAIN}/api/user/model-config/list", headers=headers).json()["data"]) == 1

    # 参数校验：缺 baseUrl/apiKey/model → 10002
    bad = _payload("坏配置")
    bad["apiKey"] = ""
    assert _save(client, headers, bad)["code"] == 10002

    # 自清理（用户 teardown 不覆盖本表）
    client.post(f"{MAIN}/api/user/model-config/delete", params={"name": "备用"}, headers=headers)


def test_internal_model_config(client: httpx_client, make_user) -> None:
    """internal 端点：正确 token 得明文；错误 token 拒绝；无配置/非数字 userId → null。"""
    user = make_user("mcfgint")
    headers = user["headers"]
    key = f"sk-mcfg-int-{make_suffix()}-secret9999"
    assert _save(client, headers, _payload("内测", key))["code"] == 200
    assert client.post(f"{MAIN}/api/user/model-config/activate",
                       params={"name": "内测"}, headers=headers).json()["code"] == 200

    # 正确 token：明文 key 与激活配置
    r = client.get(f"{MAIN}/api/internal/model-config",
                   params={"userId": str(user["id"])},
                   headers={"X-Internal-Token": INTERNAL_TOKEN}).json()
    assert r["code"] == 200, r
    assert r["data"] and r["data"]["apiKey"] == key, r
    assert r["data"]["model"] == "deepseek-chat"

    # 错误 token → 拒绝（不泄露 key）
    r = client.get(f"{MAIN}/api/internal/model-config",
                   params={"userId": str(user["id"])},
                   headers={"X-Internal-Token": "wrong-token"}).json()
    assert r["code"] != 200 and key not in str(r), r

    # 无配置用户 → data=None（8091 降级走默认客户端）
    other = make_user("mcfgint2")
    r = client.get(f"{MAIN}/api/internal/model-config",
                   params={"userId": str(other["id"])},
                   headers={"X-Internal-Token": INTERNAL_TOKEN}).json()
    assert r["code"] == 200 and r["data"] is None, r

    # 非数字 userId（8091 测试账号风格）→ data=None，不报错
    r = client.get(f"{MAIN}/api/internal/model-config",
                   params={"userId": "u_xxx"},
                   headers={"X-Internal-Token": INTERNAL_TOKEN}).json()
    assert r["code"] == 200 and r["data"] is None, r

    # 自清理
    client.post(f"{MAIN}/api/user/model-config/delete", params={"name": "内测"}, headers=headers)
