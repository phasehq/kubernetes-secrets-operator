from utils.secret_referencing import build_secrets_index, resolve_all_secrets


class DummyPhase:
    def __init__(self):
        self.calls = 0

    def get(self, env_name, app_name=None, keys=None, path='/'):
        self.calls += 1
        key = keys[0]
        return [{"key": key, "value": f"resolved-{key}"}]


def test_build_secrets_index_groups_by_env_and_path():
    all_secrets = [
        {"environment": "production", "path": "/", "key": "API_KEY", "value": "123"},
        {"environment": "production", "path": "/db", "key": "PASSWORD", "value": "abc"},
    ]

    idx = build_secrets_index(all_secrets)

    assert idx["production"]["/"]["API_KEY"] == "123"
    assert idx["production"]["/db"]["PASSWORD"] == "abc"


def test_resolve_all_secrets_reuses_fetch_cache_for_missing_refs():
    phase = DummyPhase()
    all_secrets = [{"environment": "production", "path": "/", "key": "A", "value": "x"}]
    idx = build_secrets_index(all_secrets)
    fetch_cache = {}

    value = "${staging.SECRET} and ${staging.SECRET}"
    resolved = resolve_all_secrets(
        value=value,
        all_secrets=all_secrets,
        phase=phase,
        current_application_name="my-app",
        current_env_name="production",
        secrets_dict=idx,
        fetch_cache=fetch_cache,
    )

    assert resolved == "resolved-SECRET and resolved-SECRET"
    assert phase.calls == 1
