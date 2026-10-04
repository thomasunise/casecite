"""Role-permission service: defaults, overrides, guardrails, resolution."""

import json

import pytest
from app.services import permissions as perm


@pytest.fixture(autouse=True)
def _memory_store(monkeypatch):
    """Route instance-settings persistence to an in-memory dict."""
    store: dict[str, str] = {}

    async def get_secret(name):
        return store.get(name)

    async def set_secret(name, value):
        store[name] = value

    async def delete_secret(name):
        store.pop(name, None)

    import app.services.instance_settings as inst

    monkeypatch.setattr(inst, "get_secret", get_secret)
    monkeypatch.setattr(inst, "set_secret", set_secret)
    monkeypatch.setattr(inst, "delete_secret", delete_secret)
    perm.invalidate_cache()
    yield store
    perm.invalidate_cache()


async def test_defaults_shape():
    matrix = await perm.get_role_permissions()
    assert set(matrix.keys()) == set(perm.ROLES)
    all_keys = {p["key"] for p in perm.PERMISSIONS}
    assert matrix["admin"] == all_keys
    assert matrix["attorney"] == {k for k in all_keys if not k.startswith("admin.")}
    # Viewer is read-and-research by default
    assert "documents.upload" not in matrix["viewer"]
    assert "chat.use" in matrix["viewer"]


async def test_override_set_and_resolve(_memory_store):
    await perm.set_role_permissions("viewer", ["chat.use"])
    matrix = await perm.get_role_permissions()
    assert matrix["viewer"] == {"chat.use"}
    # Other roles untouched
    assert "contracts.use" in matrix["attorney"]


async def test_admin_keeps_locked_permission(_memory_store):
    # Trying to strip admin.users from admin silently re-adds it.
    await perm.set_role_permissions("admin", ["chat.use"])
    matrix = await perm.get_role_permissions()
    assert "admin.users" in matrix["admin"]
    assert "chat.use" in matrix["admin"]


async def test_unknown_role_and_permission_rejected():
    with pytest.raises(ValueError):
        await perm.set_role_permissions("superuser", ["chat.use"])
    with pytest.raises(ValueError):
        await perm.set_role_permissions("viewer", ["not.a.permission"])


async def test_effective_union_across_roles(_memory_store):
    await perm.set_role_permissions("viewer", ["chat.use"])
    perms = await perm.effective_permissions(["viewer", "paralegal"])
    # Union: paralegal grants contracts even though viewer doesn't
    assert "contracts.use" in perms
    assert "chat.use" in perms
    # Case-insensitive role matching
    assert await perm.effective_permissions(["Admin"]) == (await perm.get_role_permissions())[
        "admin"
    ]


async def test_reset_restores_defaults(_memory_store):
    await perm.set_role_permissions("attorney", ["chat.use"])
    await perm.reset_role_permissions()
    matrix = await perm.get_role_permissions()
    assert matrix["attorney"] == perm.DEFAULT_ROLE_PERMISSIONS["attorney"]


async def test_corrupt_stored_json_falls_back_to_defaults(_memory_store):
    _memory_store["role_permissions"] = "not json {"
    perm.invalidate_cache()
    matrix = await perm.get_role_permissions()
    assert matrix["attorney"] == perm.DEFAULT_ROLE_PERMISSIONS["attorney"]


async def test_unknown_keys_in_storage_dropped(_memory_store):
    _memory_store["role_permissions"] = json.dumps(
        {"viewer": ["chat.use", "ghost.permission"], "badrole": ["chat.use"]}
    )
    perm.invalidate_cache()
    matrix = await perm.get_role_permissions()
    assert matrix["viewer"] == {"chat.use"}
