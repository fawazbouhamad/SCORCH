# Post-D6 release finalization - operator guide

This document describes `scripts/release/release_finalizer.py`, the tool that
performs the SCORCH v1.0.0 release finalization once - and only once - coauthor
Dr. Nasser Najibi has recorded durable written authorization to distribute the
author-created Figure 1 and Figure 4 artwork under CC BY 4.0.

**Status at the time of writing: the tooling is built and tested. It has NOT
been run against the repository in `finalize` mode. The artwork authorization
has not been recorded, so CC BY 4.0 over Figure 1 and Figure 4 remains PENDING
and NOT YET IN FORCE, exactly as every licence record in this repository
states.**

## 1. What the two modes do

| | `preflight` | `finalize` |
|---|---|---|
| writes to disk | never | only after every check passes |
| needs the authorization | no | yes, fetched live |
| safe to run now | yes | it will stop at the gate |

### `preflight` - read-only

```
python scripts/release/release_finalizer.py preflight \
  --repo-root <worktree> \
  --expect-branch chore/final-repository-cleanup \
  --expect-head <40-hex commit> \
  [--candidate-archive <zip>] \
  [--final-docx-dir <dir>] \
  [--aptos-font <ttf>] \
  [--format text|json|both]
```

Both reports go to **stdout**. Nothing is written anywhere, so redirect if you
want a file. Exit code is 0 when every invariant holds and 1 otherwise.

It verifies: the repository root, branch, HEAD and a clean tree; that
`origin/<head branch>` equals local HEAD; that `origin/main` and the `v1.0.0`
tag object and its peeled commit are all where the contract says; that the pull
request is open, draft, unmerged and pointed at the expected base and head;
the live D6 authorization status; the pinned SHA-256 of the Figure 1 and
Figure 4 assets and the archived-original and donor rasters; that all four
licence records still withhold the artwork grant; the eight-file /
fifty-six-reference identity map, including that no ninth tracked file carries
the identity; that the two protected historical records still carry the
superseded NetCDF hash they exist to record; the candidate archive's identity,
topology, self-coverage and NetCDF contract when one is supplied; the FINAL
DOCX fixture pair; and the pinned Aptos Regular face.

### `finalize` - gated and transactional

```
python scripts/release/release_finalizer.py finalize \
  --repo-root <worktree> \
  --expect-branch chore/final-repository-cleanup \
  --expect-head <40-hex commit> \
  --stage-dir <deposit staging root> \
  --final-docx-dir <dir> --aptos-font <ttf> \
  --confirm "FINALIZE SCORCH RELEASE"
```

In order: recheck every preflight invariant; fetch the authorization live;
build the archive twice in a temporary directory and require the two builds to
be byte-identical; verify topology, self-coverage and the NetCDF contract;
recompute filename, SHA-256, byte count and content-root hash **from the final
bytes**; confirm the twenty-one relocated members did not drift; plan the
eight-file identity update with per-field occurrence counts; copy the whole
repository to a disposable location, apply the edits there and run the full
test suite; require zero failures, errors, xfails, xpasses **and skips**; and
only then apply the edits to the real tree, transactionally.

## 2. The authorization gate

The only thing that satisfies the gate is a **live top-level comment on the
contracted pull request, authored by the contracted GitHub login, carrying the
exact authorization text** in `finalizer_contract.json`. The tool records the
permalink, comment id, login, created and updated timestamps, the exact body
and the SHA-256 of that body.

The comment is fetched twice: once in the listing, then re-fetched by id. A
comment that has since been deleted, edited or truncated fails on the second
read.

Not accepted, and not accepted *because they are not inputs at all*:
screenshots, pasted JSON, local evidence files, environment variables, command
line flags, and human attestation - including the operator's own. There is no
bypass in the code, and `tests/test_release_finalizer.py` asserts there is
none.

Hard wrapping of the comment is tolerated: whitespace is normalized on both
sides before comparison. Nothing else is.

