package syncstate

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"time"
)

const DefaultPath = "/tmp/phase_sync_status.json"

type Entry struct {
	Timestamp time.Time `json:"timestamp"`
	SpecHash  string    `json:"spec_hash"`
}

type Cache struct {
	path string
	mu   sync.Mutex
}

func New(path string) *Cache {
	if path == "" {
		path = DefaultPath
	}
	return &Cache{path: path}
}

func Key(namespace, name, uid string) string {
	return namespace + ":" + name + ":" + uid
}

func (c *Cache) NeedsSync(namespace, name, uid string, current time.Time, specHash string) (bool, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	entries, err := c.readLocked()
	if err != nil {
		return true, err
	}

	entry, ok := entries[Key(namespace, name, uid)]
	if !ok {
		return true, nil
	}
	if entry.SpecHash != specHash {
		return true, nil
	}
	return current.After(entry.Timestamp), nil
}

func (c *Cache) Update(namespace, name, uid string, timestamp time.Time, specHash string) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	entries, err := c.readLocked()
	if err != nil {
		return err
	}
	entries[Key(namespace, name, uid)] = Entry{Timestamp: timestamp, SpecHash: specHash}
	return c.writeLocked(entries)
}

func (c *Cache) readLocked() (map[string]Entry, error) {
	if err := os.MkdirAll(filepath.Dir(c.path), 0o755); err != nil {
		return nil, err
	}

	data, err := os.ReadFile(c.path)
	if errors.Is(err, os.ErrNotExist) {
		return map[string]Entry{}, nil
	}
	if err != nil {
		return nil, err
	}
	if len(data) == 0 {
		return map[string]Entry{}, nil
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		_ = c.writeLocked(map[string]Entry{})
		return map[string]Entry{}, nil
	}

	entries := make(map[string]Entry, len(raw))
	for key, value := range raw {
		var entry Entry
		if err := json.Unmarshal(value, &entry); err == nil && !entry.Timestamp.IsZero() {
			entries[key] = entry
			continue
		}

		var legacyTimestamp string
		if err := json.Unmarshal(value, &legacyTimestamp); err != nil {
			continue
		}
		parsed, err := time.Parse(time.RFC3339Nano, legacyTimestamp)
		if err != nil {
			continue
		}
		entries[key] = Entry{Timestamp: parsed}
	}

	return entries, nil
}

func (c *Cache) writeLocked(entries map[string]Entry) error {
	data, err := json.MarshalIndent(entries, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(c.path, data, 0o644)
}
