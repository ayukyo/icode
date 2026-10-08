package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestBoundedRegularSnapshot(t *testing.T) {
	path := filepath.Join(t.TempDir(), "artifact")
	if err := os.WriteFile(path, []byte("snapshot"), 0600); err != nil {
		t.Fatal(err)
	}
	data, err := readSnapshot(path, 8)
	if err != nil || string(data) != "snapshot" {
		t.Fatalf("regular bounded input must snapshot: data=%q err=%v", data, err)
	}
}

func TestCLIRejectsArgumentsWithoutDisclosingInput(t *testing.T) {
	for _, args := range [][]string{nil, {"--help"}, {"--artifact", "SECRET-PATH"}, {"--root", "SECRET-PATH"}, {"--arch", "x64", "--bundle", "SECRET-PATH", "--source-sha", strings.Repeat("a", 40), "--artifact", "SECRET-PATH"}} {
		var out, err bytes.Buffer
		if code := runCLI(args, &out, &err); code != 78 || out.Len() != 0 || err.String() != "icode_provenance: verification_failed\n" {
			t.Fatalf("unexpected public error: code=%d stdout=%q stderr=%q", code, out.String(), err.String())
		}
	}
}

func TestParseCanonicalRequest(t *testing.T) {
	sha := strings.Repeat("a", 40)
	for _, arch := range []string{"x64", "arm64"} {
		name := "icode-sandbox-windows-" + arch + ".exe"
		got, err := parseRequest([]string{"--artifact", name, "--bundle", "proof.json", "--source-sha", sha, "--arch", arch})
		if err != nil || got.Artifact != name || got.Bundle != "proof.json" || got.SourceSHA != sha || got.Arch != arch {
			t.Fatalf("valid canonical request must parse: %+v err=%v", got, err)
		}
	}
}

func TestSnapshotRejectsNonregularAndOversized(t *testing.T) {
	dir := t.TempDir()
	for _, tc := range []struct {
		name  string
		data  []byte
		limit int64
	}{{"empty", nil, 8}, {"large", []byte("123456789"), 8}} {
		p := filepath.Join(dir, tc.name)
		if err := os.WriteFile(p, tc.data, 0600); err != nil {
			t.Fatal(err)
		}
		if _, err := readSnapshot(p, tc.limit); err == nil {
			t.Fatal("invalid input must be denied")
		}
	}
	if _, err := readSnapshot(dir, 8); err == nil {
		t.Fatal("directory must be denied")
	}
	if _, err := readSnapshot(filepath.Join(dir, "absent"), 8); err == nil {
		t.Fatal("absent file must be denied")
	}
	link := filepath.Join(dir, "link")
	if err := os.Symlink(filepath.Join(dir, "large"), link); err == nil {
		if _, err := readSnapshot(link, 8); err == nil {
			t.Fatal("symbolic link must be denied")
		}
	}
}

func TestRejectMalformedRequest(t *testing.T) {
	base := []string{"--artifact", "icode-sandbox-windows-x64.exe", "--bundle", "proof.json", "--source-sha", strings.Repeat("a", 40), "--arch", "x64"}
	for _, tc := range []struct {
		index int
		value string
	}{{1, "helper.exe"}, {1, "icode-sandbox-windows-arm64.exe"}, {3, ""}, {5, strings.Repeat("A", 40)}, {5, strings.Repeat("a", 39)}, {5, strings.Repeat("g", 40)}, {7, "amd64"}, {6, "--bundle"}, {0, "--root"}} {
		args := append([]string(nil), base...)
		args[tc.index] = tc.value
		if _, err := parseRequest(args); err == nil {
			t.Fatalf("malformed request accepted: index=%d", tc.index)
		}
	}
	for _, args := range [][]string{append(append([]string(nil), base...), "extra"), base[:6]} {
		if _, err := parseRequest(args); err == nil {
			t.Fatal("unexpected extra/missing args accepted")
		}
	}
}

func TestSuccessReceiptDoesNotAuthorizeLaunch(t *testing.T) {
	var out bytes.Buffer
	r := request{SourceSHA: strings.Repeat("a", 40), Arch: "arm64"}
	if err := writeReceipt(&out, []byte("artifact"), r); err != nil {
		t.Fatal(err)
	}
	var got map[string]any
	if err := json.Unmarshal(out.Bytes(), &got); err != nil {
		t.Fatalf("success must emit bounded JSON receipt: %v", err)
	}
	if out.Len() > 511 || len(got) != 6 || got["schema_version"] != float64(1) || got["provenance_verified"] != true || got["launch_authorized"] != false || got["source_sha"] != r.SourceSHA || got["architecture"] != r.Arch || got["artifact_sha256"] != "c7c5c1d70c5dec4416ab6158afd0b223ef40c29b1dc1f97ed9428b94d4cadb1c" {
		t.Fatalf("unexpected authority/receipt: %s", out.String())
	}
}

func TestCLIRejectsOtherAuthenticReleaseWithoutDisclosingProof(t *testing.T) {
	dir := t.TempDir()
	artifact := filepath.Join(dir, "icode-sandbox-windows-x64.exe")
	proof := filepath.Join(dir, "SECRET-PROOF-PATH.json")
	if err := os.WriteFile(artifact, fixture(t, "artifact"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(proof, fixture(t, "bundle.json"), 0600); err != nil {
		t.Fatal(err)
	}
	var out, err bytes.Buffer
	code := runCLI([]string{"--artifact", artifact, "--bundle", proof, "--source-sha", fixtureIdentity().SourceSHA, "--arch", "x64"}, &out, &err)
	if code != 78 || out.Len() != 0 || err.String() != failureMessage {
		t.Fatalf("proof/identity rejection leaked or granted authority: code=%d stdout=%q stderr=%q", code, out.String(), err.String())
	}
}

func TestSnapshotEnforcesArtifactCapWithoutAllocating(t *testing.T) {
	path := filepath.Join(t.TempDir(), "oversized")
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := file.Truncate(maxArtifactBytes + 1); err != nil {
		file.Close()
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := readSnapshot(path, maxArtifactBytes); err == nil {
		t.Fatal("artifact over 64 MiB must be denied before reading")
	}
}
