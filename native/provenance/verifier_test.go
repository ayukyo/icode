package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"

	in_toto "github.com/in-toto/attestation/go/v1"
)

func fixture(t *testing.T, name string) []byte {
	t.Helper()
	if name == "artifact" {
		name = "artifact.base64"
	}
	data, err := os.ReadFile("testdata/" + name)
	if err != nil {
		t.Fatal(err)
	}
	if name == "artifact.base64" {
		data, err = base64.StdEncoding.DecodeString(strings.TrimSpace(string(data)))
		if err != nil {
			t.Fatal(err)
		}
	}
	return data
}

func fixtureIdentity() identityPolicy {
	return identityPolicy{
		SAN:       "https://github.com/github/artifact-attestations-workflows/.github/workflows/attest.yml@09b495c3f12c7881b3cc17209a327792065c1a1d",
		Issuer:    "https://token.actions.githubusercontent.com",
		SignerSHA: "09b495c3f12c7881b3cc17209a327792065c1a1d",
		SourceURI: "https://github.com/malancas/attest-demo", SourceSHA: "95baf27389e83e6a5c48f42e190d48d7abcea19e",
		SourceRef: "refs/heads/main", RepositoryID: "804070735", OwnerID: "16248153", Runner: "github-hosted",
	}
}

func TestAuthenticUpstreamArtifact(t *testing.T) {
	err := verifySignedArtifact(fixture(t, "artifact"), fixture(t, "bundle.json"), fixture(t, "trusted-root.json"), fixtureIdentity(), "github_provenance_demo-0.0.0-py3-none-any.whl")
	if err != nil {
		t.Fatalf("authentic signed upstream artifact must verify: %v", err)
	}
}

func TestEmbeddedProductionRootAuthenticatesPublicFixture(t *testing.T) {
	if err := verifySignedArtifact(fixture(t, "artifact"), fixture(t, "bundle.json"), productionRoot, fixtureIdentity(), fixtureSubject); err != nil {
		t.Fatalf("reviewed compiled root must authenticate real public fixture: %v", err)
	}
}

func TestDuplicateJSONFieldsAreDenied(t *testing.T) {
	proof := bytes.Replace(fixture(t, "bundle.json"), []byte(`"mediaType":`), []byte(`"mediaType":"application/vnd.dev.sigstore.bundle.v0.3+json","mediaType":`), 1)
	if bytes.Equal(proof, fixture(t, "bundle.json")) {
		t.Fatal("fixture mutation did not occur")
	}
	if verifySignedArtifact(fixture(t, "artifact"), proof, fixture(t, "trusted-root.json"), fixtureIdentity(), fixtureSubject) == nil {
		t.Fatal("duplicate security fields must be denied")
	}
}

const fixtureSubject = "github_provenance_demo-0.0.0-py3-none-any.whl"

