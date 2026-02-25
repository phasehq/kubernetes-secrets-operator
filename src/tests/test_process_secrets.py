import base64
import pytest
from main import process_secrets


def b64(value: str) -> str:
    """Helper to base64 encode a string, matching what process_secrets does for plain type."""
    return base64.b64encode(value.encode()).decode()


# ---------------------------------------------------------------------------
# Basic value processing (type: plain / base64)
# ---------------------------------------------------------------------------

class TestValueProcessing:
    """Tests for secret value encoding based on processor type."""

    def test_plain_default_base64_encodes(self):
        """Default type is 'plain' — value should be base64 encoded."""
        result = process_secrets(
            {"API_KEY": "my-secret-value"},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"API_KEY": b64("my-secret-value")}

    def test_explicit_plain_type(self):
        result = process_secrets(
            {"API_KEY": "my-secret-value"},
            processors={"API_KEY": {"type": "plain"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"API_KEY": b64("my-secret-value")}

    def test_base64_type_no_re_encode(self):
        """type: base64 means value is already encoded — should NOT be re-encoded."""
        already_encoded = b64("raw-cert-data")
        result = process_secrets(
            {"TLS_CERT": already_encoded},
            processors={"TLS_CERT": {"type": "base64"}},
            secret_type="kubernetes.io/tls",
            name_transformer="upper_snake",
        )
        assert result == {"TLS_CERT": already_encoded}

    def test_unknown_type_falls_back_to_plain(self):
        """Unknown processor type should default to base64 encoding (same as plain)."""
        result = process_secrets(
            {"KEY": "value"},
            processors={"KEY": {"type": "unknown_type"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"KEY": b64("value")}

    def test_empty_value(self):
        """Empty string should be base64 encoded to empty string's encoding."""
        result = process_secrets(
            {"EMPTY": ""},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"EMPTY": b64("")}

    def test_multiline_value(self):
        """Multiline values like certificates or SSH keys."""
        pem = "-----BEGIN CERTIFICATE-----\nMIIBxTCCAW...\n-----END CERTIFICATE-----"
        result = process_secrets(
            {"CERT": pem},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"CERT": b64(pem)}

    def test_json_value(self):
        """JSON string values should be encoded as-is."""
        json_val = '{"host":"db.example.com","port":5432}'
        result = process_secrets(
            {"DB_CONFIG": json_val},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"DB_CONFIG": b64(json_val)}

    def test_value_with_special_chars(self):
        """Values with special characters (passwords, connection strings)."""
        password = "p@$$w0rd!#%^&*()=+"
        result = process_secrets(
            {"DB_PASSWORD": password},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"DB_PASSWORD": b64(password)}

    def test_unicode_value(self):
        """Unicode characters in secret values."""
        result = process_secrets(
            {"GREETING": "こんにちは"},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"GREETING": b64("こんにちは")}

    def test_long_value(self):
        """Large secret values (e.g. base64 encoded files)."""
        long_value = "A" * 100_000
        result = process_secrets(
            {"BIG_SECRET": long_value},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"BIG_SECRET": b64(long_value)}


# ---------------------------------------------------------------------------
# asName processor
# ---------------------------------------------------------------------------

class TestAsName:
    """Tests for the asName processor — explicit key renaming."""

    def test_basic_rename(self):
        result = process_secrets(
            {"PKCS12_PRIVATE_KEY": "cert-data"},
            processors={"PKCS12_PRIVATE_KEY": {"asName": "tls.crt"}},
            secret_type="kubernetes.io/tls",
            name_transformer="upper_snake",
        )
        assert "tls.crt" in result
        assert "PKCS12_PRIVATE_KEY" not in result

    def test_tls_secret_full_example(self):
        """Full TLS secret example from docs — PKCS12 certs."""
        cert_data = b64("raw-cert")
        key_data = b64("raw-key")
        result = process_secrets(
            {"PKCS12_PRIVATE_KEY": cert_data, "PKCS12_CERTIFICATE": key_data},
            processors={
                "PKCS12_PRIVATE_KEY": {"asName": "tls.crt", "type": "base64"},
                "PKCS12_CERTIFICATE": {"asName": "tls.key", "type": "base64"},
            },
            secret_type="kubernetes.io/tls",
            name_transformer="upper_snake",
        )
        assert result == {"tls.crt": cert_data, "tls.key": key_data}

    def test_asname_preserves_exact_casing(self):
        """asName should be used exactly as specified — no transformation."""
        result = process_secrets(
            {"APPLICATION_ID": "some-id"},
            processors={"APPLICATION_ID": {"asName": "appLICATion_ID"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "appLICATion_ID" in result

    def test_asname_with_dots(self):
        """Kubernetes secret keys can contain dots (e.g. tls.crt, app.config)."""
        result = process_secrets(
            {"APP_CONFIG": "config-data"},
            processors={"APP_CONFIG": {"asName": "app.config"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "app.config" in result

    def test_asname_takes_priority_over_name_transformer(self):
        """asName should always win over nameTransformer, even if both could apply."""
        result = process_secrets(
            {"SECRET_KEY": "value"},
            processors={"SECRET_KEY": {"asName": "myCustomName"}},
            secret_type="Opaque",
            name_transformer="camel",  # Would produce 'secretKey' but asName wins
        )
        assert "myCustomName" in result
        assert "secretKey" not in result

    def test_asname_takes_priority_over_per_key_transformer(self):
        """asName wins over per-key nameTransformer too."""
        result = process_secrets(
            {"SECRET_KEY": "value"},
            processors={
                "SECRET_KEY": {
                    "asName": "myCustomName",
                    "nameTransformer": "camel",
                }
            },
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "myCustomName" in result


# ---------------------------------------------------------------------------
# nameTransformer — secret-level (applies to all keys)
# ---------------------------------------------------------------------------

class TestSecretLevelNameTransformer:
    """Tests for nameTransformer at the managedSecretReferences level."""

    def test_camel_all_keys(self):
        result = process_secrets(
            {"DATABASE_URL": "postgres://...", "API_KEY": "abc123"},
            processors={},
            secret_type="Opaque",
            name_transformer="camel",
        )
        assert set(result.keys()) == {"databaseUrl", "apiKey"}

    def test_upper_camel_all_keys(self):
        result = process_secrets(
            {"DATABASE_URL": "postgres://...", "API_KEY": "abc123"},
            processors={},
            secret_type="Opaque",
            name_transformer="upper-camel",
        )
        assert set(result.keys()) == {"DatabaseUrl", "ApiKey"}

    def test_lower_snake_all_keys(self):
        result = process_secrets(
            {"DATABASE_URL": "val", "API_KEY": "val"},
            processors={},
            secret_type="Opaque",
            name_transformer="lower-snake",
        )
        assert set(result.keys()) == {"database_url", "api_key"}

    def test_lower_kebab_all_keys(self):
        result = process_secrets(
            {"DATABASE_URL": "val", "API_KEY": "val"},
            processors={},
            secret_type="Opaque",
            name_transformer="lower-kebab",
        )
        assert set(result.keys()) == {"database-url", "api-key"}

    def test_tf_var_all_keys(self):
        result = process_secrets(
            {"DATABASE_URL": "val", "API_KEY": "val"},
            processors={},
            secret_type="Opaque",
            name_transformer="tf-var",
        )
        assert set(result.keys()) == {"TF_VAR_database_url", "TF_VAR_api_key"}

    def test_upper_snake_default_no_change(self):
        """Default 'upper_snake' is unknown format — keys stay as-is."""
        result = process_secrets(
            {"DATABASE_URL": "val", "API_KEY": "val"},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert set(result.keys()) == {"DATABASE_URL", "API_KEY"}


# ---------------------------------------------------------------------------
# nameTransformer — per-key (in processors)
# ---------------------------------------------------------------------------

class TestPerKeyNameTransformer:
    """Tests for nameTransformer set per-key within processors."""

    def test_per_key_camel(self):
        result = process_secrets(
            {"APPLICATION_REGION": "us-east-1"},
            processors={"APPLICATION_REGION": {"nameTransformer": "camel"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "applicationRegion" in result

    def test_per_key_upper_camel(self):
        """The exact case from the user's bug report."""
        result = process_secrets(
            {"APPLICATION_REGION": "us-east-1"},
            processors={"APPLICATION_REGION": {"nameTransformer": "upper-camel"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "ApplicationRegion" in result

    def test_per_key_overrides_secret_level(self):
        """Per-key nameTransformer should override the secret-level default."""
        result = process_secrets(
            {"KEY_A": "val", "KEY_B": "val"},
            processors={"KEY_A": {"nameTransformer": "upper-camel"}},
            secret_type="Opaque",
            name_transformer="camel",  # KEY_B gets camel, KEY_A gets upper-camel
        )
        assert "KeyA" in result       # per-key upper-camel
        assert "keyB" in result        # secret-level camel

    def test_per_key_lower_kebab(self):
        result = process_secrets(
            {"DATABASE_HOST": "localhost"},
            processors={"DATABASE_HOST": {"nameTransformer": "lower-kebab"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "database-host" in result

    def test_per_key_tf_var(self):
        result = process_secrets(
            {"AWS_REGION": "us-east-1"},
            processors={"AWS_REGION": {"nameTransformer": "tf-var"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "TF_VAR_aws_region" in result


# ---------------------------------------------------------------------------
# Mixed processors — asName + nameTransformer + type combinations
# ---------------------------------------------------------------------------

class TestMixedProcessors:
    """Tests combining asName, nameTransformer, and type across multiple keys."""

    def test_user_reported_scenario(self):
        """The exact scenario from the user's bug report."""
        result = process_secrets(
            {
                "APPLICATION_REGION": "us-east-1",
                "APPLICATION_ID": "app-123",
            },
            processors={
                "APPLICATION_REGION": {"nameTransformer": "upper-camel"},
                "APPLICATION_ID": {"asName": "appLICATion_ID"},
            },
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "ApplicationRegion" in result
        assert "appLICATion_ID" in result
        assert result["ApplicationRegion"] == b64("us-east-1")
        assert result["appLICATion_ID"] == b64("app-123")

    def test_mixed_asname_transformer_and_default(self):
        """Three keys: one with asName, one with per-key transformer, one with default."""
        result = process_secrets(
            {
                "DB_HOST": "localhost",
                "DB_PORT": "5432",
                "DB_PASSWORD": "secret",
            },
            processors={
                "DB_HOST": {"asName": "database-host"},
                "DB_PORT": {"nameTransformer": "camel"},
            },
            secret_type="Opaque",
            name_transformer="lower-kebab",  # DB_PASSWORD gets this
        )
        assert "database-host" in result   # asName
        assert "dbPort" in result          # per-key camel
        assert "db-password" in result     # secret-level lower-kebab

    def test_base64_with_name_transformer(self):
        """type: base64 combined with nameTransformer."""
        cert = b64("raw-cert-data")
        result = process_secrets(
            {"TLS_CERT": cert},
            processors={"TLS_CERT": {"type": "base64", "nameTransformer": "lower-kebab"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"tls-cert": cert}

    def test_all_processor_fields_together(self):
        """asName + type together (asName wins for key name)."""
        cert = b64("raw-cert-data")
        result = process_secrets(
            {"PKCS12_KEY": cert},
            processors={"PKCS12_KEY": {"asName": "tls.key", "type": "base64"}},
            secret_type="kubernetes.io/tls",
            name_transformer="camel",
        )
        assert result == {"tls.key": cert}

    def test_realistic_multi_secret_deployment(self):
        """A realistic scenario with many secrets and different processor configs."""
        secrets = {
            "DATABASE_URL": "postgres://user:pass@db:5432/app",
            "DATABASE_PASSWORD": "s3cr3t!",
            "REDIS_HOST": "redis.internal",
            "REDIS_PORT": "6379",
            "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
            "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "TLS_CERTIFICATE": b64("cert-pem-data"),
            "APP_VERSION": "1.2.3",
        }
        processors = {
            "TLS_CERTIFICATE": {"asName": "tls.crt", "type": "base64"},
            "DATABASE_PASSWORD": {"nameTransformer": "camel"},
        }
        result = process_secrets(
            secrets,
            processors=processors,
            secret_type="Opaque",
            name_transformer="upper_snake",  # default — no change for most keys
        )
        # asName
        assert "tls.crt" in result
        assert result["tls.crt"] == b64("cert-pem-data")
        # per-key nameTransformer
        assert "databasePassword" in result
        # default keys unchanged
        assert "DATABASE_URL" in result
        assert "REDIS_HOST" in result
        assert "AWS_ACCESS_KEY_ID" in result
        assert "APP_VERSION" in result


# ---------------------------------------------------------------------------
# Empty / edge-case inputs
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases for process_secrets."""

    def test_no_secrets(self):
        result = process_secrets({}, processors={}, secret_type="Opaque", name_transformer="upper_snake")
        assert result == {}

    def test_no_processors(self):
        """All keys should pass through with default encoding."""
        result = process_secrets(
            {"A": "1", "B": "2"},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert set(result.keys()) == {"A", "B"}
        assert result["A"] == b64("1")

    def test_processor_for_nonexistent_key(self):
        """Processors referencing keys not in fetched_secrets should be ignored."""
        result = process_secrets(
            {"REAL_KEY": "value"},
            processors={"NONEXISTENT_KEY": {"asName": "ghost"}},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "REAL_KEY" in result
        assert "ghost" not in result

    def test_single_secret(self):
        result = process_secrets(
            {"SOLO": "alone"},
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result == {"SOLO": b64("alone")}

    def test_many_secrets(self):
        """Large number of secrets processed correctly."""
        secrets = {f"KEY_{i}": f"value_{i}" for i in range(100)}
        result = process_secrets(
            secrets,
            processors={},
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert len(result) == 100
        assert result["KEY_0"] == b64("value_0")
        assert result["KEY_99"] == b64("value_99")

    def test_key_collision_from_different_transformers(self):
        """Two different source keys that map to the same output key — last one wins."""
        # SECRET_KEY and secret_key both transform to 'secretKey' with camel
        result = process_secrets(
            {"SECRET_KEY": "first", "secret_key": "second"},
            processors={},
            secret_type="Opaque",
            name_transformer="camel",
        )
        # Both map to 'secretKey' — dict will have whichever was processed last
        assert "secretKey" in result

    def test_key_collision_asname(self):
        """Two keys with asName mapping to the same output — last one wins."""
        result = process_secrets(
            {"KEY_A": "val_a", "KEY_B": "val_b"},
            processors={
                "KEY_A": {"asName": "same_name"},
                "KEY_B": {"asName": "same_name"},
            },
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert "same_name" in result
        assert len(result) == 1  # collision — one overwrites the other

    def test_values_are_correctly_paired_after_rename(self):
        """Ensure values follow their keys through renaming."""
        result = process_secrets(
            {"KEY_A": "value_a", "KEY_B": "value_b"},
            processors={
                "KEY_A": {"asName": "renamed_a"},
                "KEY_B": {"nameTransformer": "camel"},
            },
            secret_type="Opaque",
            name_transformer="upper_snake",
        )
        assert result["renamed_a"] == b64("value_a")
        assert result["keyB"] == b64("value_b")
