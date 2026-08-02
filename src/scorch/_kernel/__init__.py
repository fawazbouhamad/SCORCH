"""Canonical SCORCH numerical kernel (verbatim copies).

The modules in this subpackage are byte-for-byte copies of the canonical
scientific kernel used to produce every number in the SCORCH paper:

* ``ellipse_pca.py``  -- PCA / ellipse utilities (sigma-scaled principal-axis
  ellipses with the 1 km^2 eigenvalue variance floor; the former 1 km
  semi-axis floor was removed 2026-07-28 and is documented in the module).
* ``clustering.py``   -- spatial-clustering abstraction (DBSCAN and friends on
  precomputed distance matrices; grid-cell distance helper).

Do NOT edit these files: scientific identity with the published catalog
depends on them remaining unchanged. Public, documented wrappers live in
``scorch.ellipses``, ``scorch.clustering``, and ``scorch.dbscan_params``.
"""
