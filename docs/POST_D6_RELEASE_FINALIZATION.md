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
| writes to disk | never, including bytecode | only after every check passes |
| needs the authorization | no | yes, fetched live, twice |
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

Both reports go to **stdout**. Nothing is written anywhere - `preflight` sets
`sys.dont_write_bytecode` before importing anything, so it does not even leave
a `__pycache__` behind. Exit code is 0 when every invariant holds and 1
otherwise.

It verifies: the repository root, branch, HEAD and a clean tree; that
`origin/<head branch>` equals local HEAD; that `origin/main` and the `v1.0.0`
tag object and its peeled commit are all where the contract says; that the pull
request is open, draft, unmerged and pointed at the expected base and head;
the live D6 authorization status; the pinned SHA-256 of the Figure 1 and
Figure 4 assets and the archived-original and donor rasters; that all four
licence records still withhold the artwork grant, reported as an explicit
licensing STATE; the eight-file / fifty-six-reference identity map, including
that no ninth tracked file carries the identity; that the two protected
historical records still carry the superseded NetCDF hash they exist to record,
**and that their tracked git blobs are unmoved**; that the D6 receipt does not
already exist; the candidate archive's identity, topology, self-coverage,
NetCDF contract and agreement with the pinned technical source when one is
supplied; the FINAL DOCX fixture pair; and the pinned Aptos Regular face.

### `finalize` - gated and transactional

```
python scripts/release/release_finalizer.py finalize \
  --repo-root <worktree> \
  --expect-branch chore/final-repository-cleanup \
  --expect-head <40-hex commit> \
  --candidate-archive <the pinned pre-D6 candidate zip> \
  --release-staging <explicit destination directory> \
  --final-docx-dir <dir> --aptos-font <ttf> \
  --confirm "FINALIZE SCORCH RELEASE"
```

`--release-staging` is **required and explicit**. The destination is never
derived from the repository's parent directory.

## 2. The authorization gate

The only thing that satisfies the gate is a **live top-level issue comment on
the contracted pull request, authored by the contracted GitHub login, whose
whitespace-normalized body is EXACTLY EQUAL to the authorization text** in
`finalizer_contract.json`.

**Equality, not containment.** This is the difference that matters. Under a
containment rule, all of the following authorize the release, because each one
genuinely contains the required paragraph:

* the paragraph followed by *"However, I revoke this authorization."*
* the paragraph prefixed by *"DO NOT ACT ON THIS YET"*
* the paragraph quoted inside a comment that explicitly declines to give it

All of them are refused. Hard wrapping is still tolerated - whitespace is
normalized on both sides - and nothing else is.

**The LATEST comment by that author, not any comment by that author.** A grant
followed by the same author's revocation or qualification is refused with
`AUTHZ_SUPERSEDED_OR_QUALIFIED`. Accepting any historical exact match meant a
withdrawn grant still stood, because the withdrawal was never looked at.
Comments by *other* authors never supersede it - a stranger cannot withdraw
the copyright holder's permission, and cannot grant it either.

**Every page of comments is read.** The listing goes through `gh api
--paginate --slurp` with `per_page=100`, and the pages are flattened into one
sequence. Without it a pull request with more than a hundred comments returns
only the first page - and the comment most likely to land on a later page is
precisely a revocation posted after the grant.

The comment is fetched **live twice by id** after the listing that discovers
it, exact equality is required on both reads, and the two reads must agree with
each other on every field in `cross_read_agreement_fields` - id, body,
`created_at`, `updated_at`, permalink, `issue_url` and user. A comment deleted,
edited or truncated between the reads authorizes nothing. A pull request
**review** comment is a different object and is refused, as is a comment on
another pull request or in a fork.

The authorization is then **re-fetched and revalidated immediately before the
transaction writes**, because a check performed before an archive build is a
check of the past. That final re-read compares **every identity field the
receipt records** - comment id, login, body, body hash, `created_at`,
`updated_at`, permalink and `issue_url`. Comparing a subset let a comment
deleted and reposted with identical text, or edited so only its `updated_at`
moved, pass as "unchanged", and the receipt would then record a comment that
is not the one validation approved (`AUTHZ_CHANGED_BEFORE_WRITE`).

Not accepted, and not accepted *because they are not inputs at all*:
screenshots, pasted JSON, local evidence files, environment variables, command
line flags, and human attestation - including the operator's own. There is no
bypass in the code, and `tests/test_release_finalizer.py` asserts there is
none.

## 3. The contract production is allowed to trust

The contract decides who may authorize the release, what text counts as
authorization, which assets the licence reaches and what the activation may
touch. **There is no `--contract` option.** Production reads exactly one path,
`scripts/release/finalizer_contract.json`, inside the verified worktree, and
requires that it is tracked by git, that it resolves to that path with no link
or `..` escape, and that its bytes on disk equal the blob at HEAD. Unit tests
inject contracts by passing a dict to the Python functions, which is not an
operator-facing surface.

A contract cannot pin its own hash without circularity, so identity is verified
against git rather than against a constant stored inside it.

> While the finalizer repair is uncommitted, the working-tree contract differs
> from the blob at HEAD and production preflight reports
> `CONTRACT_NOT_AT_HEAD`. That is the intended behaviour, not a defect; once
> the repair is committed the two agree and the code no longer fires.

## 4. The durable authorization receipt

`docs/FIGURE_01_04_CC_BY_AUTHORIZATION_RECEIPT.json`

A stdout report is not a receipt. Once CC BY is in force over the artwork, the
repository must be able to show **which** comment, by **which** account, at
**which** time, over **which** files licensed it - years later, from the tree
alone, without the GitHub API and without this tool. The receipt records the
repository and pull request, the permalink and comment id, the exact login,
`created_at` and `updated_at`, the exact body and its SHA-256, all seven
licensed artwork paths with their hashes, the activation timestamp, and the
finalizer version and starting HEAD.

It is built and validated inside the disposable validation copy, then written
**atomically as part of the same transaction** as the licence and identity
edits. If any part of the transaction fails, the receipt is removed again. Its
presence is what the publication builder and the consistency guards read to
decide which licensing state the repository is in.

**It must not exist before a real authorization has been fetched.** `preflight`
fails with `RECEIPT_PREMATURE` if it does.

## 4a. One state module, and a receipt that must VALIDATE

