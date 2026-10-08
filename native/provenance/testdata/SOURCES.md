# Public signed test fixture

These are public verification inputs, not private keys or ICODE release artifacts.
Source: GitHub CLI v2.102.0, commit `fc4b137cdef0a6bd28fd461b7cf9c84a5812a8cd`,
`pkg/cmd/attestation/test/data/` (MIT; full license in `LICENSE.cli`).

- `bundle.json`: `reusable-workflow-attestation.sigstore.json`, 11346 bytes,
  upstream SHA-256 `88e35c3496fc9b9bd29629b69271bd32738e170f0d85a12d67da0c72c743f3bd`.
  The repository text snapshot adds one final LF: 11347 bytes, SHA-256
  `169b682676d10335da8916011bb4225c9771cf7c08697ef9e0b9b6720ab76f81`.
  Only outer JSON whitespace changes; signed DSSE payload bytes are unchanged.
- `artifact.base64`: base64 encoding of `reusable-workflow-artifact`, decoded
  2962 bytes, SHA-256 `49a3aa6075e0f49f82843e74b5baa614ad2a588e6675612bf108a0a008c5ac25`.
- `trusted-root.json`: `trusted_root.json`, 3806 bytes,
  SHA-256 `455b3fe53e2678889f093d66ebbfda5f12ebb9d682b146c3535fa04e97689787`.

The positive test verifies real artifact bytes, certificate, signed time, SCT,
DSSE, inclusion proof and checkpoint offline. The test root and release identity
are internal test inputs; the CLI has no means to select them.
