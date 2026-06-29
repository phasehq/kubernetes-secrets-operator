package syncstate

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestNeedsSyncAndUpdate(t *testing.T) {
	cache := New(filepath.Join(t.TempDir(), "cache.json"))
	now := time.Date(2026, 6, 14, 12, 0, 0, 0, time.UTC)

	needs, err := cache.NeedsSync("default", "example", "uid", now, "hash-a")
	if err != nil {
		t.Fatalf("NeedsSync() error = %v", err)
	}
	if !needs {
		t.Fatal("first sync should be needed")
	}

	if err := cache.Update("default", "example", "uid", now, "hash-a"); err != nil {
		t.Fatalf("Update() error = %v", err)
	}

	needs, err = cache.NeedsSync("default", "example", "uid", now, "hash-a")
	if err != nil {
		t.Fatalf("NeedsSync() error = %v", err)
	}
	if needs {
		t.Fatal("unchanged timestamp and spec hash should not need sync")
	}

	needs, err = cache.NeedsSync("default", "example", "uid", now, "hash-b")
	if err != nil {
		t.Fatalf("NeedsSync() error = %v", err)
	}
	if !needs {
		t.Fatal("changed spec hash should need sync")
	}

	needs, err = cache.NeedsSync("default", "example", "uid", now.Add(time.Second), "hash-a")
	if err != nil {
		t.Fatalf("NeedsSync() error = %v", err)
	}
	if !needs {
		t.Fatal("newer timestamp should need sync")
	}
}

func TestLegacyTimestampEntryForcesSpecHashSync(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cache.json")
	if err := os.WriteFile(path, []byte(`{"default:example:uid":"2026-06-14T12:00:00Z"}`), 0o644); err != nil {
		t.Fatalf("WriteFile() error = %v", err)
	}

	cache := New(path)
	now := time.Date(2026, 6, 14, 12, 0, 0, 0, time.UTC)
	needs, err := cache.NeedsSync("default", "example", "uid", now, "hash-a")
	if err != nil {
		t.Fatalf("NeedsSync() error = %v", err)
	}
	if !needs {
		t.Fatal("legacy entries have no spec hash and should force one upgrade sync")
	}
}