`scripts/release/artwork_licence_state.py` is the single source of truth for
"is CC BY in force over the artwork?". The finalizer, the publication builder
and the repository guards all import it, so they cannot drift into disagreeing.

It exists because all three used to answer that question by asking whether a
receipt FILE EXISTED. A file with the right name containing
`{"schema_version": "1.0.0"}` was therefore enough to make the publication
builder assert an active CC BY licence over a coauthor's artwork.

ACTIVE now requires a receipt that **validates**: correct schema version,
repository and pull request; the exact contracted login; a body that is exactly
the contracted authorization text and whose recorded SHA-256 hashes it; a
`comment_id` that is a positive **integer**; `created_at`, `updated_at` and
`activated_at` that are **real parsed** UTC instants in a sensible order (a
regex accepts `2026-13-45T99:99:99Z`, which is not a date); a permalink that is
an **HTTPS github.com** comment whose fragment is exactly
`issuecomment-{comment_id}`; an `issue_url` exactly equal to
`https://api.github.com/repos/<owner>/<name>/issues/<n>`; and **exactly the
seven** contracted artwork paths whose recorded hashes still match the files on
disk. During a live finalization it must also agree with the comment fetched
moments earlier. Anything less is not ACTIVE.

### The receipt is opened by ONE fail-closed operation

Checking a pathname and then opening it are two operations, and the whole
attack on this file lives in the gap: `lstat` says regular file, the path is
swapped, the read follows the swap. The gap was **not** closed by asking for
`O_NOFOLLOW`, because **`O_NOFOLLOW` does not exist on Windows** - the flag was
requested through a `getattr` defaulting to zero, contributed nothing to the
flag word, and the "no-follow" read followed links exactly like an ordinary
`open()`. Swapping the checked receipt for a symlink to an external file and
reading the external bytes was reproducible.

There is now a single safe open. On Windows the repository root is opened
FIRST, with `CreateFileW` and `FILE_FLAG_OPEN_REPARSE_POINT`, and HELD OPEN for
the whole operation; then **every component below it** is opened and inspected
in turn with the same flag, so a junction anywhere along the path is refused at
the component that carries it - the same decision the POSIX walk makes. An
earlier revision opened only the final component as itself, which says nothing
whatever about `docs`. Each component opens **as itself** rather than as its
target; `GetFileInformationByHandle` refuses anything
carrying `FILE_ATTRIBUTE_REPARSE_POINT` (symlinks *and* directory junctions) or
`FILE_ATTRIBUTE_DIRECTORY`; `GetFileType` refuses pipes, consoles and character
devices; and `GetFinalPathNameByHandleW` reports the fully resolved path of the
object actually opened, which must be inside the repository. That last check is
what protects **every path component** - a junction on a parent directory is
invisible to any test of the final filename.

On POSIX the equivalent is stronger than a no-follow open of the final path,
because a no-follow open of the final path protects the final component and
nothing else. The repository root is opened once and **every component** is
then opened relative to the previous descriptor with
`O_DIRECTORY | O_NOFOLLOW` (`openat`), so a link anywhere along the chain is
refused by the kernel where it sits. Containment becomes **structural** - the
descriptor was reached from the root and never left it - so there is nothing to
compare and no path to resolve. The bytes are then read from **that handle**
and no other.

**No pathname is resolved after the open.** A `realpath` once the descriptor is
in hand is a second, independent question about a *name*, and its answer is not
required to describe the object the descriptor refers to. Both sides of the
Windows containment comparison therefore come from opened handles -
`GetFinalPathNameByHandleW` on the root and on the receipt - and neither is
passed back through `os.path.realpath`.

If the platform primitive is unavailable the operation **refuses**; there is no
weaker fallback. A refusal is reported as `RECEIPT_PATH_INVALID`, and the state
is never ACTIVE on a receipt that could not be opened safely.

### Classification is scoped to exact markers

`artwork_licence_markers` in the trusted contract lists the exact artwork
clauses. Classification used to scan whole documents for broad vocabulary -
`prohibited`, `must not`, `may not`, `no CC BY` - which matches a great deal of
legitimate unrelated prose: a "prohibited-region invariance" note, or a
sentence correctly stating that the underlying ERA5 data carries no CC BY
licence. That made records read as artwork-PENDING for reasons having nothing
to do with the artwork, and - because such sentences survive activation - it
made ACTIVE unreachable. Every unrelated ERA5, GHCN, Natural Earth, software
and font restriction is now invisible to the classifier.

**When the activation wording is authored, `artwork_licence_markers.active`
must be filled in at the same time**, or the classifier will not recognise it.

### ACTIVE is decided by whole blocks, never by containment

A registered PENDING marker is found by substring, because a document
containing one anywhere still withholds the grant. ACTIVE is not symmetric: a
document that *quotes* the grant in order to deny it contains the grant as a
substring. An active marker is therefore matched only as a **complete
normalized block** - a whole line, a whole sentence, or a whole table cell.
Cells are decomposed into sentences as well as lines, because a licence table
states the claim in a cell that also carries rights sentences the claim does
not touch, and splitting the row alone tears sentences across cell boundaries.

### A registrable ACTIVE marker is ONE anchored affirmative clause

Matching whole blocks is necessary and was not sufficient: the *shape* rule
that decides whether a marker may register at all was a set of independent
keyword **searches**, so a marker could satisfy every one of them while
granting nothing. Four clauses that used to register:

| Clause | Why it registered | Why it is not a grant |
| --- | --- | --- |
| `Figure 1 artwork is licensed under CC BY 4.0, and 4 copies exist.` | a bare `and 4` alternative counted as naming Figure 4 | it is a sentence about how many copies exist |
| `Figure 1 is licensed under CC BY 4.0. Figure 4 is discussed elsewhere.` | the two sentences together named both figures | only Figure 1 is licensed; Figure 4 is merely mentioned |
| `The project licenses data; Figure 1 and Figure 4 artwork and CC BY 4.0 are discussed.` | `the project licenses` counted as a granting verb | the grant is over *data*, by a different subject |
| `Figures 1 and 4 artwork is licensed under CC BY 4.0, although approval is required.` | no negation or conditional keyword matched | it states the grant and withdraws it in the same clause |

