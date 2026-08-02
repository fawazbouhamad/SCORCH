"""SCORCH: spatiotemporal organization of regionally extensive heatwaves.

Installable companion package to the SCORCH framework paper. It wraps the
canonical scientific kernel (verbatim in ``scorch._kernel``) with a small,
documented API:

  * :func:`identify_heatwaves`  -- per-box heatwave labelling of a 0/1 daily
    exceedance series (canonical >=3-day / >=3-exceedance rule).
  * :func:`cluster_structures`  -- daily DBSCAN clustering of the
    heatwave-labelled grid cells on the precomputed grid-cell distance
    matrix.
  * :func:`fit_pca_ellipses`    -- canonical sigma=1.25 PCA ellipse geometry.
  * :func:`classify_events`     -- mechanical Type 1-4 event typology.
  * :func:`load_master` / :func:`validate_master` / :func:`export_master` --
    master ellipse catalog I/O and schema checks.

Command line: ``scorch --help`` (fetch-data, reproduce, validate-sources,
validate-deposit, version).
"""
from __future__ import annotations

__version__ = "1.0.0"

from .labeling import identify_heatwaves, label_heatwaves        # noqa: F401
from .clustering import cluster_structures, cluster_day_cells    # noqa: F401
from .ellipses import fit_pca_ellipses, fit_day_ellipses         # noqa: F401
from .typology import classify_events, derive_type               # noqa: F401
from .catalog import (                                           # noqa: F401
    load_master,
    load_event_parameters,
    validate_master,
    validate_event_parameters,
    export_master,
)
from .thresholds import (                                        # noqa: F401
    aggregate_to_one_degree,
    compute_p95_thresholds,
    label_exceedance,
)
from .selection import select_days, build_events                 # noqa: F401
from .dbscan_params import (                                     # noqa: F401
    select_modal,
    select_day_parameters,
    event_global_max_parameters,
)

__all__ = [
    "__version__",
    "identify_heatwaves", "label_heatwaves",
    "cluster_structures", "cluster_day_cells",
    "fit_pca_ellipses", "fit_day_ellipses",
    "classify_events", "derive_type",
    "load_master", "load_event_parameters",
    "validate_master", "validate_event_parameters", "export_master",
    "aggregate_to_one_degree", "compute_p95_thresholds", "label_exceedance",
    "select_days", "build_events",
    "select_modal", "select_day_parameters", "event_global_max_parameters",
]
