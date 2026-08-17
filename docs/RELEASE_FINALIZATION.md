# Release finalization - operator guide

This document describes `scripts/release/release_finalizer.py`, the tool that
performs the SCORCH v1.0.0 release finalization once - and only once - the
CC BY 4.0 licence over the Figure 1 and Figure 4 schematic artwork has been
recorded in this repository by the artwork's creator.

**Who licenses this artwork.** Fawaz Bouhamad created the Figure 1 and Figure 4
schematic artwork and is its copyright holder and sole licensor. Dr. Nasser
Najibi provided the scientific guidance, review and corrections behind those
figures, remains a manuscript coauthor, and is credited for exactly that
contribution. Dr. Najibi is not a copyright co-owner or licensor of the
artwork. No email, signature, GitHub comment, evidence file or other written
authorization is sought from them, and none is recorded anywhere in this
release. Every activated licence surface carries this credit line verbatim:

> Figure 1 and Figure 4 artwork by Fawaz Bouhamad, developed with scientific
> guidance from Dr. Nasser Najibi. Licensed under CC BY 4.0.

**What the tool therefore verifies.** Not consent - the licensor is the person
running the release - but SCOPE and INTEGRITY: that the creator's declaration
is committed at HEAD, that its bytes equal the reviewed blob, that it pins
exactly the seven registered artwork identities, that those identities still
hold in the tree, and that the credit is carried without being turned into a
second grant. Every one of those fails closed.

**Status at the time of writing: the tooling is built and tested. It has NOT
been run against the repository in `finalize` mode. The creator's declaration
has not been recorded, so CC BY 4.0 over Figure 1 and Figure 4 remains PENDING
and NOT YET IN FORCE, exactly as every licence record in this repository
states.**

## 1. What the two modes do

| | `preflight` | `finalize` |
|---|---|---|
| writes to disk | never, including bytecode | only after every check passes |
| needs the declaration | no | yes, resolved from the tracked creator declaration committed in this repository |
| safe to run now | yes | it will stop at the gate |

### The interpreter: name it, never inherit it

Every command below names the interpreter through `PY312`, never bare `python`.
Set it once, to the **canonical Python 3.12** this repository is locked to.

The two shells are **not interchangeable** and the examples are given
separately throughout. Bash quotes the variable, `"$PY312"`; PowerShell must
invoke it through the call operator, `& $PY312`, because a bare `$PY312` at the
start of a line is an expression PowerShell prints rather than a command it
runs. Bash's `\` line continuation is a syntax error in PowerShell, so the
PowerShell examples pass their arguments as an array instead.

bash:

```bash
PY312="$LOCALAPPDATA/Programs/Python/Python312/python"
"$PY312" -c "import sys; print(sys.version)"    # expect 3.12.x
```

PowerShell:

```powershell
$PY312 = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $PY312 -c "import sys; print(sys.version)"    # expect 3.12.x
```

This is not pedantry about versions. On the authoring machine the `python`
first on `PATH` is a **Spyder-bundled 3.8.10** whose `sys.path[0]` is
`python38.zip` rather than the running script's own directory, so
`release_finalizer.py` cannot import its sibling `artwork_licence_state` and
dies before it checks anything:

```
$ python scripts/release/release_finalizer.py preflight ...
ModuleNotFoundError: No module named 'artwork_licence_state'
$ echo $?
1
```

The failure is at least **loud** - exit 1, nothing on stdout, so it can never
be misread as a clean preflight - but it is a failure of the wrong interpreter,
not of the release. The file compiles fine under 3.8; the defect is that frozen
distribution's `sys.path`, which no amount of `cd` repairs. Do not work around
it with `PYTHONPATH`: run the pinned 3.12.

The test suite additionally needs `src` importable - either `PYTHONPATH=src`
(`$env:PYTHONPATH = 'src'` in PowerShell) or the editable install `README.md`
describes: `"$PY312" -m pip install --no-deps -e .` in bash,
`& $PY312 -m pip install --no-deps -e .` in PowerShell.

### `preflight` - read-only

bash:

```bash
"$PY312" scripts/release/release_finalizer.py preflight \
  --repo-root <worktree> \
  --expect-branch chore/final-repository-cleanup \
  --expect-head <40-hex commit> \
  [--candidate-archive <zip>] \
  [--final-docx-dir <dir>] \
  [--aptos-font <ttf>] \
  [--format text|json|both]
```

PowerShell:

```powershell
$flags = @(
  'preflight',
  '--repo-root',      '<worktree>',
  '--expect-branch',  'chore/final-repository-cleanup',
  '--expect-head',    '<40-hex commit>',
  '--candidate-archive', '<zip>',        # optional
  '--final-docx-dir', '<dir>',           # optional
  '--aptos-font',     '<ttf>',           # optional
  '--format',         'both'
)
& $PY312 scripts/release/release_finalizer.py @flags
```

Drop any optional line you are not supplying; an array element is one argument,
so no quoting or escaping is needed for paths containing spaces.

Both reports go to **stdout**. Nothing is written anywhere - `preflight` sets
`sys.dont_write_bytecode` before importing anything, so it does not even leave
a `__pycache__` behind. Exit code is 0 when every invariant holds and 1
otherwise.

It verifies: the repository root, branch, HEAD and a clean tree; that
`origin/<head branch>` equals local HEAD; that `origin/main` and the `v1.0.0`
tag object and its peeled commit are all where the contract says; that the pull
request is open, draft, unmerged and pointed at the expected base and head;
the licence declaration status; the pinned SHA-256 of the Figure 1 and
Figure 4 assets and the archived-original and donor rasters; that all four
licence records still withhold the artwork grant, reported as an explicit
licensing STATE; the eight-file / fifty-six-reference identity map, including
that no ninth tracked file carries the identity; that the two protected
historical records still carry the superseded NetCDF hash they exist to record,
**and that their tracked git blobs are unmoved**; that the licence receipt does not
already exist; the candidate archive's identity, topology, self-coverage,
NetCDF contract and agreement with the pinned technical source when one is
supplied; the FINAL DOCX fixture pair; and the pinned Aptos Regular face.

#### Which DOCX pair is which

Two different pairs are in play and they must never be swapped. **Only the
first is an input to anything the tooling checks.**

| role | files | identity |
|---|---|---|
| **R5 geometry fixtures** - what `SCORCH_FINAL_DOCX_DIR` and `docx_fixtures` mean, and the only pair `tests/test_final_docx_geometry.py` and `tests/test_stale_provenance.py` accept | `SCORCH_Manuscript_FINAL_v1.0.0.docx`, `SCORCH_Supplementary_Material_FINAL_v1.0.0.docx` | pinned in `docx_fixtures`; the manuscript is 24,405,662 B |
| **Latest author-review documents** - the current editorial drafts, reviewed by the authors | `SCORCH_Manuscript_FINAL_Hyperlinked.docx`, `SCORCH_Supplementary_Material_FINAL_corrected.docx` | **not pinned anywhere**; different content, different hashes, different byte counts |

The review documents are **later** than the fixtures and are *not* supersets of
them: the hyperlinked manuscript is ~5.4 MB larger. Renaming or copying one
over the other is the exact mistake `DOCX_FIXTURE_MISMATCH` exists to catch
("the superseded pre-R5 pair must not be used"), and it would catch it in the
wrong direction too - the geometry guards pin EMU extents and 17 embedded image
hashes that only the R5 pair carries.