A registrable marker must now match **one anchored, simple affirmative
clause**: a subject that **jointly** identifies Figure 1 and Figure 4, a
present-tense copula, an affirmative granting participle, and CC BY 4.0 placed
in force over that subject - with nothing before the subject and nothing after
the licence except a trailing parenthetical. The bare `and 4` alternative is
gone, and so are the granting verbs whose subject is somebody other than the
artwork (`the project licenses…`, `we grant…`, `…applies to…`).

New refusal codes join the existing ones: `CCBY_ACTIVE_MARKER_COMPOUND` for
more than one clause, `CCBY_ACTIVE_MARKER_QUALIFIED` for concession and
contrast (`although`, `however`, `but`, `notwithstanding`…), and
`CCBY_ACTIVE_MARKER_UNGRAMMATICAL` for anything the anchored grammar does not
accept. An outstanding approval, authorization, permission or consent - in
either word order - is `CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE`.

A trailing **parenthetical is not decoration** - it qualifies the sentence it
hangs off - and the first version of the anchored grammar accepted any
parenthetical at all, so the qualification simply moved inside the brackets:

    Figures 1 and 4 are licensed under CC BY 4.0 (without authorization).
    Figures 1 and 4 are licensed under CC BY 4.0 (approval denied).
    Figures 1 and 4 are licensed under CC BY 4.0 (authorization revoked).
    Figures 1 and 4 are licensed under CC BY 4.0 (only after consent).
    Figures 1 and 4 are licensed under CC BY 4.0 (expires tomorrow).

Every one of those registered as a grant in force. Only **enumerated** contents
are now permitted (`ALLOWED_PARENTHETICALS`): an alias for the licence already
named in the predicate, and the `TEST-ONLY SYNTHETIC WORDING` decoration the
synthetic fixtures carry. Anything else is `CCBY_ACTIVE_MARKER_PARENTHETICAL`.

### TEST-ONLY wording may never reach production

The synthetic clause exists so the tests can drive the ACTIVE state without
anybody drafting licence prose. That is worth nothing if the same wording can
reach a production contract - the repository would then be asserting a
copyright licence over a coauthor's artwork in words that say, in themselves,
that they are not real.

A contract is a test fixture only if it **says so** (`synthetic_fixture:
true`). Silence means production, so the real contract cannot become
"synthetic" by omission. `synthetic_wording_issues()` scans the contract's
markers, its publication rows and its activation-plan replacements for the
`TEST-ONLY` token, and it is enforced where production actually happens: in the
production contract loader and in the activation planner, both refusing with
`CCBY_TESTONLY_WORDING_IN_PRODUCTION`. The real contract carries no such token
anywhere, and a test asserts that.

None of this authors anything. The real contract keeps
`artwork_licence_markers.active == []` and the state stays **PENDING**; the
rule governs what *could* be registered if the authors ever write the wording.

A registrable active marker must additionally be a complete affirmative scoped
clause. It is refused when it is:

* **generic** - `CC BY 4.0`, `in force`, `Figure 1`: tokens that also appear in
  sentences denying the grant (`CCBY_ACTIVE_MARKER_GENERIC`);
* **unscoped** - it does not name both the Figure 1 / Figure 4 artwork and the
  CC BY 4.0 licence (`CCBY_ACTIVE_MARKER_UNSCOPED`);
* **not affirmative** - it reads as a denial, exclusion or deferral
  (`CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE`). "Figure 1 and Figure 4 artwork is
  excluded from the CC BY 4.0 grant" is long, scoped and names the licence;
  only reading it as a denial tells it from a grant;
* **already present** before activation (`CCBY_ACTIVE_MARKER_PRE_EXISTING`).
  If the pre-activation records already classify ACTIVE, "the activation took
  effect" and "the activation did nothing" produce identical evidence.

Every authored destination block, on **all five** surfaces, must itself carry
a registered marker as a standalone block, or the record it produces would be
unclassifiable after activation (`CCBY_ACTIVE_MARKER_ABSENT`). The authored
`publication_outputs_artwork_row.active` is held to the same rule: an
activation nobody can publish is not a complete activation.

A receipt that is PRESENT but does not validate is a **refusal**, not a
PENDING answer: the standalone publication builder raises
`ARTWORK_RECEIPT_INVALID` rather than serving the pending row while a stub,
forged or half-written receipt sits in the tree.

`activated_at` defaults to the validated comment's **`updated_at`**, not its
`created_at`. The effective activation time is the moment the authorization
last stood as written, which for an edited comment is later than the moment it
was posted. Defaulting to `created_at` was wrong in both directions: an
authorization edited after posting would have carried
`activated_at < updated_at` and failed the receipt's own ordering rule, and a
receipt recording an activation earlier than the last edit to the text it
records would misstate what was authorized when. Using a comment timestamp
rather than the wall clock keeps the receipt validated in the disposable copy
byte-identical to the one written to the real tree, and makes the receipt
reproducible.

The publication builder no longer accepts injected licence prose. Both wordings
live in the trusted contract under `publication_outputs_artwork_row`; `active`
is `null`, so the builder refuses to render an active row until an author
writes one. `readme_text` has no parameter for passing licence text in - a
caller able to inject arbitrary wording into published output would be a way to
publish a licence claim nobody authored.

## 5. Licensing is a state machine with FIVE surfaces

| state | receipt | four tracked licence records | archive `LICENSE.txt` | builder emits |
|---|---|---|---|---|
| `pending` | absent | all withhold the grant | withholds the grant | pending wording |
| `active` | present and valid | all assert the grant | asserts the grant | active wording |

Anything else is `inconsistent` and is refused. Activating CC BY in the four
tracked records while shipping a deposit whose own `LICENSE.txt` still reads
PENDING publishes a contradiction, so the archive member transitions **with**
them or not at all.

The activation plan must cover all five surfaces; a partial plan is refused.
Each `from` block must be a complete source block occurring **exactly once** -
a bare marker such as `PENDING` is refused, because activation must not become
a global word replacement. `.zenodo.json` is re-parsed with duplicate-key
rejection, every third-party rights token must survive at exactly its original
count, and the licensed scope is exactly the seven pinned Figure 1 / Figure 4
assets.

A file may carry **both** the archive identity and the licence wording -
`assets/manuscript_final/README.md` does. Its edits are composed from a single
original snapshot and written once, rather than planned independently and
applied in sequence where the later write would discard the earlier one.

### Why the CC BY activation still stops

