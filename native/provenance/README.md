# Offline provenance engine

This read-only executable is compiled into architecture-specific Windows wheels.
It does not execute a helper, authorize launch, or assert sandbox readiness.
Users do not need Go, GitHub CLI, an online verification service, or a compiler.

Build toolchain: Go 1.27.1, `CGO_ENABLED=0`, maximum build parallelism 6.
Cryptographic implementation: sigstore-go v1.3.0, source commit
`22d3691c7b8e0c5530fae3c05577690bfef5cd00` (Apache-2.0, `LICENSE.sigstore`).
Dependency versions and authenticated module checksums are fixed in go.mod/go.sum.

Build the original-license closure for the same GOOS/GOARCH/CGO settings as the
executable with `python tools/license_notices.py --go go --output NOTICES.txt`.
The command uses `go list -mod=readonly -deps -json .`, includes original
LICENSE/COPYING/NOTICE/PATENTS files from each linked package's module ancestry,
the Go runtime license and the compiled trust anchor license, and rejects missing
licenses or replaced modules. `license-review.json` additionally fixes the
reviewed module versions and original notice digests; unreviewed additions or
changed license bytes block distribution. This snapshot covers permissive
Apache-2.0, MIT and BSD code. The auxiliary `go-digest/LICENSE.docs` is CC-BY-SA-4.0,
retained for transparency; its upstream documentation is not linked/copied.
It creates a new generated output and refuses to
overwrite one. Test fixtures are source-only and retain their separate MIT notice.

The compiled `trusted_root.json` is the reviewed public-good trust anchor from
sigstore/root-signing commit `53b521c505a79aef0e7ef089e05eb6b68b2e9854`,
`targets/trusted_root.json`, 6787 bytes, SHA-256
`6494e21ea73fa7ee769f85f57d5a3e6a08725eae1e38c755fc3517c9e6bc0b66`.
Root-signing uses Apache-2.0. Pinning and reviewing these bytes does not claim
authenticated TUF metadata verification. Root/key rotation requires reviewed
package updates and replay of the real signature tests. No runtime root override
or HTTP fallback exists. This compiled root and verifier are part of the
installed package trust base; they cannot authenticate replacement of their own
wheel. Adjacent hashes detect corruption only.

Public test fixture provenance and license are recorded in testdata/SOURCES.md.
Local cross-compilation is not evidence of native Windows execution or full R2/R3
acceptance; those require the installed-wheel native CI gates.
