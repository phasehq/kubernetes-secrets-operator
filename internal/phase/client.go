package phase

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"strconv"
	"sync"
	"time"

	phasesdk "github.com/phasehq/golang-sdk/v2/phase"
	"github.com/phasehq/golang-sdk/v2/phase/misc"
	"github.com/phasehq/golang-sdk/v2/phase/network"
	"golang.org/x/sync/singleflight"
)

type Client struct {
	debug       bool
	retries     int
	backoff     time.Duration
	cacheTTL    time.Duration
	mu          sync.Mutex
	metaCache   map[string]metadataCacheEntry
	secretCache map[string]secretsCacheEntry
	group       singleflight.Group
}

func NewFromEnv() *Client {
	debug := boolEnv("PHASE_DEBUG", false)
	misc.VerifySSL = boolEnv("PHASE_VERIFY_SSL", true)
	network.SetUserAgent("phase-kubernetes-operator-go")

	return &Client{
		debug:       debug,
		retries:     intEnv("PHASE_OPERATOR_HTTP_RETRIES", 5),
		backoff:     durationSecondsEnv("PHASE_OPERATOR_HTTP_BACKOFF", time.Second),
		cacheTTL:    durationSecondsEnv("PHASE_OPERATOR_SOURCE_CACHE_TTL", 10*time.Second),
		metaCache:   map[string]metadataCacheEntry{},
		secretCache: map[string]secretsCacheEntry{},
	}
}

func (c *Client) EnvironmentUpdatedAt(ctx context.Context, token, host, appName, appID, envName string) (time.Time, error) {
	cacheKey := c.cacheKey("metadata", token, host, appName, appID, envName)
	if updatedAt, ok := c.cachedMetadata(cacheKey); ok {
		return updatedAt, nil
	}

	value, err, _ := c.group.Do(cacheKey, func() (interface{}, error) {
		if updatedAt, ok := c.cachedMetadata(cacheKey); ok {
			return updatedAt, nil
		}

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
		c.setMetadata(cacheKey, updatedAt)
		return updatedAt, nil
	})
	if err != nil {
		return time.Time{}, err
	}
	return value.(time.Time), nil
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

func (c *Client) GetSecrets(ctx context.Context, token, host, appName, appID, envName, path, tag string) (map[string]string, error) {
	cacheKey := c.cacheKey("secrets", token, host, appName, appID, envName, path, tag)
	if secrets, ok := c.cachedSecrets(cacheKey); ok {
		return secrets, nil
	}

	value, err, _ := c.group.Do(cacheKey, func() (interface{}, error) {
		if secrets, ok := c.cachedSecrets(cacheKey); ok {
			return secrets, nil
		}

		result := map[string]string{}
		err := c.withRetry(ctx, func() error {
			p, err := phasesdk.New(token, host, c.debug)
			if err != nil {
				return err
			}

			secrets, err := p.Get(phasesdk.GetOptions{
				AppName: appName,
				AppID:   appID,
				EnvName: envName,
				Path:    path,
				Tag:     tag,
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
		c.setSecrets(cacheKey, result)
		return cloneSecrets(result), nil
	})
	if err != nil {
		return nil, err
	}
	return cloneSecrets(value.(map[string]string)), nil
}

type metadataCacheEntry struct {
	value     time.Time
	expiresAt time.Time
}

type secretsCacheEntry struct {
	value     map[string]string
	expiresAt time.Time
}

func (c *Client) cachedMetadata(key string) (time.Time, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	entry, ok := c.metaCache[key]
	if !ok || time.Now().After(entry.expiresAt) {
		return time.Time{}, false
	}
	return entry.value, true
}

func (c *Client) setMetadata(key string, value time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.metaCache[key] = metadataCacheEntry{value: value, expiresAt: time.Now().Add(c.cacheTTL)}
}

func (c *Client) cachedSecrets(key string) (map[string]string, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	entry, ok := c.secretCache[key]
	if !ok || time.Now().After(entry.expiresAt) {
		return nil, false
	}
	return cloneSecrets(entry.value), true
}

func (c *Client) setSecrets(key string, value map[string]string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.secretCache[key] = secretsCacheEntry{value: cloneSecrets(value), expiresAt: time.Now().Add(c.cacheTTL)}
}

func (c *Client) cacheKey(parts ...string) string {
	if len(parts) > 1 {
		sum := sha256.Sum256([]byte(parts[1]))
		parts[1] = fmt.Sprintf("%x", sum[:])
	}
	data, _ := json.Marshal(parts)
	return string(data)
}

func cloneSecrets(input map[string]string) map[string]string {
	output := make(map[string]string, len(input))
	for key, value := range input {
		output[key] = value
	}
	return output
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