`ccby_activation_plan.authored` in the contract is `false`, so `finalize` stops
with `CCBY_ACTIVATION_PLAN_UNAUTHORED`. Activation rewrites legal prose, and
that prose belongs to the authors, not to the tooling. The publication builder
takes the same stance: in the active state it raises rather than inventing a
licence row nobody wrote.

CC BY reaches the authors' own artwork. It reaches nothing else.

## 6. How the final archive is built

The finalizer does **not** zip an arbitrary staging directory. It:

1. requires the exact pinned pre-D6 candidate as the **technical source** -
   a local, unpublished, pre-D6 working artifact that is *not* the released
   identity and *not* evidence of publication or deposit;
2. verifies its full SHA-256, byte count, content root and topology **once**,
   then copies those verified bytes into a private temporary snapshot and
   builds only from the snapshot, re-hashing it before and after both builds.
   Verifying a path and then reading it twice more is a time-of-check /
   time-of-use hole: the file can be replaced in between;
3. extracts it into temporary staging, with containment decided by
   `Path.relative_to` rather than a string prefix - `/tmp/extract-evil` is not
   inside `/tmp/extract`, however well the characters line up;
4. applies the authored archive `LICENSE.txt` transition;
5. regenerates `FILE_MANIFEST.csv`;
6. regenerates `SHA256SUMS`;
7. requires exactly 107 manifest rows, 108 checksum entries and 109 members;
8. executes the archive's own shipped `validate_deposit.py` and requires an
   **anchored** verdict: exit 0, exactly one whole-line verdict, and that line
   must be the last non-empty line and equal to `PASS`. Counting substrings is
   not enough - `BYPASS` and `COMPASS` both contain `PASS`. Silence, a `FAIL`
   line, mixed verdicts and duplicate passes are all refused. The contract
   pins this under `archive_topology.validator_verdict`, measured against the
   real deposit (66 lines, terminal `PASS`, exit 0);
9. re-runs the NetCDF metadata contract;
10. builds **twice from two independent fresh extractions** and requires the
    two ZIPs to be byte-identical;
11. recomputes the released identity from those final bytes only.

Two builds from the *same* staging directory prove the writer is deterministic
and nothing about the inputs. Two builds from independent extractions prove
what the double-build check was always supposed to prove.

Missing or corrupt archives, manifests and checksum files produce aggregated
issue codes, never a traceback.

## 7. Validation validates the release, not the ambient environment

The disposable run extracts the newly built final archive afresh, sets
`SCORCH_DATA_ARCHIVE`, `SCORCH_DATA_DIR` and `SCORCH_CANONICAL_DATA_DIR` to it
explicitly, sets the required DOCX, font and output paths, and **clears every
other `SCORCH_*` variable** along with `PYTEST_ADDOPTS`, `PYTHONPATH`,
`PYTEST_PLUGINS` and the plugin-autoload controls. Bytecode writing is off and
the cache provider is disabled.

The complete **collected node-ID set** and the **executed node-ID set** are
both recorded and compared. A run where they differ is `VALIDATION_INCOMPLETE`:
counts alone cannot distinguish "everything passed" from "everything that was
not quietly deselected passed".

Release acceptance requires zero failed, zero errors, zero skipped, zero
xfailed and zero xpassed.

The validation tree is an **independent clone at the expected head**, not a
copy of the worktree and not a copy of `.git`. `git clone --no-hardlinks
--no-checkout` gives the copy its own real `.git` **directory**, its own object
store, refs and index; the checkout then materialises the **committed** bytes
of the exact commit the run was invoked for. The clone's `HEAD`, its tracked
set and its tree identity are all verified against the source's committed tree
before a single planned edit is applied, and the fresh tree must be clean.

Three separate defects are closed here:

* `.git` is a **file**, not a directory, in a **linked worktree** - and this
  repository is checked out as one. Walking it as a directory tree refused
  every real run with `VALIDATION_TREE_UNBUILDABLE` before anything was
  validated at all.
* Copying tracked **worktree bytes** admitted whatever the checkout happened
  to be holding while the copy was being taken. A test neutered during
  preparation and restored immediately afterwards would have been validated
  and would have left nothing for the dirty-tree check to find. The worktree
  is now never read for content, so the window does not exist.
* Copying `.git` file-by-file also copied **live mutable state** - the index,
  `HEAD`, reflogs, any lock held at that instant.

A source at the wrong commit is `VALIDATION_TREE_HEAD_MISMATCH`; a clone whose
tree does not match is `VALIDATION_TREE_IDENTITY_MISMATCH`. A tracked
**symlink** (mode `120000`) is `VALIDATION_TREE_SYMLINK` and a **gitlink**
(mode `160000`) is `VALIDATION_TREE_SUBMODULE` - checked in the source **index**
and in the **committed tree**, because the index is what is about to be
released and the tree is what the copy will contain. Ignored artifacts are
admitted only through `validation_copy.ignored_allowlist`, and only at a pinned
SHA-256 - an entry without a pin is `VALIDATION_ALLOWLIST_UNPINNED` and one
whose bytes differ is `VALIDATION_ALLOWLIST_MISMATCH`. The list ships empty.

The child environment is **built by allowing variables through**, not by naming
bad ones, and it gets an **isolated `HOME`/`USERPROFILE`** created for the run.
`GIT_*`, `GH_*`, `PYTHON*`, `PYTEST*`, `SCORCH*`, coverage, XDG and matplotlib
controls are all absent, and `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` and
`MPLCONFIGDIR` are pointed inside the temporary home. A deny-list is only ever
as complete as the last person to think about it, and every entry that mattered
was found after the fact: `PYTHONOPTIMIZE` strips `assert` statements and this
suite *is* assert statements; `GIT_DIR` and `GIT_INDEX_FILE` point the
repository guards at a different repository entirely; `~/.gitconfig` can set
`core.hooksPath` or alias a git subcommand.

The **same** environment now covers the two places that were still inheriting
the operator's shell:

* **The shipped deposit validator.** It used to run under a three-prefix
  deny-list (`SCORCH*`, `PYTEST*`, `PYTHON*`) and inherited everything else,
  so the program that certifies the deposit ran with the operator's
  `GH_TOKEN`, `GIT_DIR`, coverage instrumentation, XDG configuration and
  matplotlib configuration in scope. It now runs under the isolated-home
  allow-list, exactly like the pytest validation.
