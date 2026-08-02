"""Release-local path configuration for the SCORCH public release (Phase F4).

Sanitized, release-relative path resolution shared by every figure, pipeline,
LGCP and validation script in this release. Contains NO absolute or
user-specific paths. The release root is auto-discovered as the nearest
ancestor directory containing both ``scripts/`` and ``configs/``, so the
package is fully relocatable.

Layout mapping:
    <root>/scorch_data/  -> the processed-data deposit
                            (scorch_processed_data_v1.0.0 layout: catalogs/,
                            gridded/, lgcp/, power_law/, selected_days/,
                            validation_kfold/, validation_station/, ...)
    <root>/data/auxiliary/     -> small auxiliary inputs shipped with the code
                            (e.g. method-A parameter grid for Fig. B)
    <root>/reproduced/   -> ALL regenerated outputs land here
                            (frozen assets and deposit data are never touched)

Override points (environment variables):
    SCORCH_RELEASE_ROOT -> explicit release root (else auto-discovered)
    SCORCH_DATA_DIR     -> processed-data deposit root
                           (default: <root>/scorch_data)
    SCORCH_OUT_DIR      -> regenerated-output root (default: <root>/reproduced)

``SCORCH_CLEAN_DATA`` / ``SCORCH_CLEAN_OUT`` are honoured as legacy aliases
for compatibility with the Phase F3 candidate scripts.

Raw ERA5 is not redistributed by this release; no script in this module's
scope reads the raw ERA5 archive (see docs/SOURCE_DATA_PROVENANCE.md).
"""
import os


def _discover_root() -> str:
    env = os.environ.get("SCORCH_RELEASE_ROOT")
    if env and os.path.isdir(env):
        return os.path.abspath(env)
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    while True:
        if (os.path.isdir(os.path.join(cur, "scripts"))
                and os.path.isdir(os.path.join(cur, "configs"))):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            # fallback: common/ -> figures/ -> scripts/ -> <root>
            return os.path.dirname(os.path.dirname(os.path.dirname(here)))
        cur = parent


RELEASE_ROOT = _discover_root()

DATA_DIR = (os.environ.get("SCORCH_DATA_DIR")
            or os.environ.get("SCORCH_CLEAN_DATA")
            or os.path.join(RELEASE_ROOT, "scorch_data"))
AUX_DIR = os.path.join(RELEASE_ROOT, "data", "auxiliary")
GENERATED_DIR = (os.environ.get("SCORCH_OUT_DIR")
                 or os.environ.get("SCORCH_CLEAN_OUT")
                 or os.path.join(RELEASE_ROOT, "reproduced"))

# Deposit sub-directories searched (in order) when no hint matches.
_SEARCH_SUBDIRS = (
    "catalogs", "gridded", "selected_days", "lgcp", "validation_kfold",
    "validation_station",
    os.path.join("power_law", "statistics"),
    os.path.join("power_law", "largest_daily_ellipse"),
    os.path.join("power_law", "largest_event_ellipse"),
)


def data_file(name: str, *subdirs: str) -> str:
    """Resolve ``name`` inside the processed-data deposit.

    ``subdirs`` (joined) is the preferred deposit location and is tried
    first; the known deposit sub-directories and the deposit root are tried
    as fallbacks. If nothing exists yet (deposit not downloaded), the
    preferred path is returned so the caller fails with a readable
    file-not-found error naming the expected location.
    """
    candidates = []
    if subdirs:
        candidates.append(os.path.join(DATA_DIR, *subdirs, name))
    candidates.append(os.path.join(DATA_DIR, name))
    for sd in _SEARCH_SUBDIRS:
        candidates.append(os.path.join(DATA_DIR, sd, name))
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


MASTER_CSV = data_file(
    "scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv",
    "catalogs")
# The deposit ships the master as CSV only; XLSX path kept for API
# compatibility with scripts that offer an Excel fallback.
MASTER_XLSX = os.path.splitext(MASTER_CSV)[0] + ".xlsx"
LABELS_CSV = data_file("final_labels_event_global_max.csv", "catalogs")


def generated(subdir: str) -> str:
    """Return (and create) a subdirectory of the reproduced-outputs root."""
    path = os.path.join(GENERATED_DIR, subdir)
    os.makedirs(path, exist_ok=True)
    return path

# ---------------------------------------------------------------------------
# Reproducible-build epoch -- declared ONCE for the whole release.
# ---------------------------------------------------------------------------
# matplotlib stamps PDF /CreationDate (and /ModDate when it emits one) from
# the wall clock unless SOURCE_DATE_EPOCH is set, so two builds of the same
# figure on different days differ in exactly those bytes while the rendered
# content is identical. That alone defeats byte-for-byte reproduction.
#
# CANONICAL_SOURCE_DATE_EPOCH is the approved release instant expressed as a
# reproducible-builds SOURCE_DATE_EPOCH (integer seconds since the Unix
# epoch, UTC):
#
#     1785374765  ==  2026-07-30T01:26:05Z  ==  2026-07-29T21:26:05-04:00
#
# That is the SAME physical instant carried by the previously approved PDF
# metadata; only the representation changed, from a local-time rendering to
# the UTC rendering the specification requires. matplotlib converts the
# epoch with tzinfo=UTC, so the PDFs carry
#
#     /CreationDate (D:20260730012605Z)
#
# which cannot depend on the machine timezone, locale, user, temporary
# directory or path. A timezone-aware local datetime is NOT used instead:
# matplotlib 3.10.9 renders the offset from timedelta.seconds rather than
# total_seconds(), so a correct -04:00 instant emits "-20'00'".
#
# See https://reproducible-builds.org/specs/source-date-epoch/
CANONICAL_SOURCE_DATE_EPOCH = 1785374765


class SourceDateEpochError(RuntimeError):
    """A pre-set SOURCE_DATE_EPOCH conflicts with the declared release epoch."""


def enforce_source_date_epoch(env=None) -> int:
    """Pin SOURCE_DATE_EPOCH to the declared release epoch.

    absent                -> set it, so a public build is deterministic by
                             default with no operator action;
    present and equal     -> accepted unchanged;
    present and different -> refuse loudly. Silently honouring a foreign
                             epoch would emit PDFs that differ from the
                             published ones while every other check passed;
    present and malformed -> refuse loudly for the same reason. int() would
                             otherwise raise deep inside matplotlib, and a
                             value like " 12 " or "0012" would be accepted
                             as some other date.

    Mutates ``env`` (default ``os.environ``) so the caller can propagate the
    value to child processes, and returns the declared epoch.
    """
    if env is None:
        env = os.environ
    declared = CANONICAL_SOURCE_DATE_EPOCH
    raw = env.get("SOURCE_DATE_EPOCH")
    if raw is None or raw == "":
        env["SOURCE_DATE_EPOCH"] = str(declared)
        return declared
    if not raw.isdigit():
        raise SourceDateEpochError(
            "SOURCE_DATE_EPOCH is malformed: {!r}. This release declares "
            "{} (2026-07-30T01:26:05Z). Refusing to build: a malformed "
            "value would silently change every generated PDF.".format(
                raw, declared))
    if int(raw) != declared:
        raise SourceDateEpochError(
            "SOURCE_DATE_EPOCH is set to {}, but this release declares {} "
            "(2026-07-30T01:26:05Z). Refusing to build: honouring a "
            "different epoch would produce PDFs that do not match the "
            "published artifacts. Unset the variable to use the declared "
            "value.".format(raw, declared))
    env["SOURCE_DATE_EPOCH"] = str(declared)
    return declared