Point `SCORCH_FINAL_DOCX_DIR` at a directory holding the **fixture** pair, and
verify by hash before use. A third document,
`SCORCH_Manuscript_FINAL_Figure04Symmetry.docx`, is the Figure 4 *integration*
DOCX; `tests/test_fig04_symmetry_final.py` reads its `word/media/image4.png`
and requires it to equal the canonical Figure 4 asset byte for byte.

### `finalize` - gated and transactional

bash:

```bash
"$PY312" scripts/release/release_finalizer.py finalize \
  --repo-root <worktree> \
  --expect-branch chore/final-repository-cleanup \
  --expect-head <40-hex commit> \
  --candidate-archive <the pinned corrected candidate zip> \
  --release-staging <explicit destination directory> \
  --final-docx-dir <dir> --aptos-font <ttf> \
  --confirm "FINALIZE SCORCH RELEASE"
```

PowerShell:

```powershell
$flags = @(
  'finalize',
  '--repo-root',         '<worktree>',
  '--expect-branch',     'chore/final-repository-cleanup',
  '--expect-head',       '<40-hex commit>',
  '--candidate-archive', '<the pinned corrected candidate zip>',
  '--release-staging',   '<explicit destination directory>',
  '--final-docx-dir',    '<dir>',
  '--aptos-font',        '<ttf>',
  '--confirm',           'FINALIZE SCORCH RELEASE'
)
& $PY312 scripts/release/release_finalizer.py @flags
```

`--release-staging` is **required and explicit**. The destination is never
derived from the repository's parent directory.

There is deliberately **no flag that supplies, asserts or points at the artwork
licence**. The grant rests on a declaration committed in this repository by the
artwork's creator and reviewed like any other tracked file; a command-line flag
that could stand in for it would be a way to license artwork from a shell.

## 2. The licence gate

One source satisfies this gate, because there is one licensor: a **declaration
by the artwork's creator**, committed inside this repository at
`docs/FIGURE_01_04_CC_BY_CREATOR_DECLARATION.json` and recorded in the receipt
as `licence_source: creator_declaration`.

There is no second route. The GitHub-comment route and the external-evidence
route that earlier revisions carried have been **removed, not disabled**: the
client can no longer read comments at all, `find_authorization` is gone, and
`tests/test_release_finalizer.py` asserts that `GitHubCLI` has no
`issue_comments` or `issue_comment` attribute. A dormant method is a surface a
later edit can reach for.

Pull request **metadata** is still verified through GitHub - open, draft,
unmerged, pointing at this HEAD - because that is a fact about the release. It
has nothing to do with the artwork licence.

### 2.0 What the declaration is

A reviewed, committed JSON file stating, in the clear:

| field | what it fixes |
| --- | --- |
| `declared_text` | the contracted declaration paragraph, EXACTLY - pinned by digest in `REVIEWED_DECLARATION_TEXT` |
| `licensed_artwork` | the seven repository paths, each with the SHA-256 of the exact bytes being licensed |
| `creator_attestation` | `creator` (Fawaz Bouhamad), `declared_at`, and the contracted attestation statement |
| `scientific_guidance_credit` | `Dr. Nasser Najibi` - a CREDIT, checked for exact equality so it can neither be dropped nor inflated into a grant |
| `declaration_date` | an ISO-8601 UTC instant, no later than `declared_at` |

Nothing is preserved in a private mailbox, nothing is supplied on the command
line, and no network is consulted. Every surface this tool reads for the
licence is repository-contained.

### 2.1 What the software proves, and what it does not

Stated plainly, because the guarantee is different in kind from the one an
approval workflow offers - and pretending otherwise would be the dishonesty
this design exists to remove.

**The software proves**, mechanically and repeatably:

* that the declaration is **tracked at HEAD** and byte-identical to its
  committed blob - so the declaration read is the one that was reviewed;
* that it **parses strictly** - a duplicate JSON key is a refusal, not a silent
  last-wins;
* that `declared_text` is **exactly** the contracted paragraph. Equality, never
  containment: the paragraph plus a withdrawal, a qualification, a condition,
  or a sentence deferring the decision to somebody else is refused;
* that the **seven path -> SHA-256 identities** still hold in the tree and
  equal the identities pinned in code, so the grant reaches the bytes that were
  declared and not whatever is at the path now;
* that the **creator** is the contracted one and the attestation is exactly the
  contracted statement;
* that the **guidance credit is exactly** `Dr. Nasser Najibi` - a declaration
  that drops the credit, or that restates it as a co-licence, is refused; and
* that the **declaration and the receipt agree** on every one of those facts.

**The software does not prove** - and does not claim to - that the person
running the finalization is Fawaz Bouhamad. It cannot: the licensor and the
operator are the same person, so there is no third party whose consent could be
forged and no signature for a program to check.

That is the honest shape of the guarantee, and it is deliberately narrower than
what an approval gate would claim. **What is mechanically enforced here is
SCOPE, not consent**: that a release cannot quietly widen a CC BY grant beyond
the seven registered works, cannot license bytes nobody declared, and cannot
represent anyone other than the creator as granting anything. Consent is not at
issue, because the work being licensed is the licensor's own.

The declaration is read through a **component-safe, no-follow, opened-handle
walk** anchored at the repository root: every directory component is opened and
refused if it is a symlink, junction or not a directory, the leaf is refused
unless it is a regular file, and the object hashed is the object that was
checked. **Containment failures fail closed** - there is no fallback to a plain
`open()`, because a fallback would be the whole attack.

The receipt records the declaration's blob id and digest, so the chain is
reconstructible years later from the tree alone - and every later reader of
that receipt (the publication builder, the repository guards) **re-verifies the
declaration at HEAD** before treating CC BY as being in force.

Deliberately absent: any boolean meaning "licensed", any way to supply the
declared text on the command line, any way for this tool to write the
declaration, and any hand-written receipt - every field a forger would have to
invent is checked against the declaration or the tree, and a receipt whose
declaration is absent, untracked, locally edited or contradictory is refused
rather than reported as active.

**Before the declaration is committed** both preflight and finalize stop at
`LICENCE_DECLARATION_ABSENT`. That is the current and correct state.

## 3. The contract production is allowed to trust

The contract decides who may authorize the release, what text counts as
the declaration, which assets the licence reaches and what the activation may
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

## 4. The durable licence receipt

`docs/FIGURE_01_04_CC_BY_LICENCE_RECEIPT.json`

A stdout report is not a receipt. Once CC BY is in force over the artwork, the
repository must be able to show **who** declared the grant, at **which** time,
over **which** files, and on **which** committed declaration it rests - years
later, from the tree alone, without any network and without this tool.

The receipt carries `licence_source`, whose only legal value is
`creator_declaration`. It is **required**: a receipt that does not say where
the licence comes from is refused, and so is one naming a route this project
does not use. There is no legacy default to fall back to, because no receipt
has ever been written under any other scheme.

| the receipt records | |
| --- | --- |
| the declaration | its tracked path, its SHA-256 and its git blob id |
| the grant | the exact declared paragraph and its SHA-256 |
| the people | `creator` (the licensor) and `scientific_guidance_credit` (a credit, never a grant) |
| the works | all seven licensed artwork paths with their hashes |
| the run | `declaration_date`, `declared_at`, `activated_at`, `finalizer_version`, `starting_head` |

It carries **no** comment id, **no** permalink, **no** pull request, **no**
login and **no** evidence digest, because there is no comment, no third party
and no external evidence: fabricating those fields to satisfy an older schema
would produce a receipt pointing at things that do not exist and at a person
who was never asked for anything. A test asserts each of those fields is
absent.

