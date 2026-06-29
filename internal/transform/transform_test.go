package transform

import (
	"encoding/base64"
	"testing"

	phasev1 "github.com/phasehq/kubernetes-secrets-operator/api/v1alpha1"
)

func TestName(t *testing.T) {
	tests := map[string]struct {
		format string
		want   string
	}{
		"unknown preserves key": {format: "upper_snake", want: "DATABASE_URL"},
		"camel":                 {format: "camel", want: "databaseUrl"},
		"upper camel":           {format: "upper-camel", want: "DatabaseUrl"},
		"lower snake":           {format: "lower-snake", want: "database_url"},
		"tf var":                {format: "tf-var", want: "TF_VAR_database_url"},
		"lower kebab":           {format: "lower-kebab", want: "database-url"},
	}

	for name, tt := range tests {
		t.Run(name, func(t *testing.T) {
			if got := Name("DATABASE_URL", tt.format); got != tt.want {
				t.Fatalf("Name() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestProcessSecrets(t *testing.T) {
	encoded := base64.StdEncoding.EncodeToString([]byte("certificate"))

	got, err := ProcessSecrets(
		map[string]string{
			"API_KEY":             "secret",
			"PKCS12_CERTIFICATE":  encoded,
			"DATABASE_URL":        "postgres://example",
			"COLLIDING_KEY":       "first",
			"COLLIDING_KEY_AGAIN": "second",
		},
		map[string]phasev1.Processor{
			"API_KEY":             {AsName: "api.key"},
			"PKCS12_CERTIFICATE":  {AsName: "tls.crt", Type: "base64"},
			"DATABASE_URL":        {NameTransformer: "camel"},
			"COLLIDING_KEY":       {AsName: "same"},
			"COLLIDING_KEY_AGAIN": {AsName: "same"},
		},
		"upper_snake",
	)
	if err != nil {
		t.Fatalf("ProcessSecrets() error = %v", err)
	}

	assertBytes(t, got, "api.key", "secret")
	assertBytes(t, got, "tls.crt", "certificate")
	assertBytes(t, got, "databaseUrl", "postgres://example")
	assertBytes(t, got, "same", "second")
}

func TestProcessSecretsRejectsInvalidBase64(t *testing.T) {
	_, err := ProcessSecrets(
		map[string]string{"CERT": "not base64"},
		map[string]phasev1.Processor{"CERT": {Type: "base64"}},
		"upper_snake",
	)
	if err == nil {
		t.Fatal("expected invalid base64 error")
	}
}

func assertBytes(t *testing.T, got map[string][]byte, key, want string) {
	t.Helper()
	if string(got[key]) != want {
		t.Fatalf("got[%q] = %q, want %q", key, string(got[key]), want)
	}
}
