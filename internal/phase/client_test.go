package phase

import (
	"fmt"
	"testing"
	"time"

	sdknetwork "github.com/phasehq/golang-sdk/v2/phase/network"
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