**A receipt is only as good as the declaration it rests on, so that declaration
is re-verified every time the receipt is read** - by the finalizer, by the
publication builder and by the repository guards. The declaration must be
present, **tracked at HEAD**, byte-equal to its committed blob, and its SHA-256
and git blob id are **recomputed** and required to equal the two the receipt
commits to; its paragraph, its seven-artwork scope, its creator attestation and
its guidance credit must then equal the receipt's. A receipt whose declaration
is absent, untracked, locally edited, or contradictory never yields `ACTIVE` -
which closes the gap a self-consistent hand-written receipt was aimed at, since
its author can choose every digest in it but cannot commit a matching
declaration.

It is built and validated inside the disposable validation copy, then written
**atomically as part of the same transaction** as the licence and identity
edits. If any part of the transaction fails, the receipt is removed again. Its
presence is what the publication builder and the consistency guards read to
decide which licensing state the repository is in.

**It must not exist before a qualifying declaration has been resolved and
revalidated.** `preflight` fails with `RECEIPT_PREMATURE` if it does.

## 4a. One state module, and a receipt that must VALIDATE

`scripts/release/artwork_licence_state.py` is the single source of truth for
"is CC BY in force over the artwork?". The finalizer, the publication builder
and the repository guards all import it, so they cannot drift into disagreeing.

It exists because all three used to answer that question by asking whether a
receipt FILE EXISTED. A file with the right name containing
`{"schema_version": "1.0.0"}` was therefore enough to make the publication
builder assert an active CC BY licence over the artwork.

ACTIVE now requires a receipt that **validates**:

* `licence_source` exactly `creator_declaration` - anything else, or its
  absence, is `RECEIPT_LICENCE_SOURCE` and nothing further is considered;
* the correct **schema version** and repository;
* `declaration_date`, `declared_at` and `activated_at` each a **real parsed**
  UTC instant, in that order (a regex accepts `2026-13-45T99:99:99Z`, which is
  not a date, so the value is parsed);
* the correct **`finalizer_version`**;
* **`starting_head`** as a 40-hex commit, equal during finalization to the
  run's validated starting HEAD;
* `declared_text` exactly the contracted paragraph, and
  `declared_text_sha256` hashing it;
* `creator` exactly the contracted creator, and
  `scientific_guidance_credit` exactly the contracted credit;
* **exactly the seven** contracted artwork paths, whose recorded hashes still
  match the files on disk;
* **the tracked declaration**, re-read at HEAD every time: present, tracked,
  byte-equal to its committed blob, with `declaration_record_sha256` and
  `declaration_record_blob_sha1` **recomputed** and equal to the receipt's, and
  the declaration itself well-formed (its own `schema_version` and full
  mandatory field set);
* agreement with the declaration this run resolved, when there is one.

Anything less is not ACTIVE.

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
copyright licence over the artwork in words that say, in themselves,
that they are not real.

A contract is a test fixture only if it **says so** (`synthetic_fixture:
true`). Silence means production, so the real contract cannot become
"synthetic" by omission. `synthetic_wording_issues()` scans the contract's
markers, its publication rows and its activation-plan replacements for the
`TEST-ONLY` token, and it is enforced where production actually happens: in the
production contract loader and in the activation planner, both refusing with
`CCBY_TESTONLY_WORDING_IN_PRODUCTION`. The real contract carries no such token
anywhere, and a test asserts that.

None of this authors anything, and none of it approves anything. What changed
since this rule was written is only that the wording now **exists**: the real
contract's `artwork_licence_markers.active` carries the authors' clause and
`ccby_activation_plan.authored` is `true`, so the rule above now governs a
marker that is registered rather than one that is hypothetical. Registering a
marker is not a grant, and writing the prose is not permission to apply it.
The real records are unchanged: every one of the five licence surfaces still
carries its PENDING marker, no qualifying declaration has been recorded, and
no receipt exists at
`docs/FIGURE_01_04_CC_BY_LICENCE_RECEIPT.json`. The state is **PENDING**
- authored, inactive, unauthorized.

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

`activated_at` **defaults to the creator attestation's `declared_at`** - the
moment the creator attested to the declaration the release acts on. The receipt
requires `activated_at >= declared_at >= declaration_date`.

Using the declaration's own timestamp rather than the wall clock keeps the
receipt validated in the disposable copy byte-identical to the one written to
the real tree, and makes the receipt reproducible.

The publication builder no longer accepts injected licence prose. Both wordings
live in the trusted contract under `publication_outputs_artwork_row`, and both
are now authored. That does not change what gets published: the builder picks
the row from the repository's **actual** licence state - receipt present and
valid, or not - so today it still emits the PENDING row. Were `active` left
empty the builder would refuse to render an active row at all, which is the
behaviour that still applies to any wording an author has not yet written.
`readme_text` has no parameter for passing licence text in - a caller able to
inject arbitrary wording into published output would be a way to publish a
licence claim nobody authored.

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

### The activation plan is AUTHORED. It is not AUTHORIZED, and not APPLIED

`ccby_activation_plan.authored` is `true`: **Fawaz Bouhamad** has written the
exact `from` / `to` prose for all five surfaces, and
`CCBY_ACTIVATION_PLAN_UNAUTHORED` no longer fires. **This changes nothing about
what is licensed today.** Three distinct things must not be confused:

| | what it means | where it lives | present state |
|---|---|---|---|
| **authored** | the exact replacement prose exists | `ccby_activation_plan.replacements` in the contract | **done** |
| **declared** | the creator recorded the CC BY 4.0 grant over the seven registered works | `docs/FIGURE_01_04_CC_BY_CREATOR_DECLARATION.json`, then `docs/FIGURE_01_04_CC_BY_LICENCE_RECEIPT.json` | **absent** |
| **applied** | the records and the deposit assert the grant | the four records + the archive `LICENSE.txt` | **pending** |

An authored plan is a **draft of a future edit**. It grants nothing, asserts
nothing, and is inert until a real `finalize` **resolves and revalidates the
creator's declaration**. The repository state is still `pending`: every licence
record still withholds the grant, the publication builder still emits the
pending row, and no receipt exists. `finalize` still stops - now at
`LICENCE_DECLARATION_ABSENT`, not at the authorship gate.

The authored clause registered in `artwork_licence_markers.active` is:

> The Figure 1 and Figure 4 slide artwork is licensed under the Creative
> Commons Attribution 4.0 International licence (CC BY 4.0).

It is one anchored affirmative clause because that is the only shape the
classifier will register (section 4a). All the scoping - which seven assets,
which approved corrections, what is excluded - lives in the sentences the
destination blocks put around it, and in `ccby_activation_plan.scope`.

**Scope of the authored plan.** Exactly the seven declared assets in
`ccby_artwork_paths`, covering the Figure 1 threshold-text correction and the
Figure 4 arrow-direction and symmetry corrections. It leaves
untouched: the SCORCH software (`GPL-3.0-only`), ERA5 and all
Copernicus-derived material, GHCN-Daily observations, Natural Earth boundaries,
the pinned Aptos face and every font right, the deposit's MIT
`validate_deposit.py`, and every other figure and underlying third-party
dataset.

**What the declaration covers, and what CC BY 4.0 then permits.** These are two
different questions, and earlier revisions of this guide ran them together.

The **Licensed Material** is bounded by identity: exactly those seven assets,
each named by complete repository path and SHA-256, together with exact copies
of them wherever they are shipped - which includes the copies carried in the
companion deposit and in `publication_outputs/`. What the activation must never
do is enlarge that set, and in particular it must never make an **eighth**,
unrelated artwork path part of it.