* **Every `git` subprocess** - preflight, `rev-parse`, `status`, `ls-files`,
  `cat-file`, the trusted-contract read, the clone and the live-ref check. An
  ambient `GIT_DIR` alone made the finalizer describe a repository the
  operator never named.

**There is no network exception.** An earlier revision retained the operator's
real `HOME` for `git ls-remote` so credential helpers kept working. That was a
hole, not a convenience: one line of global configuration

    [url "file:///somewhere/else"]
        insteadOf = https://github.com/

rewrites the URL before the connection is opened, so the "live" refs the
finalization gates itself on could be served by any host the operator's
configuration nominated - and the entire point of that check is that it is not
gateable. It was reproducible. So:

* the live-ref check names its URL from the **trusted contract**
  (`https://github.com/<owner>/<name>.git`, or `repository.remote_url` where
  the contract pins one), never through the remote name `origin`;
* it runs **outside any repository**, so no `.git/config` is read either;
* `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` point at **empty run-owned
  files**, so no configuration is left that could rewrite anything;
* `GIT_CEILING_DIRECTORIES` stops upward repository discovery at the isolated
  home, and the call is made from a directory **proved** not to be inside a
  repository. The isolated home is a temporary directory, and a temporary
  directory is wherever `TMPDIR` says - which can perfectly well be inside
  somebody else's checkout. Without the ceiling, a command with no repository
  of its own walks up, finds that one and reads its `.git/config`, so an
  `insteadOf` there would redirect the live-ref check after all the trouble
  taken to neutralise the global one.

There is **no `GIT_ASKPASS`** and no credential helper. If anonymous access
fails that is reported as a `GIT_REMOTE_UNAVAILABLE` blocker; it is not worked
around.

`APPDATA` and `LOCALAPPDATA` are redirected into the isolated home rather than
inherited. On Windows they are separate per-user roots - where `gh` keeps its
hosts file and its token, and where pip keeps its configuration - so passing
the operator's through was the same hole as passing their `HOME` through.

An **environment-capture validator** proves this rather than asserting it. The
suite poisons the ambient environment with sentinel values across every family
above, runs **both** the deposit validator and the real `run_validation` pytest
child, and requires that the environment each child actually received carries
none of the sentinels and that its `HOME` is the run's isolated one.

One distinction the check has to draw, or it reports its own scaffolding as a
breach: a variable the finalizer **sets itself to a fixed value** -
`PYTHONDONTWRITEBYTECODE=1` above all - is not an inherited control merely
because the operator's shell happens to export the same name with the same
value. Calling that a leak made the verdict depend on the environment it exists
to be independent of. Those variables are enumerated in
`FINALIZER_OWNED_FIXED`, they are excluded from the comparison **only** when
they carry the finalizer's own value, and the tests poison them with a
*different* sentinel and then require the child to hold exactly the
finalizer's.

There is **no `--python` option**. A release is accepted on a validator verdict
and a pytest summary, and both are simply the standard output of whichever
executable was named - a wrapper that prints `PASS` and a clean JSON summary is
a two-line script. Production runs `sys.executable`. Any other interpreter must
match `trusted_interpreter` in the contract by realpath and/or SHA-256; with
neither pinned it is refused as `INTERPRETER_UNTRUSTED`.

The isolation probe is an **acceptance gate**, not a printout. It refuses a run
whose probe failed, whose working directory is not the disposable copy, that
would write bytecode, that reported **any** `*__error`, that failed to report a
module's `__file__` **or** its `REPO`, or that resolved either outside the
copy. Containment is decided by `Path.relative_to`, so a sibling directory
named `copy-evil` is not inside `copy`. The probed modules are contract-driven
via `isolation_probe_modules`.

## 8. Records the tool will never rewrite

* `remediation/corrected/event_global_max_algorithm/build_manifest.json`
* `remediation/freeze/freeze_manifest_pre.json`

Both carry a superseded NetCDF hash as **historical fact**. No guard reads
them for current identity, and rewriting them would falsify provenance.

Three identities are tracked for each, and they are deliberately not
conflated:

* the **git blob** SHA-1/SHA-256 and byte count - the portable repository fact
  (LF, what every platform checks out from);
* the **working-tree** SHA-256 and byte count - a non-portable observation of
  this Windows checkout, where `.gitattributes` normalization yields CRLF;
* the proven **EOL relationship** between them: applying CRLF to LF on the
  working-tree bytes reproduces the blob exactly, with zero lone CR bytes.

A Windows checkout hash is never presented as a portable git-blob identity. The
transaction snapshots and restores the **actual current bytes**, whatever the
platform checked out, while the tracked blobs are verified separately.

During a **rollback** the protected records are **verification-only**. If one
changed while the run was working, that is reported and the rollback fails; it
is never written back. A rollback that rewrites a historical record in order to
tidy up after itself is doing the exact thing the protection exists to prevent.

## 8a. How a tracked file is actually written

Every tracked target is written through a **run-owned recovery directory**
created exclusively under `.git`, on the worktree's own filesystem. For a file
that already exists:

1. the recovery name is reserved with an exclusive, no-follow create, and the
   existing target is **moved** into it - never overwritten in place;
2. the bytes that **actually moved** are re-read and compared with the planned
   original, so a writer that won the race is detected rather than overwritten,
   and what it wrote is preserved in the recovery directory;
3. the new bytes are staged in the same directory and placed with a
   **no-clobber link**, so a target recreated in the window is
   `TRANSACTION_TARGET_RECREATED` rather than silently replaced.

A **new** file - in practice the D6 receipt alone - is created no-clobber. A
receipt that appears concurrently is preserved and refuses the run
(`RECEIPT_APPEARED_CONCURRENTLY`).

The old implementation wrote through a **predictable sibling**,
`<target>.finalizer-tmp`, with an ordinary `open()`. That name could be
pre-created as a symlink and the write would follow it into an unrelated file;
a plain file left there by an interrupted run was silently truncated and
reused. No predictable sibling path is used anywhere any more.

A **per-target journal** records the original identity, the expected updated
identity, whether the finalizer really wrote the target, and the immutable
recovery copy. The rollback reasons from the journal and from nothing else. It
restores a target only when its current state is demonstrably this run's own -
absent where the run created it, or holding exactly the bytes the run wrote.
Anything else belongs to somebody: it is left alone, the recovery copy is
retained, the run reports `ROLLBACK_FAILED`, and the recovery paths appear in
the report under `transaction_recovery_paths`. There is exactly **one**
rollback owner and it is **idempotent**; `apply()` no longer rolls back on its
own, because the old inner-plus-outer arrangement ran the restore twice and the
second pass reasoned about a tree the first had already changed.