func mutateProof(t *testing.T, change func(map[string]any)) []byte {
	t.Helper()
	var value map[string]any
	if err := json.Unmarshal(fixture(t, "bundle.json"), &value); err != nil {
		t.Fatal(err)
	}
	change(value)
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func entries(value map[string]any) []any {
	return value["verificationMaterial"].(map[string]any)["tlogEntries"].([]any)
}

func TestRealCryptoRejectsTampering(t *testing.T) {
	tests := []struct {
		name                  string
		artifact, proof, root []byte
		id                    identityPolicy
		subject               string
	}{
		{"wrong artifact", []byte("tampered"), fixture(t, "bundle.json"), fixture(t, "trusted-root.json"), fixtureIdentity(), fixtureSubject},
		{"wrong subject", fixture(t, "artifact"), fixture(t, "bundle.json"), fixture(t, "trusted-root.json"), fixtureIdentity(), "other.exe"},
		{"trailing JSON", fixture(t, "artifact"), append(fixture(t, "bundle.json"), []byte("{}")...), fixture(t, "trusted-root.json"), fixtureIdentity(), fixtureSubject},
		{"malformed", fixture(t, "artifact"), []byte("{"), fixture(t, "trusted-root.json"), fixtureIdentity(), fixtureSubject},
		{"bad root", fixture(t, "artifact"), fixture(t, "bundle.json"), []byte("{}"), fixtureIdentity(), fixtureSubject},
	}
	for _, field := range []string{"SAN", "Issuer", "SignerSHA", "SourceURI", "SourceSHA", "SourceRef", "RepositoryID", "OwnerID", "Runner"} {
		id := fixtureIdentity()
		switch field {
		case "SAN":
			id.SAN += "wrong"
		case "Issuer":
			id.Issuer += "wrong"
		case "SignerSHA":
			id.SignerSHA = strings.Repeat("0", 40)
		case "SourceURI":
			id.SourceURI += "wrong"
		case "SourceSHA":
			id.SourceSHA = strings.Repeat("0", 40)
		case "SourceRef":
			id.SourceRef = "refs/heads/other"
		case "RepositoryID":
			id.RepositoryID = "1"
		case "OwnerID":
			id.OwnerID = "1"
		case "Runner":
			id.Runner = "self-hosted"
		}
		tests = append(tests, struct {
			name                  string
			artifact, proof, root []byte
			id                    identityPolicy
			subject               string
		}{field, fixture(t, "artifact"), fixture(t, "bundle.json"), fixture(t, "trusted-root.json"), id, fixtureSubject})
	}
	for _, mutation := range []struct {
		name   string
		change func(map[string]any)
	}{
		{"missing proof", func(v map[string]any) { delete(entries(v)[0].(map[string]any), "inclusionProof") }},
		{"missing checkpoint", func(v map[string]any) {
			delete(entries(v)[0].(map[string]any)["inclusionProof"].(map[string]any), "checkpoint")
		}},
		{"empty checkpoint", func(v map[string]any) {
			entries(v)[0].(map[string]any)["inclusionProof"].(map[string]any)["checkpoint"].(map[string]any)["envelope"] = ""
		}},
		{"signature", func(v map[string]any) {
			v["dsseEnvelope"].(map[string]any)["signatures"].([]any)[0].(map[string]any)["sig"] = base64.StdEncoding.EncodeToString(bytes.Repeat([]byte{1}, 70))
		}},
		{"unsigned integrated time", func(v map[string]any) { entries(v)[0].(map[string]any)["integratedTime"] = "1" }},
		{"no authenticated time", func(v map[string]any) { delete(entries(v)[0].(map[string]any), "inclusionPromise") }},
		{"trusted promise plus unknown proof", func(v map[string]any) {
			list := entries(v)
			raw, _ := json.Marshal(list[0])
			var other map[string]any
			_ = json.Unmarshal(raw, &other)
			other["logId"].(map[string]any)["keyId"] = base64.StdEncoding.EncodeToString(bytes.Repeat([]byte{0}, 32))
			delete(list[0].(map[string]any), "inclusionProof")
			v["verificationMaterial"].(map[string]any)["tlogEntries"] = append(list, other)
		}},
	} {
		tests = append(tests, struct {
			name                  string
			artifact, proof, root []byte
			id                    identityPolicy
			subject               string
		}{mutation.name, fixture(t, "artifact"), mutateProof(t, mutation.change), fixture(t, "trusted-root.json"), fixtureIdentity(), fixtureSubject})
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if verifySignedArtifact(tc.artifact, tc.proof, tc.root, tc.id, tc.subject) == nil {
				t.Fatal("tampered or mismatched signed artifact must be denied")
			}
		})
	}
}