What the licence then permits over that material is CC BY 4.0's own business,
and CC BY 4.0 permits reproduction, technical format changes and **adaptation**
on its own terms. Earlier wording here and in the contract said that a cropped,
rescaled, recoloured or recomposed export was "outside the grant". That was
wrong as a statement of the licence and has been removed: a licensee who adapts
the Licensed Material is exercising a permission the licence itself gives them.
The seven-file boundary is about which works the creator declared - not about
forbidding what CC BY 4.0 allows anyone to do with them afterwards.

Two things follow, and both are still enforced. Language declaring an
open-ended **class** to be Licensed Material - "every PNG/PDF export derived
from them", "anything materialized into `publication_outputs/`" - is still
refused, because a class has no path and no digest and cannot be what the
creator declared; that is a claim about *identity*. And a truthful sentence
saying CC BY 4.0 permits adaptation of the seven works is accepted, because it
claims nothing about identity at all.

Four machine guards enforce that, not the prose: every third-party rights token
must survive at its exact count; no sentence may newly assert CC BY beside an
excluded token; no sentence may newly identify Licensed Material that is not
one of the seven registered assets (`CCBY_SCOPE_UNREGISTERED_ASSET`); and each
record's structure - line count for Markdown, parsed shape for `.zenodo.json` -
must be unchanged.

### The reviewed wording is PINNED IN CODE

Those guards are pattern matchers, and a pattern matcher refuses only what
somebody anticipated. The r3k guard was measured against eight ways of widening
the grant and accepted five of them outright; when an existing **denial** was
rewritten into a grant it accepted all eight, because it counted sentences that
merely *mentioned* CC BY, and a denial and a grant are both such a sentence.

So the primary authority is no longer a pattern.
`REVIEWED_ACTIVATION_DESTINATIONS` in `scripts/release/release_finalizer.py`
pins, by SHA-256, the exact activated wording of all five licence surfaces;
three companion constants pin the active publication row, the classifier's
ACTIVE marker, `licence_declaration.text` and the public credit line. The
contract carries the prose;
the code decides **which** prose was reviewed. Any edit to a destination block -
an eighth artwork path, a widened class, a deleted exclusion, one character -
changes its digest and is refused as
`CCBY_ACTIVATION_DESTINATION_UNREVIEWED`, at preflight and again before any
activation is planned, without the code having to understand what changed.

Revising the wording is therefore a **two-part** change: edit the contract, then
re-review and update the code-owned digest. That friction is the point.

**The ACTIVE publication row is read for its SCOPE too** (4D-r3n). It is the one
licence surface published to readers of `publication_outputs/README.md`, and it
was checked only for its digest and its marker - never for what its scope token
identified as Licensed Material. So it wrote `assets/frozen_figures/**`, an
undeclared glob reaching everything under that directory, which would have been
refused instantly in any licence record. It now names the two declared scopes
exactly, `fig01/**` and `fig04/**`, and `_assert_publication_row_scope` reads it.

A row is judged **whole**, not split into sentences: `_sentences` breaks on the
full stop in `(Fig. 1, 4)`, which puts the scope cell in one fragment and the CC
BY clause in another, so a sentence-scoped check sees a scope with no licence
beside it and a licence with no scope, and passes. That is precisely how the
broad glob survived. The `pending` row is left broad on purpose: it is a
*denial*, and withholding over a wider area grants nothing.

### The legal SCOPE is pinned in code too

The wording pins decide what the licence **sentences say**. They do not decide
which **files** those sentences reach, because the sentences name directories
and figure numbers, not identities - and until r3m every surface that did name
the files lived in the contract, where one edit could add an eighth work,
repoint a path at different bytes, or drop one. Four surfaces claimed to state
that scope and nothing required them to agree with each other.

`REVIEWED_CCBY_ARTWORK_IDENTITIES` pins the **seven repository path → SHA-256
identities**, and `REVIEWED_CCBY_SCOPE_GLOBS` pins the **five declared
directory scopes**. All four contract surfaces must equal them:

| surface | what it claims |
| --- | --- |
| `ccby_artwork_paths` | the works the record, the receipt and the guards check |
| `figures` entries for those paths | the exact bytes of each |
| `ccby_activation_plan.scope.assets` | what the activation says it grants |
| `ccby_artwork_scope_globs` | the directory shorthand the prose may use |

Adding, removing, renaming or changing any identity fails as
`CCBY_ARTWORK_SCOPE_UNREVIEWED`, `CCBY_ARTWORK_IDENTITY_UNREVIEWED`,
`CCBY_SCOPE_GLOBS_UNREVIEWED` or
`CCBY_ARTWORK_PATH_NOT_REPOSITORY_RELATIVE` - **in the loader**, so before an
declaration is recorded and before any activation is planned. A path alone
would not be enough: the grant is over images somebody looked at, so changing a
file's bytes is exactly as loud a failure as adding a file.

A declared `dir/**` must now hold the registered works and **nothing else** -
not a README, a caption, an extensionless file, a subdirectory, or any link,
junction or special object. The previous rule only refused files whose
*extension* was in the artwork list, which is the same anticipate-the-attack
weakness the digest pins exist to escape.

### The fixture exemption, and why production refuses it

Contracts declaring `synthetic_fixture` are exempt from the prose pins, the
scope pins **and** the TEST-ONLY wording refusal, so the test fixtures can drive
activation with invented wording in a temporary directory. Because that single
key switches off the entire apparatus, **`load_trusted_contract` refuses the key
outright** - `CONTRACT_DECLARES_SYNTHETIC_FIXTURE` - and refuses it in *any*
form, `false` and `null` as surely as `true`, since the difference between them
is one character in a file the release then trusts to define what it is
licensing.

The end-to-end tests still drive that production path against a synthetic
repository, through a keyword-only, default-off Python argument. **No
command-line flag, environment variable or contract field reaches it**, and
`main` calls the loader with the default; a test asserts all three.

### The unregistered-asset guard, as defence in depth

Underneath the pins the guard still reads the prose, and three properties were
repaired in 4E1d - each of which had been a bypass:

| property | the bypass it closes |
| --- | --- |
| **polarity** | Only affirmative grants are counted. Counting every CC BY mention made a denial and a grant the same observation, so rewriting `No CC BY 4.0 licence is asserted over assets/other/Figure_09.png` into `assets/other/Figure_09.png is licensed under CC BY 4.0` left the count unchanged and licensed an unrelated eighth work. Polarity is decided narrowly and fails **closed**: an unrecognised sentence is read as a grant, and so is a sentence that both grants and denies. |
| **identity** | Comparison is against complete normalized repository paths. A basename is not a path, so `assets/other/Figure_01.png` is a different file; a bare `Figure_01.png` names no path and can be checked against no digest; a URL, and a drive-absolute path such as `C:\assets\…\Figure_01.png`, name something outside the tree entirely and are never folded onto a registered path - which is exactly what the old pattern did by shaving the drive letter off. |
| **root anchoring** (4D-r3n) | A **POSIX-absolute** path (`/assets/…`), a **home-prefixed** path (`~/assets/…`) and a **UNC/network** path (`//host/share/…`, `\\host\share\…`) are each refused as themselves. The defect was in the TOKENIZER, not the classifier: the token pattern required a match to begin with a word character, so in `/assets/frozen_figures/fig01/Figure_01.png` the match began *after* the slash and the classifier was handed a registered repository path and correctly answered "claims nothing". No care in the classifier could have seen it. The pattern now matches these forms including their leading marker, with a lookbehind so that `and/or` and the `https://` of a deed URL are not swept up. |
| **coverage** | A token the classifier cannot place is refused, not skipped. An unrecognised extension (`.webp`) used to make a work invisible, and a directory glob (`assets/other/**`) matched no pattern at all. A glob is now accepted only where the contract declares it in `ccby_artwork_scope_globs` **and** the tree confirms nothing but registered artwork lives under it - `CCBY_SCOPE_DECLARATION_TOO_BROAD` otherwise, re-checked on every preflight, so dropping an eighth raster into a licensed directory blocks the release. |