## 3. Why the CC BY activation stops

`ccby_activation_plan.authored` in the contract is `false`, so `finalize`
stops with `CCBY_ACTIVATION_PLAN_UNAUTHORED`.

This is deliberate. Activating CC BY rewrites legal prose in four licence
records, and that prose belongs to the authors, not to the tooling. The
finalizer will not invent it. To proceed, an author adds exact `from`/`to`
pairs to `ccby_activation_plan.replacements` - each naming its file and the
exact number of occurrences expected - and sets `authored` to `true`. The tool
then applies them with the same structured, count-checked, transactional
machinery it uses for the archive identity, restricted to the four licence
records, and independently asserts that every third-party rights token
(GPL-3.0-only, the Copernicus notice and disclaimer, GHCN-Daily and ERA5)
survives at exactly its original count.

CC BY reaches the authors' own artwork. It reaches nothing else.

## 4. Records the tool will never rewrite

* `remediation/corrected/event_global_max_algorithm/build_manifest.json`
* `remediation/freeze/freeze_manifest_pre.json`

Both carry a superseded NetCDF hash as **historical fact**. No guard reads
them for current identity, and rewriting them would falsify provenance. They
are snapshotted at the start of every transaction and verified byte-for-byte
at the end; if either changes, the transaction rolls back.

The superseded archive on disk is likewise preserved, never overwritten.

## 5. Blocking codes you may see

| code | meaning |
|---|---|
| `RELEASE_BLOCKED_D6` | no qualifying authorization comment exists |
| `AUTHZ_WRONG_AUTHOR` / `AUTHZ_BODY_ALTERED` / `AUTHZ_WRONG_TARGET` | a comment exists but does not qualify |
| `GITHUB_API_UNAVAILABLE` | the comment could not be re-fetched |
| `APTOS_FONT_MISSING` / `APTOS_FONT_MISMATCH` | the pinned face is absent, or a different face was offered |
| `CCBY_ACTIVATION_PLAN_UNAUTHORED` | no author has written the activation wording |
| `GIT_TREE_DIRTY` / `GIT_BRANCH_MISMATCH` / `GIT_HEAD_MISMATCH` | the worktree is not where it must be |
| `GIT_MAIN_MOVED` / `GIT_TAG_MOVED` / `GIT_REMOTE_BRANCH_MISMATCH` | a reference moved since the contract was written |
| `PR_STATE_UNEXPECTED` | the pull request is no longer open, draft, unmerged and correctly targeted |
| `FIGURE_IDENTITY_MISMATCH` | a figure or donor raster is not the approved one |
| `PENDING_MARKER_COUNT` | the four licence records no longer all withhold the grant |
| `IDENTITY_MAPPING_MISMATCH` | the eight-file / fifty-six-reference map does not match the tree |
| `PROTECTED_RECORD_MODIFIED` | a historical record changed |
| `EDIT_*` | the planned identity update was not exact |
| `CIRCULAR_IDENTITY` | an identity-bearing record is inside the archive it names |
| `BUILD_NONDETERMINISTIC` | two builds from identical inputs differed |
| `SIDECAR_MEMBER_DRIFT` | a relocated member's bytes changed |
| `VALIDATION_RUN_FAILED` | the disposable run was not completely clean |

## 6. The pinned font

`tests/test_corrected_schematic_figures.py` pins the exact Aptos Regular face
by SHA-256. It is a non-redistributable Microsoft 365 cloud font. **No
substitute may be used** - the guard pins the face, not merely the metrics,
and a different face is a substitution rather than the pinned font. Until it
is provisioned legitimately, one honest skip remains, and a zero-skip result
must not be claimed. Release acceptance requires the pinned font and zero
skips.

## 7. What this tool never does

It never commits, pushes, merges, tags, creates a release, or touches the
Zenodo records. Those remain deliberate human actions, taken after the
authorization is recorded and this tool has reported success.
