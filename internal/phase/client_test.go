package phase

import (
	"fmt"
	"runtime"
	"strings"
	"testing"
	"time"

	sdknetwork "github.com/phasehq/golang-sdk/v2/phase/network"

	"github.com/phasehq/kubernetes-secrets-operator/internal/version"
)

func TestRetryAfterDelay(t *testing.T) {
	rateErr := &sdknetwork.RateLimitError{RetryAfter: 7 * time.Second}
	if got := retryAfterDelay(rateErr); got != 7*time.Second {
		t.Fatalf("retryAfterDelay(rate limit) = %s, want 7s", got)
	}

	apiErr := &sdknetwork.APIError{StatusCode: 503, RetryAfter: 3 * time.Second}
	if got := retryAfterDelay(fmt.Errorf("wrapped: %w", apiErr)); got != 3*time.Second {
		t.Fatalf("retryAfterDelay(api error) = %s, want 3s", got)
	}

	if got := retryAfterDelay(fmt.Errorf("plain error")); got != 0 {
		t.Fatalf("retryAfterDelay(plain error) = %s, want 0", got)
	}
}

func TestUserAgentFormat(t *testing.T) {
	ua := userAgent()
	prefix := "phase-kubernetes-operator/" + version.Version + " "
	if !strings.HasPrefix(ua, prefix) {
		t.Fatalf("userAgent() = %q, want prefix %q", ua, prefix)
	}
	if !strings.Contains(ua, runtime.GOOS+" "+runtime.GOARCH) {
		t.Fatalf("userAgent() = %q, want os/arch %q", ua, runtime.GOOS+" "+runtime.GOARCH)
	}
}