## 8a-bis. Nothing is deleted by pathname

Every removal this tool performed was shaped the same way: inspect the object
at a path, decide it is this run's own, then `unlink` **the path**. Between the
inspection and the unlink the object can be replaced, and the unlink then
destroys the replacement - somebody else's work, silently. Four sites had this
shape: `Transaction.rollback` removing a postimage it had just compared,
`_rollback_output` removing the placed archive it had just hashed, the
post-commit removal of the displaced predecessor, and `_Lock.release` removing
a lock whose `run_id` it had just read.

The rule now is: **never verify an object and later unlink that pathname.**
Instead the object is moved, in **one atomic rename**, into a slot reserved
exclusively by this run - and what is inspected afterwards is the object that
actually moved:

* **This run's own** - kept in quarantine until the outcome is verified, then
  dropped by unlinking the run-owned slot, a name no other process can hold.
* **Anybody else's**, mismatched, or **not a regular file** - preserved
  exactly as it arrived, put back under its own name if that name is still
  free and retained in quarantine if it is not, its recovery path reported,
  and the run returns `ROLLBACK_FAILED`. Independently written bytes are never
  overwritten while restoring.

After a successful commit the displaced predecessor is **not** unlinked by
path: it is quarantined, checked against the identity recorded for it, and only
then dropped. Anything else is retained and reported - past the commit point
the release stands, and a cleanup surprise is news for the operator rather than
a reason to start deleting.

**Temporaries are removed by identity, and the identity comes from the
WRITER.** `_write_new` and `_exclusive_copy` capture it from their own open
descriptor as they write - the digest covers exactly the bytes that went
through the handle - and hand it back to the caller. Nothing re-reads the
pathname afterwards to work out what is there, because that reread is the very
thing that cannot be trusted.

Neither writer unlinks a pathname on its error path any more. A write that
fails leaves an object this run created, and:

* `_exclusive_copy` knows exactly what reached the file, so the partial copy is
  journalled WITH its identity and the cleanup can prove it is this run's own
  and remove it;
* `_write_new` cannot say what reached the file, so the object is journalled
  **unconfirmed**, retained, and its location reported. It is never removed on
  a guess.

Every later removal - success path, exception path and rollback alike -
quarantines the object first and compares what actually moved against that
journalled identity. A mismatch, a non-regular object, or an
object this run never journalled at all is preserved, its recovery path
reported, and the run returns `ROLLBACK_FAILED` - or, on the success path,
`RELEASE_TEMPORARY_NOT_OURS`. This matters most for the release output
temporary, which lives beside the destination where anything can reach it and
was previously removed with an unconditional `os.unlink`.

The one place a pathname is still unlinked directly is a name this run created
with `O_EXCL` inside its own directory and never published - a staging slot, a
reservation placeholder, a quarantine slot whose contents have already been
accounted for. That is where the rule terminates, and even there the deletion
is **checked**: if the object is still present afterwards, that is a reported
failure and not a clean cleanup.

The existing release destination is **classified before it is hashed**:
`lstat` must say regular file, the descriptor is opened no-follow, and the open
handle must be the same object the name described. `sha256_file` is a plain
`open()`, so a symlink or junction at the destination previously had the run
snapshot, move aside and later restore an object somewhere else entirely.

A temporary the transaction cannot account for **stops the transaction**
(`TEMPORARY_CLEANUP_FAILED`) rather than being noted and passed over: it means
either that an object of this run's making is on disk with contents it cannot
vouch for, or that something replaced one of its temporaries while it worked,
and both are reasons to unwind rather than carry on and release.
`discard_recovery()` likewise **refuses** while any temporary is unresolved or
retained - the recovery directory may be the only place their provenance is
written down.

Cleanup state is **per run**. `_CLEANUP_FAILURES` is module-level so an at-exit
sweep can still record into it, and a leftover entry from an earlier run in the
same process would otherwise have attached somebody else's stale warning to
this run's report.

Cleanup failures are **reported, never swallowed**. The error-ignoring
recursive deletes are gone; a recovery or snapshot directory that will not
delete still holds the only intact copies of somebody's bytes, and the report
says where.

## 8b. Two exclusive locks, and one last look before committing

The whole finalization - build, validation, transaction, placement - runs under
exclusive locks on **both** the git worktree (`.git/scorch_finalizer.lock`) and
the release-staging directory (`.scorch_finalizer.lock`). A second finalizer
fails with `FINALIZER_LOCK_HELD` having touched nothing at all. A lock this run
cannot account for is **never removed or reused automatically**: it is either a
live finalization or the debris of one that died mid-transaction, and both need
a human to look first. If the second lock cannot be taken the first is
released, so a refused run leaves no lock of its own behind.

Immediately before the terminal commit point - after the archive has been
placed, with nothing left to happen - everything is re-hashed and compared
once more: every edited postimage against the journal's expected identity, the
durable receipt, the placed archive, the predecessor and recovery copies, the
protected records, the pinned figures, both archives, the technical source, the
DOCX fixtures and the font. Placement is not instantaneous, and a licence or
identity file edited during it would otherwise have shipped as part of a
"successful" release. A postimage that moved is
`POSTIMAGE_MUTATED_BEFORE_COMMIT`; the run refuses, and the external edit is
**preserved and reported**, never deleted.

### The superseded official archive shares the released filename

`scorch_processed_data_v1.0.0.zip` is the name of **both** the archive being
released and the superseded one the tracked records still point at. A
release-staging destination that resolves to the superseded archive's path
would therefore move it aside and then delete it on success. That collision is
refused outright with `RELEASE_DESTINATION_COLLIDES_WITH_SUPERSEDED`; the
operator must supply a different `--release-staging` directory.

Its explicit path, SHA-256 and byte count are verified during preflight, again
immediately before the write, and again after a successful placement - because
success, not failure, is when it would be lost. After a rollback the same
verification runs, together with a check that the receipt and every temporary
file are gone.

### Placing the archive: the race windows, and the commit point

The destination directory is shared, so every step assumes something else may
touch it.

