package main

import (
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
)

const maxArtifactBytes int64 = 64 << 20
const maxBundleBytes int64 = 2 << 20
const failureMessage = "icode_provenance: verification_failed\n"

// Reviewed package trust anchor, not a runtime trust-root selector.
//
//go:embed trusted_root.json
var productionRoot []byte

func readSnapshot(path string, limit int64) ([]byte, error) {
	deny := errors.New("verification failed")
	before, err := os.Lstat(path)
	if err != nil || !before.Mode().IsRegular() || before.Size() < 1 || before.Size() > limit {
		return nil, deny
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, deny
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil || !opened.Mode().IsRegular() || !os.SameFile(before, opened) || opened.Size() != before.Size() {
		return nil, deny
	}
	data, err := io.ReadAll(io.LimitReader(file, limit+1))
	after, statErr := file.Stat()
	pathAfter, pathErr := os.Lstat(path)
	if err != nil || statErr != nil || pathErr != nil || !pathAfter.Mode().IsRegular() || !os.SameFile(opened, pathAfter) || len(data) < 1 || int64(len(data)) > limit || after.Size() != int64(len(data)) || after.Size() != opened.Size() {
		return nil, deny
	}
	return data, nil
}

type request struct{ Artifact, Bundle, SourceSHA, Arch string }

func writeReceipt(stdout io.Writer, artifact []byte, r request) error {
	digest := sha256.Sum256(artifact)
	receipt := struct {
		SchemaVersion      int    `json:"schema_version"`
		ProvenanceVerified bool   `json:"provenance_verified"`
		LaunchAuthorized   bool   `json:"launch_authorized"`
		ArtifactSHA256     string `json:"artifact_sha256"`
		SourceSHA          string `json:"source_sha"`
		Architecture       string `json:"architecture"`
	}{1, true, false, hex.EncodeToString(digest[:]), r.SourceSHA, r.Arch}
	data, err := json.Marshal(receipt)
	if err != nil {
		return err
	}
	_, err = stdout.Write(append(data, '\n'))
	return err
}

func parseRequest(args []string) (request, error) {
	deny := errors.New("verification failed")
	if len(args) != 8 {
		return request{}, deny
	}
	values := make(map[string]string, 4)
	for i := 0; i < len(args); i += 2 {
		key, value := args[i], args[i+1]
		if value == "" || values[key] != "" {
			return request{}, deny
		}
		switch key {
		case "--artifact", "--bundle", "--source-sha", "--arch":
		default:
			return request{}, deny
		}
		values[key] = value
	}
	r := request{values["--artifact"], values["--bundle"], values["--source-sha"], values["--arch"]}
	if r.Arch != "x64" && r.Arch != "arm64" {
		return request{}, deny
	}
	if filepath.Base(r.Artifact) != "icode-sandbox-windows-"+r.Arch+".exe" || len(r.SourceSHA) != 40 {
		return request{}, deny
	}
	for _, c := range r.SourceSHA {
		if !(c >= '0' && c <= '9' || c >= 'a' && c <= 'f') {
			return request{}, deny
		}
	}
	return r, nil
}

func runCLI(args []string, stdout, stderr io.Writer) (code int) {
	// A malformed untrusted proof must not disclose an SDK panic or stack trace.
	defer func() {
		if recover() != nil {
			io.WriteString(stderr, failureMessage)
			code = 78
		}
	}()
	deny := func() int { io.WriteString(stderr, failureMessage); return 78 }
	r, err := parseRequest(args)
	if err != nil {
		return deny()
	}
	artifact, err := readSnapshot(r.Artifact, maxArtifactBytes)
	if err != nil {
		return deny()
	}
	proof, err := readSnapshot(r.Bundle, maxBundleBytes)
	if err != nil {
		return deny()
	}
	if verifySignedArtifact(artifact, proof, productionRoot, icodeIdentity(r.SourceSHA), filepath.Base(r.Artifact)) != nil {
		return deny()
	}
	if writeReceipt(stdout, artifact, r) != nil {
		return deny()
	}
	return 0
}

func main() { os.Exit(runCLI(os.Args[1:], os.Stdout, os.Stderr)) }
