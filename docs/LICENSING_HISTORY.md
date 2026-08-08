# LICENSING HISTORY

This file records how the licensing of the SCORCH **software** has changed
over the life of the public repository, so that anyone holding an older copy
can tell which terms apply to it.

## Summary

| Revisions | Software licence | Status |
|---|---|---|
| Public pre-release repository snapshots up to and including the `v1.0.0` tag target (commit `184f15c6`) and the subsequent `main` commit `bd6e4608` | **MIT** | Historical. Still in force for those revisions. |
| The forthcoming formal v1.0.0 release onward | **GPL-3.0-only** | Current. |

> The existing `v1.0.0` tag currently points at a **pre-release repository
> snapshot**, not the completed formal release. Final tag alignment is a
> separate release stop gate; the tag object and its commit are preserved
> as provenance and are not moved in this round.

## What the change does and does not do

The SCORCH software in **this** release and all later releases is licensed
under the GNU General Public License, version 3 only (`GPL-3.0-only`). The
complete, unmodified licence text is in the repository's root `LICENSE`
file.

**Earlier public revisions remain under the licence that was included with
those revisions.** A permissive licence grant, once made publicly, cannot be
withdrawn retroactively: anyone who obtained SCORCH at or before commit
`bd6e4608` received it under the MIT terms shipped in that revision's
`LICENSE` file, and they keep those MIT rights in that copy for as long as
they wish to rely on them. Nothing in this document, in the new `LICENSE`
file, or in the repository history revokes, disclaims, or attempts to
reinterpret that grant. No git history has been rewritten to conceal it, and
the MIT text remains readable at those commits.

The relicensing applies going forward, to the code as distributed from this
release.

## Authority to relicense

The copyright holders of the SCORCH software are **Fawaz Bouhamad** and
**Nasser Najibi**, as named in the MIT notice carried by the earlier
revisions. Relicensing requires the agreement of the copyright holders.

Contributor audit of the complete git history (all branches):

| Author identity | Commits |
|---|---|
| Fawaz Bouhamad (personal address) | 29 |
| Fawaz Bouhamad (institutional address) | 1 |

Addresses are omitted here deliberately; both identities belong to the same
author and remain visible in the commit metadata itself for any auditor.

There are no third-party contributors, so no outside contributor's consent
is implicated. (`GitHub <noreply@github.com>` appears twice as *committer*
only — the standard identity recorded for edits made through the GitHub web
interface — and is not an authoring party.)

No third-party source code is vendored into this repository. Every software
dependency is installed from PyPI or CRAN at build time and is separately
licensed; the inventory is in `docs/THIRD_PARTY_DEPENDENCIES.md`.

## Compatibility

No GPL-incompatible code is bundled. Every Python dependency is BSD-, MIT-,
Apache-2.0-, PSF- or HPND-licensed, all of which are one-way compatible with
GPL-3.0. The R `spatstat` family is GPL-2-or-later and is invoked as a
**separate external process** (`Rscript`) rather than linked, so it raises no
combination question; its terms are in any case GPL-3.0 compatible.

## What is *not* GPL

The GPL applies to the SCORCH **software**. It is not applied to, and does
not override, any of the following, each of which keeps its own terms:

- the processed-data Zenodo record and everything deposited in it;
- ERA5-derived material (Copernicus/ECMWF terms and required notice);
- GHCN-Daily material (NOAA/NCEI source and use terms);
- the manuscript text and any journal-formatted material;
- Figure 1 and Figure 4, and the other author-created figure assets;
- author-created documentation and record metadata (CC BY 4.0);
- third-party dependencies.

The authoritative, non-overlapping path-to-licence table is
`docs/LICENSES_AND_ATTRIBUTION.md`.

## Citation is requested, not required by the licence

If you use SCORCH, please cite the software archive and the associated
manuscript; if you use the deposited data, please also cite the data
archive. This is a request grounded in scholarly practice. It is **not** an
additional condition of the GPL. The GNU project is explicit that a
mandatory research-paper citation requirement is not a permissible added
restriction under the GPL, and none is imposed here.