Separator style and redundant `./` segments are still normalized away, so the
same file spelled `assets\frozen_figures\fig01\…` is still the same file; `..`
is deliberately **not** resolved, so a path that climbs out of the tree stays
unequal to every registered one. A malformed path such as
`assets//frozen_figures/…` fails **closed**. Version numbers, abbreviations and
citations of records (`…RECEIPT.json`, `RELOCATED_ARTIFACTS.csv`,
`test_public_consistency_guards.py`) are not artwork claims and are not
reported: a guard that buries its one real finding under a page of noise is a
guard somebody switches off.

The delta rule is unchanged and is what keeps the guard usable: sibling rows in
these tables carry long-standing grants over other figures. Only what activation
**adds** is reported.

What survives is exactly what the declaration says: the seven registered paths,
and **byte-identical copies** of them - under a licence that then permits their
adaptation on its own terms.

The publication builder takes the same stance it always did: it serves the
authored row for whichever state the repository is actually in, and invents
neither.

CC BY reaches the authors' own artwork. It reaches nothing else.

### Reviewing or revising the authored wording

The wording is the authors' and may be rewritten at any time before
finalization. Anything that changes it must keep all five of these true, and
section 8a of `tests/test_release_finalizer.py` asserts each one:

1. all five surfaces covered, exactly one transition each, `count` exactly 1;
2. each `from` block still occurs **exactly once** in its live surface - if a
   record is edited independently the plan goes stale, and the planner refuses
   rather than guessing;
3. each `to` block carries the registered clause as a **standalone block** (own
   line, own sentence, or own table cell) and leaves **no** registered pending
   marker anywhere in that surface;
4. third-party rights tokens and record structure unchanged;
5. the clause is absent from every record *before* activation, or activation
   could not be distinguished from doing nothing.

### 5a. The deposit's own notice is rewritten SURGICALLY

The four tracked licence records are Markdown and JSON, and each is held to an
unchanged line count or an unchanged parsed shape by
`_assert_structure_preserved`. The deposit's `LICENSE.txt` is neither. Its
authored destination block is deliberately **two lines longer** than the block
it retires - 13 lines becoming 15 - so "the structure did not change" was never
available as a check on it.

That is the wrong way round, because `LICENSE.txt` is the surface with the most
to lose. It carries the section 0 path table, the MIT grant over
`validate_deposit.py`, and the Copernicus and GHCN-Daily notices that neither
author has any power to relicense. Five things are now proved about it before
a single byte is written:

1. **The complete source block occurs exactly once.** Not "at least once", and
   not as a bare marker - `CCBY_ACTIVATION_COUNT` if the staged notice carries
   it any other number of times, `ARCHIVE_LICENCE_BLOCK_NOT_UNIQUE` from the
   guard itself.
2. **The authored destination replaces only that block.** The rewrite is
   **spliced**, not globally replaced: the result is constructed as
   `prefix + destination + suffix` from the two unchanged sides, so there is no
   second match for it to have landed in. `bytes.replace` is a global
   operation, and counting matches beforehand says nothing about the bytes that
   come back.
3. **Every byte outside the block is unchanged.** The prefix and the suffix are
   compared byte for byte and reported by SHA-256 and length, and the three
   spans are required to account for the whole file. Any collateral edit -
   a flipped byte in the path table, a deleted Copernicus attribution, an
   appended line, a truncated tail - is `ARCHIVE_LICENCE_COLLATERAL_EDIT`, and
   the refusal names the byte offset where the difference starts.
4. **The +2 line delta is explicit and pinned.** The block's own growth and the
   whole notice's growth must each be exactly `+2`. The figure is pinned in
   **code** as `ARCHIVE_LICENCE_EXPECTED_LINE_DELTA`, and
   `archive_topology.licence_block_replacement.expected_line_delta` must
   **equal** it. Same discipline as `CONTRACT_IDENTITY_EXEMPT_FIELDS` in
   section 8: editing the contract may not license a larger rewrite of the
   deposit's legal notice than the one that was reviewed.
5. **Adjacent and third-party licence text is unchanged.** Seven passages are
   named in `licence_block_replacement.adjacent_anchors` - the section 0 path
   table header, the MIT software section, the ERA5/Copernicus and GHCN-Daily
   section headers, the Copernicus attribution sentence, the ECMWF liability
   sentence and the NOAA courtesy line. Each must be **present**, must lie
   **outside** the replaced block, and must survive at an unchanged count. The
   outside-the-block requirement is the load-bearing one: a source block that
   grew to swallow the Copernicus notice would otherwise be free to rewrite it
   and still satisfy every check above.

The deposit's notice also now gets **the same three scope guards every tracked
record has always had** - third-party token counts, excluded scope, and the
unregistered-asset guard. Previously it got only the first. A destination block
that relicensed the MIT validator, put CC BY over the ERA5 material, or granted
over an eighth raster would have been written into the shipped deposit without
complaint.

A refused transition writes nothing: validation completes before `LICENSE.txt`
is opened for writing, so the staged notice is left exactly as it was found.

Section 38 of `tests/test_release_finalizer.py` asserts all five properties
against the **real** notice and the **real** authored pair, and includes the
adversarial case: six ways of changing text adjacent to the block, each of
which leaves the authored block itself perfectly correct, and each of which is
refused.

## 6. How the final archive is built

The finalizer does **not** zip an arbitrary staging directory. It:

1. requires the exact pinned pre-finalization candidate as the **technical source** -
   a local, unpublished, pre-finalization working artifact that is *not* the released
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

* `provenance/corrections/tmax_weighted_centroids/corrected/event_global_max_algorithm/build_manifest.json`
* `provenance/corrections/tmax_weighted_centroids/freeze/freeze_manifest_pre.json`

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

### The contract names other archives, and is ACCOUNTED FOR, not excused

The eight-file / fifty-six-reference map is checked for **exhaustiveness**: any
other tracked file carrying the archive identity would be left behind
contradicting the archive, so the scan reports it. The trusted contract trips
that scan honestly. It *has* to name the superseded archive it preserves and
the pre-finalization technical source it rebuilds from, and both are named by SHA-256 and
content-root hash.

Both easy repairs are wrong:

* **exempting the file** would let a *current-release* pointer hide anywhere
  inside it - in a note, in a new field, as an object key;
* **adding it to the map** would have the next finalization rewrite records
  that exist to state historical and candidate fact.

So the exemption is **field-level**, and the permitted paths are pinned in
`release_finalizer.py` as `CONTRACT_IDENTITY_EXEMPT_FIELDS`.
`contract_identity_exemption.declared_fields` must **declare exactly that set**
- it does not get to choose it:

```
superseded_official_archive.sha256
superseded_official_archive.content_root_hash
technical_source_candidate.sha256
technical_source_candidate.content_root_hash
```

Six rules make it narrow rather than convenient:

1. the permitted **paths** are pinned in `release_finalizer.py`
   (`CONTRACT_IDENTITY_EXEMPT_FIELDS`, from which
   `CONTRACT_IDENTITY_EXEMPT_ROOTS` is derived), **not** in the contract, so no
   contract edit can widen the exemption over `identity` or over a note;