func TestStatementSemanticContract(t *testing.T) {
	digest := sha256.Sum256(fixture(t, "artifact"))
	hash := fmt.Sprintf("%x", digest)
	valid := func() *in_toto.Statement {
		return &in_toto.Statement{Type: "https://in-toto.io/Statement/v1", PredicateType: "https://slsa.dev/provenance/v1", Subject: []*in_toto.ResourceDescriptor{{Name: fixtureSubject, Digest: map[string]string{"sha256": hash}}}}
	}
	if checkStatement(valid(), fixtureSubject, hash) != nil {
		t.Fatal("canonical single subject must pass semantic checks")
	}
	for _, tc := range []struct {
		name   string
		change func(*in_toto.Statement)
	}{
		{"wrong statement", func(s *in_toto.Statement) { s.Type = "https://in-toto.io/Statement/v0.1" }},
		{"wrong predicate", func(s *in_toto.Statement) { s.PredicateType = "https://other.invalid" }},
		{"missing subject", func(s *in_toto.Statement) { s.Subject = nil }},
		{"extra subject", func(s *in_toto.Statement) { s.Subject = append(s.Subject, s.Subject[0]) }},
		{"wrong name", func(s *in_toto.Statement) { s.Subject[0].Name = "other.exe" }},
		{"extra digest", func(s *in_toto.Statement) { s.Subject[0].Digest["sha512"] = "extra" }},
		{"wrong digest", func(s *in_toto.Statement) { s.Subject[0].Digest["sha256"] = strings.Repeat("0", 64) }},
		{"uppercase digest", func(s *in_toto.Statement) { s.Subject[0].Digest["sha256"] = strings.ToUpper(hash) }},
		{"nil subject", func(s *in_toto.Statement) { s.Subject[0] = nil }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			s := valid()
			tc.change(s)
			if checkStatement(s, fixtureSubject, hash) == nil {
				t.Fatal("noncanonical statement must be denied")
			}
		})
	}
	if checkStatement(nil, fixtureSubject, hash) == nil {
		t.Fatal("missing statement must be denied")
	}
}

func TestProductionIdentityIsCompleteAndFixed(t *testing.T) {
	sha := strings.Repeat("a", 40)
	id := icodeIdentity(sha)
	if id.SAN != "https://github.com/ayukyo/icode/.github/workflows/windows-helper-provenance.yml@refs/heads/main" || id.Issuer != "https://token.actions.githubusercontent.com" || id.SignerSHA != sha || id.SourceSHA != sha || id.SourceURI != "https://github.com/ayukyo/icode" || id.SourceRef != "refs/heads/main" || id.RepositoryID != "1381822597" || id.OwnerID != "7407460" || id.Runner != "github-hosted" {
		t.Fatalf("incomplete fixed production identity: %+v", id)
	}
	if verifySignedArtifact(fixture(t, "artifact"), fixture(t, "bundle.json"), fixture(t, "trusted-root.json"), id, fixtureSubject) == nil {
		t.Fatal("production identity must deny another legitimate release")
	}
}

func TestIncompleteIdentityIsDenied(t *testing.T) {
	for _, field := range []string{"SignerSHA", "SourceURI", "SourceSHA", "SourceRef", "RepositoryID", "OwnerID", "Runner"} {
		id := fixtureIdentity()
		switch field {
		case "SignerSHA":
			id.SignerSHA = ""
		case "SourceURI":
			id.SourceURI = ""
		case "SourceSHA":
			id.SourceSHA = ""
		case "SourceRef":
			id.SourceRef = ""
		case "RepositoryID":
			id.RepositoryID = ""
		case "OwnerID":
			id.OwnerID = ""
		case "Runner":
			id.Runner = ""
		}
		if verifySignedArtifact(fixture(t, "artifact"), fixture(t, "bundle.json"), fixture(t, "trusted-root.json"), id, fixtureSubject) == nil {
			t.Fatalf("incomplete identity must not become wildcard: %s", field)
		}
	}
}

func TestAuthenticOversizedProofIsDenied(t *testing.T) {
	proof := fixture(t, "bundle.json")
	proof = append(proof, bytes.Repeat([]byte(" "), int(maxBundleBytes)+1-len(proof))...)
	if verifySignedArtifact(fixture(t, "artifact"), proof, fixture(t, "trusted-root.json"), fixtureIdentity(), fixtureSubject) == nil {
		t.Fatal("even otherwise authentic proof must respect the 2 MiB cap")
	}
}
