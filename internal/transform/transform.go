package transform

import (
	"encoding/base64"
	"fmt"
	"log"
	"sort"
	"strings"

	phasev1 "github.com/phasehq/kubernetes-secrets-operator/api/v1alpha1"
)

func Name(secretKey, format string) string {
	words := strings.Split(strings.ToLower(secretKey), "_")

	switch format {
	case "camel":
		if len(words) == 0 {
			return ""
		}
		return words[0] + capitalizeAll(words[1:])
	case "upper-camel":
		return capitalizeAll(words)
	case "lower-snake":
		return strings.Join(words, "_")
	case "tf-var":
		return "TF_VAR_" + strings.Join(words, "_")
	case "lower-kebab":
		return strings.Join(words, "-")
	default:
		return secretKey
	}
}

func ProcessSecrets(fetched map[string]string, processors map[string]phasev1.Processor, nameTransformer string) (map[string][]byte, error) {
	if processors == nil {
		processors = map[string]phasev1.Processor{}
	}

	processed := map[string][]byte{}
	outputKeySources := map[string]string{}

	keys := make([]string, 0, len(fetched))
	for key := range fetched {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	for _, key := range keys {
		value := fetched[key]
		processor := processors[key]
		outputKey := key
		switch {
		case processor.AsName != "":
			outputKey = processor.AsName
		case processor.NameTransformer != "":
			outputKey = Name(key, processor.NameTransformer)
		default:
			outputKey = Name(key, nameTransformer)
		}

		if previous, ok := outputKeySources[outputKey]; ok {
			log.Printf("key collision: %q and %q both map to output key %q; %q will overwrite the previous value", key, previous, outputKey, key)
		}
		outputKeySources[outputKey] = key

		if processor.Type == "base64" {
			decoded, err := base64.StdEncoding.DecodeString(value)
			if err != nil {
				return nil, fmt.Errorf("processor for key %q is type base64 but value is not valid base64: %w", key, err)
			}
			processed[outputKey] = decoded
			continue
		}

		processed[outputKey] = []byte(value)
	}

	return processed, nil
}

func capitalizeAll(words []string) string {
	var b strings.Builder
	for _, word := range words {
		if word == "" {
			continue
		}
		b.WriteString(strings.ToUpper(word[:1]))
		if len(word) > 1 {
			b.WriteString(word[1:])
		}
	}
	return b.String()
}
