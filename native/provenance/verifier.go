package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"

	in_toto "github.com/in-toto/attestation/go/v1"

	"github.com/sigstore/sigstore-go/pkg/bundle"
	"github.com/sigstore/sigstore-go/pkg/fulcio/certificate"
	"github.com/sigstore/sigstore-go/pkg/root"
	"github.com/sigstore/sigstore-go/pkg/verify"
)

var errVerification = errors.New("verification failed")

func verifySignedArtifact(artifact, proof, trustedRoot []byte, identity identityPolicy, subject string) error {
	if len(artifact) < 1 || int64(len(artifact)) > maxArtifactBytes || len(proof) < 1 || int64(len(proof)) > maxBundleBytes {
		return errVerification
	}
	for _, required := range []string{identity.SAN, identity.Issuer, identity.SignerSHA, identity.SourceURI, identity.SourceSHA, identity.SourceRef, identity.RepositoryID, identity.OwnerID, identity.Runner} {
		if required == "" {
			return errVerification
		}
	}
	trusted, err := root.NewTrustedRootFromJSON(trustedRoot)
	if err != nil {
		return errVerification
	}
	entity := &bundle.Bundle{}
	if err := entity.UnmarshalJSON(proof); err != nil {
		return errVerification
	}
	// Every entry must carry a proof. A proof for an unknown log must not be
	// paired with a trusted promise-only entry to satisfy two different gates.
	entries, err := entity.TlogEntries()
	if err != nil || len(entries) == 0 {
		return errVerification
	}
	for _, entry := range entries {
		if entry == nil || !entry.HasInclusionProof() {
			return errVerification
		}
		checkpoint := entry.TransparencyLogEntry().GetInclusionProof().GetCheckpoint()
		if checkpoint == nil || checkpoint.GetEnvelope() == "" {
			return errVerification
		}
	}
	san, err := verify.NewSANMatcher(identity.SAN, "")
	if err != nil {
		return errVerification
	}
	issuer, err := verify.NewIssuerMatcher(identity.Issuer, "")
	if err != nil {
		return errVerification
	}
	certIdentity, err := verify.NewCertificateIdentity(san, issuer, certificate.Extensions{
		BuildSignerURI: identity.SAN, BuildSignerDigest: identity.SignerSHA,
		RunnerEnvironment: identity.Runner, SourceRepositoryURI: identity.SourceURI,
		SourceRepositoryDigest: identity.SourceSHA, SourceRepositoryRef: identity.SourceRef,
		SourceRepositoryIdentifier: identity.RepositoryID, SourceRepositoryOwnerIdentifier: identity.OwnerID,
	})
	if err != nil {
		return errVerification
	}
	verifier, err := verify.NewVerifier(trusted, verify.WithObserverTimestamps(1), verify.WithSignedCertificateTimestamps(1), verify.WithTransparencyLog(1))
	if err != nil {
		return errVerification
	}
	result, err := verifier.Verify(entity, verify.NewPolicy(verify.WithArtifact(bytes.NewReader(artifact)), verify.WithCertificateIdentity(certIdentity)))
	if err != nil {
		return errVerification
	}
	digest := sha256.Sum256(artifact)
	return checkStatement(result.Statement, subject, hex.EncodeToString(digest[:]))
}

type identityPolicy struct {
	SAN, Issuer, SignerSHA, SourceURI, SourceSHA, SourceRef, RepositoryID, OwnerID, Runner string
}

func icodeIdentity(sourceSHA string) identityPolicy {
	return identityPolicy{
		SAN:    "https://github.com/ayukyo/icode/.github/workflows/windows-helper-provenance.yml@refs/heads/main",
		Issuer: "https://token.actions.githubusercontent.com", SignerSHA: sourceSHA, SourceSHA: sourceSHA,
		SourceURI: "https://github.com/ayukyo/icode", SourceRef: "refs/heads/main",
		RepositoryID: "1381822597", OwnerID: "7407460", Runner: "github-hosted",
	}
}

// This is a post-verification semantic check, never a signature substitute.
func checkStatement(stmt *in_toto.Statement, subject, digest string) error {
	if stmt == nil || stmt.GetType() != "https://in-toto.io/Statement/v1" || stmt.GetPredicateType() != "https://slsa.dev/provenance/v1" || len(stmt.GetSubject()) != 1 {
		return errVerification
	}
	item := stmt.GetSubject()[0]
	if item == nil || item.GetName() != subject || len(item.GetDigest()) != 1 || item.GetDigest()["sha256"] != digest {
		return errVerification
	}
	return nil
}