2. the declaration must be that set **exactly** - no fifth entry, no repeat,
   and nothing missing. Pinning only the two *blocks* left a real gap: a newly
   declared sibling such as `superseded_official_archive.previous_sha256` sat
   under a permitted root and holds a genuine digest, so every earlier rule
   waved it through and the file quietly gained a second archive pointer;
3. each declared field must **exist and hold a 64-hex digest** - a declaration
   naming nothing, prose or an integer is refused with
   `CONTRACT_IDENTITY_EXEMPTION_INVALID`;
4. the value at a declared path must **be** the digest, not merely contain it,
   and every other string **and object key** in the file is scanned;
5. all four **declared digests are themselves scanned** across the whole
   document, each permitted only at its own registered path. The scan used to
   look for the current release pointer alone, so a candidate digest repeated
   in a note was invisible to it;
6. the digest count in the file's **bytes** must equal the count the structured
   walk saw, so a copy hidden in a duplicate key that JSON parsing drops cannot
   pass as exempt.

The contract is deliberately absent from `identity.files`, and the finalizer
refuses it there explicitly. Every other tracked file is scanned exactly as
before: the same digest in any unapproved tracked file is still
`IDENTITY_MAPPING_MISMATCH`.

### Inside a mapped file, the undeclared fields must be zero

The map records how many times each file carries each identity field, and the
eight declarations sum to 56. That proved the 56 were present; it said nothing
about a fifty-seventh reference through a field that file never declared -
`docs/RELOCATED_ARTIFACTS.csv` declares `archive_filename` and `archive_sha256`
and says nothing about `content_root_hash`.

That gap was the worst of both worlds. A mapped file is **rewritten** by an
identity update, and the rewrite is planned from the declared counts, so an
undeclared reference is not in the plan: it survives the finalization still
pointing at the superseded archive, inside a file the tool has just certified.
Every identity field is now counted in every mapped file, and a field the
contract does not declare for that file must occur **zero** times. The four
field names are pinned in code as `IDENTITY_FIELDS`; if `identity.fields`
records a different set, that disagreement is itself reported.

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

A **new** file - in practice the licence receipt alone - is created no-clobber. A
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

### Slot names are bounded, and the mapping is written down

A slot inside the recovery directory used to be named
`orig.<sequence>.<run id>.<the whole repository-relative path, flattened>`. That
made the name's length depend on its target's: the tree's longest tracked path
is 99 characters, which produced a 125-character filename, and under a deep
temporary directory the total crossed the Windows 260-character limit. Windows
reports that refusal as `ENOENT`, so it did not look like a length problem at
all - the transaction failed as `TRANSACTION_UNWRITABLE` with *no such file or
directory* for a file that was plainly there, and the rollback then failed the
same way for the same reason. Twenty-six transaction, rollback, cleanup and
lock tests failed this way inside the disposable validation run while passing
everywhere else.

Names are now `<kind>.<sequence>.<16-hex digest>` - **31 characters at most**,
whatever the target is called. The digest covers the run id, the kind, the
sequence and the exact repository-relative path, so two runs, two kinds and two
targets can never collide, and neither can two paths the old sanitizer
flattened to the same text (`a b.md` and `a_b.md`).

Nothing is lost by shortening the name. Each slot is recorded in an append-only
**recovery manifest**, `slots.jsonl`, inside the recovery directory: one JSON
object per line carrying the slot name, kind, sequence, the exact
repository-relative path, the original identity, size and mode, and the
expected identity. It is created exclusively and flushed as it grows, and after
the first record it is only ever appended to - a manifest that has been removed
or replaced is a refusal, not a silently restarted mapping. The same mapping
travels in the run's report under `slots`, so an operator reading a failure
never has to decode a filename.

### The budget is decided before the first mutation

Whether this run's names can fit is arithmetic, and it is answered while
nothing is on disk. Before a transaction touches anything it computes the
longest path it could create - the recovery directory plus the longest possible
slot name - and refuses with `TRANSACTION_PATH_TOO_LONG` if the platform will
not take it. Every tracked file, archive, receipt, lock and temporary is left
exactly as it was. The machine's `LongPathsEnabled` setting is **read and never
written**: it belongs to the operator, and a tool that quietly changed it would
be repairing the computer instead of its own names.

