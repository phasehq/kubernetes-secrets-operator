import pytest
from utils.misc import transform_name


class TestCamelCase:
    """Tests for the 'camel' nameTransformer (camelCase output)."""

    def test_basic(self):
        assert transform_name("SECRET_KEY", "camel") == "secretKey"

    def test_single_word(self):
        assert transform_name("SECRET", "camel") == "secret"

    def test_three_words(self):
        assert transform_name("DATABASE_CONNECTION_STRING", "camel") == "databaseConnectionString"

    def test_many_words(self):
        assert transform_name("AWS_ACCESS_KEY_ID", "camel") == "awsAccessKeyId"

    def test_single_char_words(self):
        assert transform_name("A_B_C", "camel") == "aBC"

    def test_already_lowercase(self):
        assert transform_name("already_lower", "camel") == "alreadyLower"

    def test_mixed_case_input(self):
        """Keys from Phase are typically UPPER_SNAKE, but mixed case should still work."""
        assert transform_name("Mixed_Case_Key", "camel") == "mixedCaseKey"

    def test_numeric_segments(self):
        assert transform_name("API_V2_ENDPOINT", "camel") == "apiV2Endpoint"

    def test_trailing_underscore(self):
        """Trailing underscore produces an empty last segment."""
        assert transform_name("SECRET_KEY_", "camel") == "secretKey"

    def test_leading_underscore(self):
        """Leading underscore produces an empty first segment — first real word gets capitalized."""
        assert transform_name("_SECRET_KEY", "camel") == "SecretKey"


class TestUpperCamel:
    """Tests for the 'upper-camel' nameTransformer (PascalCase output)."""

    def test_basic(self):
        assert transform_name("SECRET_KEY", "upper-camel") == "SecretKey"

    def test_single_word(self):
        assert transform_name("SECRET", "upper-camel") == "Secret"

    def test_three_words(self):
        assert transform_name("APPLICATION_REGION", "upper-camel") == "ApplicationRegion"

    def test_many_words(self):
        assert transform_name("AWS_SECRET_ACCESS_KEY", "upper-camel") == "AwsSecretAccessKey"

    def test_numeric_segments(self):
        assert transform_name("REDIS_DB_0_HOST", "upper-camel") == "RedisDb0Host"

    def test_single_char_words(self):
        assert transform_name("A_B_C", "upper-camel") == "ABC"

    def test_user_reported_bug(self):
        """The exact case from the user bug report - APPLICATION_REGION with upper-camel."""
        assert transform_name("APPLICATION_REGION", "upper-camel") == "ApplicationRegion"


class TestLowerSnake:
    """Tests for the 'lower-snake' nameTransformer (lower_snake_case output)."""

    def test_basic(self):
        assert transform_name("SECRET_KEY", "lower-snake") == "secret_key"

    def test_single_word(self):
        assert transform_name("SECRET", "lower-snake") == "secret"

    def test_already_lower(self):
        assert transform_name("secret_key", "lower-snake") == "secret_key"

    def test_many_words(self):
        assert transform_name("DATABASE_CONNECTION_STRING", "lower-snake") == "database_connection_string"


class TestTfVar:
    """Tests for the 'tf-var' nameTransformer (TF_VAR_ prefix, lowercase)."""

    def test_basic(self):
        assert transform_name("SECRET_KEY", "tf-var") == "TF_VAR_secret_key"

    def test_single_word(self):
        assert transform_name("SECRET", "tf-var") == "TF_VAR_secret"

    def test_many_words(self):
        assert transform_name("DATABASE_HOST", "tf-var") == "TF_VAR_database_host"

    def test_numeric(self):
        assert transform_name("API_V2_KEY", "tf-var") == "TF_VAR_api_v2_key"


class TestDotnetEnv:
    """Tests for the 'dotnet-env' nameTransformer (DotNet__Section format)."""

    def test_basic(self):
        assert transform_name("SECRET_KEY", "dotnet-env") == "Secret__Key"

    def test_single_word(self):
        assert transform_name("SECRET", "dotnet-env") == "Secret"

    def test_three_words(self):
        assert transform_name("DB_USER_NAME", "dotnet-env") == "Db__User__Name"


class TestLowerKebab:
    """Tests for the 'lower-kebab' nameTransformer (lower-kebab-case output)."""

    def test_basic(self):
        assert transform_name("SECRET_KEY", "lower-kebab") == "secret-key"

    def test_single_word(self):
        assert transform_name("SECRET", "lower-kebab") == "secret"

    def test_many_words(self):
        assert transform_name("DATABASE_CONNECTION_STRING", "lower-kebab") == "database-connection-string"

    def test_numeric(self):
        assert transform_name("API_V2_ENDPOINT", "lower-kebab") == "api-v2-endpoint"


class TestDefaultBehavior:
    """Tests for unknown/default format — key should be returned as-is."""

    def test_upper_snake_default(self):
        """The default nameTransformer in the CR is 'upper_snake' which is not a recognized format."""
        assert transform_name("SECRET_KEY", "upper_snake") == "SECRET_KEY"

    def test_unknown_format(self):
        assert transform_name("SECRET_KEY", "nonexistent") == "SECRET_KEY"

    def test_empty_format(self):
        assert transform_name("SECRET_KEY", "") == "SECRET_KEY"

    def test_none_format(self):
        """None format should return key as-is (falls through to else)."""
        assert transform_name("SECRET_KEY", None) == "SECRET_KEY"


class TestEdgeCases:
    """Edge cases for transform_name."""

    def test_empty_key(self):
        assert transform_name("", "camel") == ""

    def test_single_char_key(self):
        assert transform_name("X", "camel") == "x"

    def test_single_char_key_upper_camel(self):
        assert transform_name("X", "upper-camel") == "X"

    def test_numeric_only_key(self):
        assert transform_name("123", "camel") == "123"

    def test_numeric_words(self):
        assert transform_name("123_456", "camel") == "123456"

    def test_key_with_numbers(self):
        assert transform_name("REDIS_6379_PORT", "camel") == "redis6379Port"

    def test_preserves_original_on_unknown_format(self):
        """Keys with unusual casing should be preserved as-is for unknown formats."""
        assert transform_name("MyWeirdKey", "upper_snake") == "MyWeirdKey"

    def test_consecutive_underscores(self):
        """Double underscores create empty segments - this is a known edge case."""
        result = transform_name("DB__HOST", "camel")
        # split('_') on 'db__host' gives ['db', '', 'host']
        # empty string capitalize() is '', so we get 'db' + '' + 'Host' = 'dbHost'
        assert result == "dbHost"
