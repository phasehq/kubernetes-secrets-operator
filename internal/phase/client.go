package phase

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/user"
	"runtime"
	"strconv"
	"strings"
	"time"

	phasesdk "github.com/phasehq/golang-sdk/v2/phase"
	"github.com/phasehq/golang-sdk/v2/phase/misc"
	"github.com/phasehq/golang-sdk/v2/phase/network"

	"github.com/phasehq/kubernetes-secrets-operator/internal/version"
)

type Client struct {
	debug   bool
	retries int
	backoff time.Duration
}

func NewFromEnv() *Client {
	debug := boolEnv("PHASE_DEBUG", false)
	misc.VerifySSL = boolEnv("PHASE_VERIFY_SSL", true)
	network.SetUserAgent(userAgent())

	return &Client{
		debug:   debug,
		retries: intEnv("PHASE_OPERATOR_HTTP_RETRIES", 5),
		backoff: durationSecondsEnv("PHASE_OPERATOR_HTTP_BACKOFF", time.Second),
	}
}

func (c *Client) EnvironmentUpdatedAt(ctx context.Context, token, host, appName, appID, envName string) (time.Time, error) {
	var updatedAt time.Time
	err := c.withRetry(ctx, func() error {
		p, err := phasesdk.New(token, host, c.debug)
		if err != nil {
			return err
		}

		resp, err := network.FetchPhaseUser(p.TokenType, p.AppToken, p.Host)
		if err != nil {
			return err
		}
		defer resp.Body.Close()

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			return err
		}

		var userData misc.AppKeyResponse
		if err := json.Unmarshal(body, &userData); err != nil {
			return err
		}
		var timestampData appKeyTimestamps
		if err := json.Unmarshal(body, &timestampData); err != nil {
			return err
		}

		_, _, _, envID, _, err := misc.PhaseGetContext(&userData, appName, envName, appID)
		if err != nil {
			return err
		}
		for _, app := range timestampData.Apps {
			for _, envKey := range app.EnvironmentKeys {
				if envKey.Environment.ID != envID {
					continue
				}
				updatedAtValue := envKey.Environment.UpdatedAt
				if updatedAtValue == "" {
					updatedAtValue = envKey.UpdatedAt
				}
				if updatedAtValue == "" {
					return fmt.Errorf("phase environment %q has no updated_at timestamp", envID)
				}
				parsed, err := time.Parse(time.RFC3339Nano, updatedAtValue)
				if err != nil {
					return fmt.Errorf("parse phase environment updated_at %q: %w", updatedAtValue, err)
				}
				updatedAt = parsed
				return nil
			}
		}
		return fmt.Errorf("phase environment %q not found in metadata", envID)
	})
	if err != nil {
		return time.Time{}, err
	}
	return updatedAt, nil
}

type appKeyTimestamps struct {
	Apps []struct {
		EnvironmentKeys []struct {
			UpdatedAt   string `json:"updated_at"`
			Environment struct {
				ID        string `json:"id"`
				UpdatedAt string `json:"updated_at"`
			} `json:"environment"`
		} `json:"environment_keys"`
	} `json:"apps"`
}

func (c *Client) GetSecrets(ctx context.Context, token, host, appName, appID, envName, path, tag string, failOnReferenceError bool) (map[string]string, error) {
	result := map[string]string{}
	err := c.withRetry(ctx, func() error {
		p, err := phasesdk.New(token, host, c.debug)
		if err != nil {
			return err
		}

		secrets, err := p.Get(phasesdk.GetOptions{
			AppName:                        appName,
			AppID:                          appID,
			EnvName:                        envName,
			Path:                           path,
			Tag:                            tag,
			FailOnReferenceResolutionError: failOnReferenceError,
		})
		if err != nil {
			return err
		}

		flattened := make(map[string]string, len(secrets))
		for _, secret := range secrets {
			flattened[secret.Key] = secret.Value
		}
		result = flattened
		return nil
	})
	if err != nil {
		return nil, err
	}
	return result, nil
}

func (c *Client) withRetry(ctx context.Context, fn func() error) error {
	var lastErr error
	attempts := c.retries + 1
	for attempt := 0; attempt < attempts; attempt++ {
		if err := ctx.Err(); err != nil {
			return err
		}
		if err := fn(); err != nil {
			lastErr = err
			if attempt < attempts-1 {
				sleep := c.backoff * time.Duration(attempt+1)
				if delay := retryAfterDelay(err); delay > 0 {
					sleep = delay
				}
				log.Printf("phase API call failed, retrying in %s: %v", sleep, err)
				timer := time.NewTimer(sleep)
				select {
				case <-ctx.Done():
					timer.Stop()
					return ctx.Err()
				case <-timer.C:
				}
			}
			continue
		}
		return nil
	}
	return lastErr
}

func retryAfterDelay(err error) time.Duration {
	var rateErr *network.RateLimitError
	if errors.As(err, &rateErr) && rateErr.RetryAfter > 0 {
		return rateErr.RetryAfter
	}
	var apiErr *network.APIError
	if errors.As(err, &apiErr) && apiErr.RetryAfter > 0 {
		return apiErr.RetryAfter
	}
	return 0
}

func boolEnv(name string, fallback bool) bool {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func intEnv(name string, fallback int) int {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed < 0 {
		return fallback
	}
	return parsed
}

func durationSecondsEnv(name string, fallback time.Duration) time.Duration {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil || parsed < 0 {
		return fallback
	}
	return time.Duration(parsed * float64(time.Second))
}

// userAgent builds the User-Agent sent to the Phase API, e.g.
// "phase-kubernetes-operator/2.0.0 linux amd64 nonroot@<pod>". The user@host
func userAgent() string {
	parts := []string{
		"phase-kubernetes-operator/" + version.Version,
		runtime.GOOS + " " + runtime.GOARCH,
	}
	if u, err := user.Current(); err == nil {
		if host, err := os.Hostname(); err == nil {
			parts = append(parts, u.Username+"@"+host)
		}
	}
	return strings.Join(parts, " ")
}