* **Leftovers are refused, not reused.** Before placement the directory is
  LISTED and any entry whose name carries `finalizer-tmp` blocks the run
  (`RELEASE_STAGING_STALE_TEMP`) - from *any* run, not only from this one, and
  including a **dangling symlink**, which `Path.exists()` reports as absent
  and would then be clobbered or followed on write.
* **Temporaries are run-unique, exclusive and no-follow.** The names carry a
  per-run token, and they are created with `O_EXCL | O_NOFOLLOW`, so something
  planted in the window between the last check and the open is refused rather
  than overwritten or written through. A copy that fails mid-write removes its
  own partial output.
* **Placement is no-clobber.** The predecessor is moved aside, then the new
  archive is linked into place with `os.link`, which fails if the destination
  exists. `os.replace` would silently destroy a file recreated after the
  move-aside; instead the run refuses with
  `RELEASE_DESTINATION_RECREATED`.
* **The predecessor is snapshotted privately** outside the staging directory,
  and re-hashed immediately after the move. If the bytes actually moved are
  not the bytes snapshotted, a concurrent writer won the race: those bytes are
  preserved for restoration and the run refuses (`PREDECESSOR_MUTATED`) rather
  than continuing and eventually deleting somebody else's work.
* **A rollback never deletes or overwrites bytes this run did not write.**
  Before removing the placed archive the destination is re-hashed against what
  was placed; if it differs, it is left alone, the predecessor is *not*
  restored over it, and the outcome is a structured `ROLLBACK_FAILED` with the
  private snapshot retained and its recovery path reported.
* **There is an explicit terminal commit point.** It is reached once every
  operation capable of triggering a rollback has completed. Past it the
  release STANDS: a cleanup failure - a displaced predecessor that will not
  delete - is reported as `post_commit_cleanup_warning`, never rolled back
  into. Undoing a completed, verified release because a temporary file would
  not delete is the worst available trade.

> **Build artifacts must not live under `manuscript_revision_output/`.**
> `tests/test_stale_provenance.py::test_no_false_lifecycle_phrases_in_release_tree`
> scans the whole tree except `.git`, `__pycache__`, `.pytest_cache` and
> `release_staging`. A review bundle containing a pytest node-ID listing trips
> it, because test names legitimately combine a lifecycle word with a figure
> reference in ways the guard reads as a false publication claim. Keep review
> bundles outside the repository.

## 9. Blocking codes you may see

