# Provenance records

This directory preserves the auditable record of scientific corrections and
superseded artifacts associated with the SCORCH release.

## Layout

| Directory | Contents |
| --- | --- |
| `corrections/` | Reproducible evidence for scientific corrections made before release. `corrections/tmax_weighted_centroids/` documents the correction that replaced unweighted PCA-origin structure centroids with raw-Celsius Tmax-weighted centroids, including the freeze manifests, displacement audits, corrected-output hash manifest, and equivalence reports produced during that work. |
| `legacy/` | Explanatory records for superseded artifacts that are no longer distributed. `legacy/figure09/` retains the pointer README for the superseded pre-release Figure 9 renders, whose bytes are preserved only in the local processed-data archive candidate. |

## Status

These records exist to support auditability of the released science. They are
not active workflow inputs unless explicitly referenced by the reproduction
system. Nothing in this directory is required to run the pipeline or to
reproduce the published outputs.