The validation run gets the same treatment from the other end. Its pytest base
directory is created **short**, on the same volume as the clone it validates,
one per run and never a shared fixed name. It carries an ownership token, and
it is removed only when that token is still the one this run wrote; a directory
that has been replaced, that is no longer a plain directory, or that will not
delete is **retained and reported** under `retained_basetemp` rather than swept
away.

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
| `LICENCE_DECLARATION_ABSENT` | the creator's declaration has not been recorded; there is nothing to finalize. This is the expected state until it is committed |
| `DECLARATION_UNTRACKED` | the declaration exists only in a working copy - no history, no review, no author |
| `DECLARATION_MODIFIED` | the declaration differs from its committed blob; the bytes being read are not the bytes that were reviewed |
| `DECLARATION_MALFORMED` | the declaration is not strict JSON, or is missing a required field (a duplicate key is a refusal, not a silent last-wins) |
| `DECLARATION_SCHEMA_VERSION` / `DECLARATION_DATE` | the declaration's schema version or declaration date is not one the contract admits |
| `DECLARATION_TEXT_MISMATCH` | `declared_text` is not EXACTLY the contracted paragraph - paraphrased, truncated, prefixed, widened, qualified or withdrawn |
| `DECLARATION_ARTWORK_SCOPE` / `DECLARATION_ARTWORK_MISSING` / `DECLARATION_ARTWORK_MISMATCH` | the declaration licenses other than the seven registered assets, or their bytes in the tree are no longer the bytes that were declared |
| `DECLARATION_ATTESTATION_CREATOR` / `DECLARATION_ATTESTATION_STATEMENT` / `DECLARATION_ATTESTATION_TIMESTAMP` / `DECLARATION_ATTESTATION_MALFORMED` | the creator attestation is absent, by the wrong creator, rewritten, or undated |
| `DECLARATION_GUIDANCE_CREDIT` | the scientific guidance credit is not exactly the contracted one - dropped, renamed, or inflated into a co-licence |
| `DECLARATION_UNREADABLE` | the declaration could not be read through the component-safe, no-follow walk - a link on the file, a junction on a parent, a special object, or a swap between inspection and open |
| `DECLARATION_SOURCE_UNCONFIGURED` | the contract declares no `declaration_source`, so there is nothing the release could rest on |
| `DECLARATION_WITHDRAWN_BEFORE_WRITE` / `DECLARATION_CHANGED_BEFORE_WRITE` | the declaration stopped qualifying, or changed, between validation and the write |
| `RECEIPT_DECLARATION_ABSENT` | the receipt names a declaration that is not in the tree - the hand-written receipt's real target |
| `RECEIPT_DECLARATION_UNTRACKED` / `RECEIPT_DECLARATION_MODIFIED` | the declaration the receipt rests on was never committed, or no longer equals its blob at HEAD |
| `RECEIPT_DECLARATION_MISMATCH` | the declaration's recomputed SHA-256 or git blob id is not the one the receipt commits to |
| `RECEIPT_DECLARATION_MALFORMED` / `RECEIPT_DECLARATION_UNREADABLE` / `RECEIPT_DECLARATION_ATTESTATION` | the declaration is not strict JSON, is missing a mandatory field, could not be read safely, or its creator attestation is not the contracted statement |
| `RECEIPT_DECLARATION_SCHEMA_VERSION` / `RECEIPT_DECLARATION_CREATOR` / `RECEIPT_DECLARATION_GUIDANCE_CREDIT` | the committed declaration's own schema version, creator or guidance credit is not one the contract admits. Checked on the DECLARATION, not merely on its agreement with the receipt |
| `RECEIPT_DISAGREES_WITH_DECLARATION` | the receipt and the committed declaration differ on the paragraph, the seven-artwork scope, the creator or the credit |
| `CONTRACT_DECLARES_SYNTHETIC_FIXTURE` | the tracked contract carries `synthetic_fixture` in any form; that key disables the reviewed-prose and scope pins and belongs only to test fixtures |
| `CCBY_ARTWORK_SCOPE_UNREVIEWED` / `CCBY_ARTWORK_IDENTITY_UNREVIEWED` / `CCBY_SCOPE_GLOBS_UNREVIEWED` | a contract surface - `ccby_artwork_paths`, `figures`, `ccby_activation_plan.scope.assets` or `ccby_artwork_scope_globs` - does not equal the seven path → SHA-256 identities and five directory scopes pinned in code |
| `CCBY_ARTWORK_PATH_NOT_REPOSITORY_RELATIVE` | an artwork path is filesystem-absolute, UNC, drive-absolute, home-prefixed or climbs out of the tree; joining it onto the repository root would read a file outside the repository |
| `RECEIPT_LICENCE_SOURCE` | the receipt does not carry `licence_source: creator_declaration` - absent, or naming a route this project does not use |
| `RECEIPT_CREATOR` / `RECEIPT_GUIDANCE_CREDIT` | the receipt names a creator or a credit that is not the contracted one |
| `RECEIPT_DECLARED_TEXT` / `RECEIPT_DECLARED_TEXT_SHA256` | the receipt's paragraph is not the contracted one, or its digest does not hash its own text |
| `CONTRACT_NOT_AT_HEAD` / `CONTRACT_UNTRACKED` / `CONTRACT_PATH_ESCAPE` | the contract is not the tracked one at HEAD |
| `RECEIPT_PREMATURE` / `RECEIPT_*` | the receipt pre-exists, or does not match the declaration |
| `RECEIPT_PATH_INVALID` | the contracted receipt path is a symlink, a directory or another special object, or resolves outside the repository |
| `RECEIPT_APPEARED_CONCURRENTLY` | a receipt appeared while this run was writing one; it is preserved and the run refuses |
| `FINALIZER_LOCK_HELD` | another finalization holds the worktree or staging lock, or died holding it |
| `TRANSACTION_TARGET_RECREATED` / `TRANSACTION_TARGET_NOT_REGULAR` | a tracked target was recreated after the move-aside, or is not a regular file |
| `TRANSACTION_STAGING_OCCUPIED` / `TRANSACTION_RECOVERY_OCCUPIED` | a run-owned staging or recovery slot, or the recovery manifest, was already occupied |
| `TRANSACTION_PATH_TOO_LONG` | the compact layout still will not fit on this platform; nothing was written |
| `POSTIMAGE_MUTATED_BEFORE_COMMIT` | a file this run wrote was edited from outside before the commit point |
| `PREDECESSOR_MUTATED` / `PREDECESSOR_RECOVERY_LOST` | the destination was rewritten during the move-aside, or a recovery copy disappeared |
| `VALIDATION_TREE_SYMLINK` / `VALIDATION_TREE_SUBMODULE` | a tracked symlink or gitlink cannot be reproduced in the validation tree |
| `VALIDATION_ALLOWLIST_UNPINNED` / `VALIDATION_ALLOWLIST_MISMATCH` | an ignored artifact was admitted without a pin, or does not match it |
| `INTERPRETER_UNTRUSTED` | an interpreter other than the running one was used and the contract pins none |
| `CCBY_ACTIVE_MARKER_CONDITIONAL` | the active wording is conditional, deferred or hypothetical rather than a grant in force |
| `CCBY_ACTIVE_MARKER_UNSCOPED` / `CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE` | the active wording does not name **both** Figure 1 and Figure 4 and CC BY 4.0, or carries no present-tense affirmative grant |
| `GITHUB_API_UNAVAILABLE` | pull request metadata could not be read |
| `APTOS_FONT_MISSING` / `APTOS_FONT_MISMATCH` | the pinned face is absent, or a different face was offered |
| `CCBY_ACTIVATION_PLAN_UNAUTHORED` | no author has written the activation wording |
| `CCBY_ACTIVATION_PARTIAL` | the plan does not cover all five licence surfaces |
| `CCBY_ACTIVATION_BLOCK_TOO_BROAD` | a bare marker was used instead of a complete source block |
| `CCBY_THIRD_PARTY_LEAKAGE` | activation disturbed a third-party rights token |
| `LICENCE_STATE_INCONSISTENT` | the five surfaces do not agree |
| `GIT_TREE_DIRTY` / `GIT_BRANCH_MISMATCH` / `GIT_HEAD_MISMATCH` | the worktree is not where it must be |
| `GIT_MAIN_MOVED` / `GIT_TAG_MOVED` / `GIT_REMOTE_BRANCH_MISMATCH` | a reference moved, per the **live** remote |
| `PR_STATE_UNEXPECTED` | the pull request is no longer open, draft, unmerged and correctly targeted |
| `FIGURE_IDENTITY_MISMATCH` | a figure or donor raster is not the pinned one |
| `PENDING_MARKER_COUNT` | the four licence records no longer all withhold the grant |
| `IDENTITY_MAPPING_MISMATCH` | the eight-file / fifty-six-reference map does not match the tree, or an identity appears in a tracked file the contract has not approved - including the contract itself, outside its declared historical/candidate fields |
| `CONTRACT_IDENTITY_EXEMPTION_INVALID` | the contract's field-level identity exemption is not a real declaration: it names nothing, is rooted outside the two pinned blocks, points at a field that is missing or is not a 64-hex digest, or the contract file could not be parsed |
| `PROTECTED_RECORD_MODIFIED` / `PROTECTED_RECORD_BLOB_MOVED` | a historical record, or its tracked blob, changed |
| `TECHNICAL_SOURCE_MISSING` / `TECHNICAL_SOURCE_MISMATCH` | the candidate is not the pinned technical source |
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
| `CCBY_SCOPE_UNREGISTERED_ASSET` | the activation newly identifies as Licensed Material something that is not one of the seven registered assets: a different complete path, a same-named file elsewhere, a bare filename that names no path, a URL or drive-absolute path outside the tree, an unrecognised extension, an undeclared directory glob, or an open-ended class. Counted for AFFIRMATIVE grants only, so rewriting a denial into a grant is a widening |
| `CCBY_ACTIVATION_DESTINATION_UNREVIEWED` | a destination block, the active publication row or the ACTIVE marker is not the wording pinned by digest in `REVIEWED_ACTIVATION_DESTINATIONS`; the prose about to be written is not the prose that was reviewed |
| `CCBY_DECLARATION_TEXT_UNREVIEWED` / `CCBY_PUBLIC_CREDIT_UNREVIEWED` / `CCBY_PUBLIC_CREDIT_MISSING` | `licence_declaration.text` is not the reviewed paragraph, the credit line is not the reviewed credit, or an authored destination does not carry it |
| `CCBY_SCOPE_DECLARATION_TOO_BROAD` | a declared directory scope in `ccby_artwork_scope_globs` reaches anything other than the registered works - an eighth raster, but since r3m also a README, a caption, an extensionless file, a subdirectory, or any symlink, junction or special object, none of which the reviewed shorthand `dir/**` was ever read to cover |
| `CCBY_SCOPE_DECLARATION_UNVERIFIABLE` | a declared scope is not a real directory, could not be inspected, or no longer holds the registered works it was reviewed to stand for |
| `CCBY_SCOPE_DECLARATION_UNVERIFIABLE` | a declared directory scope is not a directory in this tree, so what it reaches cannot be checked |
| `CCBY_ACTIVE_MARKER_ABSENT` | an authored destination block, or the published row, carries no registered marker |
| `RELEASE_STAGING_STALE_TEMP` | a finalizer temporary - file or dangling symlink - exists beside the destination, or appeared after the check |
| `RELEASE_STAGING_UNREADABLE` / `RELEASE_STAGING_UNWRITABLE` | the staging directory could not be listed, or the temporary could not be created exclusively |
| `RELEASE_DESTINATION_RECREATED` | the destination reappeared after the move-aside; this run will not overwrite it |
| `PREDECESSOR_SNAPSHOT_FAILED` / `PREDECESSOR_MUTATED` | the predecessor could not be snapshotted, or was rewritten by another process |
| `BYTES_MUTATED_AFTER_HASHING` | the archive changed between hashing and placement, or after it |
| `TRANSACTION_ROLLED_BACK` | an unexpected exception aborted the transaction; everything was undone |
| `ARTWORK_RECEIPT_INVALID` | (publication builder) a receipt is present but does not validate, so no licence row may be published |
| `ARCHIVE_LICENCE_BLOCK_NOT_UNIQUE` | the complete source block does not occur exactly once in the staged deposit notice |
| `ARCHIVE_LICENCE_BLOCK_EMPTY` | the activation source block is empty, so it would match at every position |
| `ARCHIVE_LICENCE_COLLATERAL_EDIT` | the rewrite changed bytes outside the one authored block; the message names the first differing offset |
| `ARCHIVE_LICENCE_DESTINATION_ALTERED` | the block written in place of the retired one is not the authored destination |
| `ARCHIVE_LICENCE_SOURCE_SURVIVED` | the retired PENDING block still appears somewhere the author did not reinstate it |
| `ARCHIVE_LICENCE_LINE_DELTA` | the deposit notice's line count moved by something other than the pinned `+2` |
| `ARCHIVE_LICENCE_ADJACENT_TEXT_CHANGED` | a pinned adjacent or third-party passage did not survive the rewrite at its original count |
| `ARCHIVE_LICENCE_ANCHOR_ABSENT` | a pinned adjacent passage is not in the staged notice, so holding it fixed would assert nothing |
| `ARCHIVE_LICENCE_ANCHOR_INSIDE_BLOCK` | a pinned adjacent passage lies inside the block being replaced, so proving the block changed would not prove that passage survived |
| `ARCHIVE_LICENCE_REPLACEMENT_UNPINNED` | the contract declares no line delta, declares one that differs from the value pinned in code, or holds no adjacent passage fixed |