| code | meaning |
|---|---|
| `RELEASE_BLOCKED_D6` | no qualifying authorization comment exists |
| `AUTHZ_WRONG_AUTHOR` / `AUTHZ_BODY_ALTERED` / `AUTHZ_WRONG_TARGET` | a comment exists but does not qualify |
| `AUTHZ_MUTATED_DURING_READ` | the comment changed between two live reads |
| `AUTHZ_SUPERSEDED_OR_QUALIFIED` | the author's **latest activity** is not the grant - including an older comment **edited** after it into a revocation or a qualification |
| `AUTHZ_TIMESTAMP_UNPARSABLE` | an author comment carries a timestamp that is not a real instant, so activity order cannot be established |
| `AUTHZ_WITHDRAWN_BEFORE_WRITE` / `AUTHZ_CHANGED_BEFORE_WRITE` | it stopped qualifying just before the write |
| `CONTRACT_NOT_AT_HEAD` / `CONTRACT_UNTRACKED` / `CONTRACT_PATH_ESCAPE` | the contract is not the tracked one at HEAD |
| `RECEIPT_PREMATURE` / `RECEIPT_*` | the receipt pre-exists, or does not match the authorization |
| `RECEIPT_PATH_INVALID` | the contracted receipt path is a symlink, a directory or another special object, or resolves outside the repository |
| `RECEIPT_APPEARED_CONCURRENTLY` | a receipt appeared while this run was writing one; it is preserved and the run refuses |
| `FINALIZER_LOCK_HELD` | another finalization holds the worktree or staging lock, or died holding it |
| `TRANSACTION_TARGET_RECREATED` / `TRANSACTION_TARGET_NOT_REGULAR` | a tracked target was recreated after the move-aside, or is not a regular file |
| `TRANSACTION_STAGING_OCCUPIED` / `TRANSACTION_RECOVERY_OCCUPIED` | a run-owned staging or recovery slot was already occupied |
| `POSTIMAGE_MUTATED_BEFORE_COMMIT` | a file this run wrote was edited from outside before the commit point |
| `PREDECESSOR_MUTATED` / `PREDECESSOR_RECOVERY_LOST` | the destination was rewritten during the move-aside, or a recovery copy disappeared |
| `VALIDATION_TREE_SYMLINK` / `VALIDATION_TREE_SUBMODULE` | a tracked symlink or gitlink cannot be reproduced in the validation tree |
| `VALIDATION_ALLOWLIST_UNPINNED` / `VALIDATION_ALLOWLIST_MISMATCH` | an ignored artifact was admitted without a pin, or does not match it |
| `INTERPRETER_UNTRUSTED` | an interpreter other than the running one was used and the contract pins none |
| `CCBY_ACTIVE_MARKER_CONDITIONAL` | the active wording is conditional, deferred or hypothetical rather than a grant in force |
| `CCBY_ACTIVE_MARKER_UNSCOPED` / `CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE` | the active wording does not name **both** Figure 1 and Figure 4 and CC BY 4.0, or carries no present-tense affirmative grant |
| `GITHUB_API_UNAVAILABLE` | the comment could not be re-fetched |
| `APTOS_FONT_MISSING` / `APTOS_FONT_MISMATCH` | the pinned face is absent, or a different face was offered |
| `CCBY_ACTIVATION_PLAN_UNAUTHORED` | no author has written the activation wording |
| `CCBY_ACTIVATION_PARTIAL` | the plan does not cover all five licence surfaces |
| `CCBY_ACTIVATION_BLOCK_TOO_BROAD` | a bare marker was used instead of a complete source block |
| `CCBY_THIRD_PARTY_LEAKAGE` | activation disturbed a third-party rights token |
| `LICENCE_STATE_INCONSISTENT` | the five surfaces do not agree |
| `GIT_TREE_DIRTY` / `GIT_BRANCH_MISMATCH` / `GIT_HEAD_MISMATCH` | the worktree is not where it must be |
| `GIT_MAIN_MOVED` / `GIT_TAG_MOVED` / `GIT_REMOTE_BRANCH_MISMATCH` | a reference moved, per the **live** remote |
| `PR_STATE_UNEXPECTED` | the pull request is no longer open, draft, unmerged and correctly targeted |
| `FIGURE_IDENTITY_MISMATCH` | a figure or donor raster is not the approved one |
| `PENDING_MARKER_COUNT` | the four licence records no longer all withhold the grant |
| `IDENTITY_MAPPING_MISMATCH` | the eight-file / fifty-six-reference map does not match the tree |
| `PROTECTED_RECORD_MODIFIED` / `PROTECTED_RECORD_BLOB_MOVED` | a historical record, or its tracked blob, changed |
| `TECHNICAL_SOURCE_MISSING` / `TECHNICAL_SOURCE_MISMATCH` | the candidate is not the pinned pre-D6 source |
| `MANIFEST_REBUILD_FAILED` / `ARCHIVE_TOPOLOGY_DRIFT` | regeneration failed or changed the shape |
| `DEPOSIT_VALIDATOR_FAILED` | the archive's own validator did not pass |
| `EDIT_*` | the planned identity update was not exact |
| `CIRCULAR_IDENTITY` | an identity-bearing record is inside the archive it names |
| `BUILD_NONDETERMINISTIC` | two builds from independent extractions differed |
| `SIDECAR_MEMBER_DRIFT` | a relocated member's bytes changed |
| `CONCURRENT_MODIFICATION` | a tracked file changed after it was planned |
| `RELEASE_STAGING_MISSING` | the explicit destination directory does not exist |
| `VALIDATION_RUN_FAILED` / `VALIDATION_INCOMPLETE` | the disposable run was not completely clean, or not complete |
| `RELEASE_COLLECTION_UNFROZEN` / `RELEASE_COLLECTION_DRIFT` | the run did not collect exactly the frozen release node-ID set |
| `RELEASE_DESTINATION_COLLIDES_WITH_SUPERSEDED` | the destination is the superseded archive's own path |
| `SUPERSEDED_ARCHIVE_MISSING` / `SUPERSEDED_ARCHIVE_MODIFIED` | the archive the tracked records point at is gone or changed |
| `TECHNICAL_SOURCE_MUTATED` | the verified source snapshot changed during the build |
| `ARCHIVE_MEMBER_DRIFT` | a member other than the three authorized ones differs from the source |
| `ARCHIVE_MEMBER_PATH_ESCAPE` | a member name escapes the extraction root |
| `DEPOSIT_VALIDATOR_AMBIGUOUS` | the validator exited 0 without exactly one unambiguous PASS |
| `CCBY_ACTIVATION_DUPLICATE_SURFACE` | a licence surface has more than one authored transition |
| `CCBY_SCOPE_WIDENED` | activation added a CC BY claim over an excluded category |
| `AUTHZ_WRONG_TARGET` (host) | the permalink or API issue URL is not on github.com |
| `ISOLATION_UNVERIFIED` / `ISOLATION_WRONG_TREE` / `ISOLATION_BYTECODE_ENABLED` | the disposable run did not demonstrably validate the disposable copy |
| `ROLLBACK_FAILED` | the restore itself failed, or could not be completed without destroying bytes this run did not write |
| `RECEIPT_*` | the receipt does not validate, so the licence is not ACTIVE |
| `AUTHZ_SUPERSEDED_OR_QUALIFIED` | the author granted, then revoked or qualified it in a later comment |
| `CCBY_ACTIVE_MARKERS_MISSING` | the plan is authored but no active marker is registered |
| `CCBY_ACTIVE_MARKER_GENERIC` / `_UNSCOPED` / `_NOT_AFFIRMATIVE` | the registered marker is a token, is unscoped, or reads as a denial |
| `CCBY_ACTIVE_MARKER_PRE_EXISTING` | the marker is already in a record, so activation could not be distinguished from doing nothing |
| `CCBY_ACTIVE_MARKER_ABSENT` | an authored destination block, or the published row, carries no registered marker |
| `RELEASE_STAGING_STALE_TEMP` | a finalizer temporary - file or dangling symlink - exists beside the destination, or appeared after the check |
| `RELEASE_STAGING_UNREADABLE` / `RELEASE_STAGING_UNWRITABLE` | the staging directory could not be listed, or the temporary could not be created exclusively |
| `RELEASE_DESTINATION_RECREATED` | the destination reappeared after the move-aside; this run will not overwrite it |
| `PREDECESSOR_SNAPSHOT_FAILED` / `PREDECESSOR_MUTATED` | the predecessor could not be snapshotted, or was rewritten by another process |
| `BYTES_MUTATED_AFTER_HASHING` | the archive changed between hashing and placement, or after it |
| `TRANSACTION_ROLLED_BACK` | an unexpected exception aborted the transaction; everything was undone |
| `ARTWORK_RECEIPT_INVALID` | (publication builder) a receipt is present but does not validate, so no licence row may be published |

## 10. The four distinct release conditions

Pull request #1 currently describes the remaining work in a way that reads as
"two blockers". **It is not two.** These are four separate conditions with
different owners and different resolutions, and the PR wording needs updating
to say so:

1. **D6 artwork authorization.** Absent. Only Dr. Najibi can supply it, as a
   comment on PR #1. Blocks CC BY activation.
2. **The pinned Aptos Regular face.** A non-redistributable Microsoft 365 cloud
   font. `tests/test_corrected_schematic_figures.py` pins the exact face by
   SHA-256; **no substitute may be used**. Until it is provisioned
   legitimately, one honest skip remains and a zero-skip result must not be
   claimed. Independent of D6.
3. **The unauthored CC BY activation plan.** Even with D6 recorded, the
   activation wording does not exist. An author must write the exact from/to
   pairs for all five licence surfaces. Independent of both of the above.
4. **The superseded official archive.** The tracked records still point at
   `scorch_processed_data_v1.0.0.zip`, whose payload is superseded. The
   corrected candidate exists locally and unpublished. Resolved by running
   `finalize`, which is gated on 1 and 3.

Release acceptance requires the pinned font and zero skips, so condition 2
gates acceptance even after 1, 3 and 4 are resolved.

## 11. What this tool never does

It never commits, pushes, merges, tags, creates a release, publishes, or
touches the deposit records at the archive host. Those remain deliberate human
actions, taken after the authorization is recorded and this tool has reported
success.