## 9a. Verifying the release evidence manifest

`release_staging/evidence/RELEASE_MANIFEST.sha256` covers the release evidence
artifacts. It had two defects that made it unverifiable as written: a stray
`# ` and a UTF-8 **BOM** were prepended to the first entry, corrupting that
line, and the entries were rooted **inconsistently** - three were written
relative to `release_staging/evidence/` while `scorch_corrected_overlay_v1.0.1.zip`
was written relative to `release_staging/`. No single working directory
verified all four.

**One root is possible, and is now used: `release_staging/`.** Every entry is
written relative to it, so the deeper artifacts carry their `evidence/` prefix
and no manifest needs splitting. The manifest states its own root in a header
comment. There is no BOM and no `# ` before a digest; the only `#` lines are
whole-line comments, which `sha256sum -c` ignores.

The manifest lives one level below its own root, so it is named through
`evidence/` when invoked. Run from the repository root:

bash:

```bash
cd release_staging && sha256sum -c evidence/RELEASE_MANIFEST.sha256
```

PowerShell:

```powershell
Push-Location release_staging
Get-Content evidence\RELEASE_MANIFEST.sha256 |
  Where-Object { $_ -notmatch '^\s*#' -and $_.Trim() } |
  ForEach-Object {
    $expected, $rel = ($_ -split '\s+', 2)
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $rel.Trim()).Hash.ToLower()
    if ($actual -eq $expected) { "OK   $rel" } else { "FAIL $rel`n  expected $expected`n  actual   $actual" }
  }
Pop-Location
```

`sha256sum` prints `<path>: OK` per entry and exits 0 only if every line
verified. The PowerShell loop is not a `sha256sum` substitute - it is written
out longhand because Windows ships no `sha256sum`, and it reports each entry
the same way. It skips comment and blank lines, which is why the manifest's
documented root can live in the file itself.

The review bundle carries its own separate, self-verifying checksum file,
rooted at the bundle directory; see the `BUNDLE_SHA256SUMS.txt` header for its
own verification commands.

## 10. The remaining release conditions

Pull request #1's description should state these plainly. What was once four
conditions is now two, and one of those is mechanical.

1. ~~**Coauthor artwork approval.**~~ **RETIRED - it was never the right
   model.** Fawaz Bouhamad created the Figure 1 and Figure 4 artwork and
   licenses it; Dr. Najibi provided the scientific guidance behind those
   figures and is credited for that. Nothing is asked of Dr. Najibi, and no
   approval from them exists or is required.
2. ~~**The pinned Aptos Regular face.**~~ **RESOLVED - located, not
   provisioned.** The face was already present in this operator's Microsoft 365
   cloud-font cache; nothing was downloaded, substituted, or copied anywhere.
   See "Locating the pinned face" below. It stays outside the repository, the
   bundle and every review packet: it is non-redistributable, and
   `ccby_excluded_scope` keeps the CC BY activation away from all font rights.
3. ~~**The unauthored CC BY activation plan.**~~ **RESOLVED - authored, not
   applied.** The exact from/to pairs for all five licence surfaces are in
   `ccby_activation_plan.replacements`, and each carries the public credit
   line. Authoring is not applying; see "The activation plan is AUTHORED"
   above.
4. **The creator's CC BY declaration.** Absent until
   `docs/FIGURE_01_04_CC_BY_CREATOR_DECLARATION.json` is committed. Writing and
   committing it is the creator's own act and needs nobody else.
5. **The superseded official archive.** The tracked records still point at
   `scorch_processed_data_v1.0.0.zip`, whose payload is superseded. The
   corrected candidate exists locally and unpublished. Resolved by running
   `finalize`, which is gated on 4.

Release acceptance requires zero skips, so every optional input above must be
supplied on the machine that runs the accepted validation.

### Locating the pinned face

Do **not** download Aptos from anywhere. It ships with Microsoft 365 and is
cached per user, under **numeric filenames** - there is no `Aptos.ttf` to find,
which is why a search by name reports nothing on a machine that has it:

    %LOCALAPPDATA%\Microsoft\FontCache\4\CloudFonts\Aptos\<digits>.ttf

Identify it by **hash, never by filename**: hash every file under that
directory and take the one equal to `aptos_font_sha256` in the contract. The
sibling `Aptos Display`, `Aptos Narrow` and `Aptos Mono` directories are
different faces and are not substitutes. Confirm the match by reading the
font's own name table - the pinned face reports family `Aptos`, subfamily
`Regular`. Then point `SCORCH_APTOS_FONT` (or `--aptos-font`) at that path.

If no file matches, stop: the correct outcome is the explicit
`APTOS_FONT_MISSING` blocker and an honest skip, never a substituted face.

## 11. What this tool never does

It never commits, pushes, merges, tags, creates a release, publishes, or
touches the deposit records at the archive host. Those remain deliberate human
actions, taken after the declaration is recorded and this tool has reported
success.
