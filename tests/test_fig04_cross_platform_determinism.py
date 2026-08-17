"""Figure 4 determinism, split into the two claims that are NOT the same claim.

A Linux audit regenerated Figure 4 **pixel-identically** but emitted **different
PNG bytes**. Both observations are correct, and conflating them produced a false
portability claim. The two guarantees are therefore stated and enforced apart:

1. **Cross-platform pixel determinism (portable, always required).**
   The producer's raw RGB output must equal the shipped asset's raw RGB exactly,
   on every supported platform. This is the scientific and visual guarantee:
   the figure is the same image everywhere. It is asserted unconditionally.

2. **Canonical-byte determinism (toolchain-bound, conditionally required).**
   The exact PNG byte stream - and therefore SHA-256 ``74ea37f0...`` - is a
   property of the *encoder*, not of the figure. Pillow chooses filters and
   zlib emits the deflate stream, so a different Pillow or zlib build
   legitimately produces different bytes from identical pixels. Byte identity is
   required only where the declared canonical toolchain is present. Elsewhere
   the check SKIPS with an explicit reason and the pixel check still runs, so a
   non-canonical platform can never silently pass a weaker gate.

Consequently the shipped asset is **materialized, not re-encoded**, on
non-canonical platforms: the approved canonical PNG in ``assets/frozen_figures/``
is the artifact of record and is copied, while its pixels are verified against a
fresh producer run either way. Nothing here alters the approved Figure 4 asset
or its pixels.

The publication route must continue to ship the exact approved hash; that is
asserted independently of platform, because the route copies approved bytes
rather than re-encoding them.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
FIG04 = REPO / "assets" / "frozen_figures" / "fig04" / "Figure_04.png"
DONOR = (REPO / "scripts" / "figures" / "fig04" / "donor" /
         "Figure_04_approved_horizontal.png")
PRODUCER = (REPO / "scripts" / "figures" / "fig04" /
            "make_fig04_symmetry_final.py")
PUB = REPO / "publication_outputs" / "figures" / "Figure_04" / "Figure_04.png"

APPROVED_SHA = ("74ea37f0ab54453a7c28895edd381cad3a75c199af88c60de6715472"
                "1db23484")
CANVAS = (2531, 4500, 3)          # (height, width, channels) as decoded

# ---------------------------------------------------------------------------
# Declared canonical encoder toolchain for BYTE identity.
#
# Deliberately keyed on the PNG encoder stack (Pillow + zlib), NOT on the
# operating system: the OS does not write PNG bytes, the encoder does. A Linux
# machine carrying these exact versions is canonical; a Windows machine with a
# different Pillow is not. Byte identity is claimed for this stack alone.
# ---------------------------------------------------------------------------
CANONICAL_PILLOW = "12.2"         # major.minor
CANONICAL_ZLIB = "1.3.1"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rgb(p: Path) -> np.ndarray:
    from PIL import Image
    with Image.open(p) as im:
        return np.array(im.convert("RGB"))


def _toolchain():
    import zlib

    import PIL
    pillow_mm = ".".join(PIL.__version__.split(".")[:2])
    return {"pillow": PIL.__version__, "pillow_major_minor": pillow_mm,
            "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
            "canonical": (pillow_mm == CANONICAL_PILLOW
                          and zlib.ZLIB_RUNTIME_VERSION == CANONICAL_ZLIB)}


# The canonical asset, the immutable donor and the active producer are all
# TRACKED files. A checkout missing any of them is broken, not merely
# unconfigured, so their absence is a FAILURE. The module-wide skipif that used
# to sit here turned a deleted canonical figure into a green run.
def test_required_figure04_inputs_are_present():
    missing = [str(p.relative_to(REPO)) for p in (FIG04, DONOR, PRODUCER)
               if not p.is_file()]
    assert not missing, (
        f"tracked Figure 4 inputs are missing from this checkout: {missing}. "
        f"These are committed files, so this is a broken tree, not an "
        f"unconfigured one.")


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory):
    """A fresh producer run. Never optional - the inputs are tracked."""
    for p in (PRODUCER, DONOR):
        assert p.is_file(), (
            f"required tracked file missing: {p.relative_to(REPO)}")
    out = tmp_path_factory.mktemp("fig04_regen")
    subprocess.run([sys.executable, str(PRODUCER), "--out", str(out),
                    "--src", str(DONOR)], check=True, cwd=REPO)
    png = out / "Figure_04.png"
    assert png.is_file(), "producer emitted no Figure_04.png"
    return png


# ---------------------------------------------------------------------------
# 1. The approved asset itself is untouched.
# ---------------------------------------------------------------------------
def test_approved_asset_bytes_are_unchanged():
    """The artifact of record must still be exactly the approved PNG."""
    assert _sha(FIG04) == APPROVED_SHA, (
        "the approved Figure 4 asset has been altered - this pass must never "
        "change its bytes or pixels")
    assert _rgb(FIG04).shape == CANVAS


# ---------------------------------------------------------------------------
# 2. Cross-platform PIXEL determinism - always required.
# ---------------------------------------------------------------------------
def test_pixel_identity_is_required_on_every_platform(regenerated):
    # No skip guard: this comparison must ALWAYS run. It is the portable
    # guarantee, and the only one that says the figure is the same image.
    generated, shipped = _rgb(regenerated), _rgb(FIG04)
    assert generated.shape == shipped.shape, (
        f"canvas differs: regenerated {generated.shape} vs shipped "
        f"{shipped.shape}")
    if not np.array_equal(generated, shipped):
        diff = (generated != shipped).any(axis=-1)
        ys, xs = np.nonzero(diff)
        raise AssertionError(
            f"raw-RGB pixel identity FAILED on this platform: "
            f"{int(diff.sum())} differing pixels, first at "
            f"(row={ys[0]}, col={xs[0]}). Pixel identity is portable and "
            f"unconditional - a pixel difference is a real defect, never an "
            f"encoder difference.")


# ---------------------------------------------------------------------------
# 3. Canonical-BYTE determinism - only on the declared toolchain.
# ---------------------------------------------------------------------------
def test_byte_identity_only_claimed_on_the_canonical_toolchain(regenerated):
    # This is the ONE assertion in the module that may legitimately skip, and
    # only for a noncanonical encoder stack - never for a missing input.
    tc = _toolchain()
    if not tc["canonical"]:
        pytest.skip(
            f"non-canonical PNG encoder toolchain (Pillow {tc['pillow']}, "
            f"zlib {tc['zlib_runtime']}; canonical is Pillow "
            f"{CANONICAL_PILLOW}.x with zlib {CANONICAL_ZLIB}). Byte identity "
            f"is NOT claimed here; pixel identity is asserted separately and "
            f"unconditionally, and the approved canonical PNG is materialized "
            f"rather than re-encoded.")
    assert _sha(regenerated) == APPROVED_SHA, (
        f"on the declared canonical toolchain (Pillow {tc['pillow']}, zlib "
        f"{tc['zlib_runtime']}) the producer must reproduce the approved PNG "
        f"byte stream exactly")


def test_the_two_determinism_claims_are_documented_separately():
    """The distinction must be written down, not merely implemented."""
    low = (__doc__ or "").lower()
    assert "pixel determinism" in low and "byte determinism" in low
    assert "not the same claim" in low
    doc = (REPO / "assets" / "frozen_figures" / "README.md").read_text(
        encoding="utf-8").lower()
    assert "pixel" in doc and "byte" in doc, (
        "assets/frozen_figures/README.md does not distinguish pixel identity "
        "from PNG byte identity")


# ---------------------------------------------------------------------------
# 4. The publication route still ships the exact approved bytes.
# ---------------------------------------------------------------------------
def test_publication_route_ships_the_exact_approved_hash():
    if not PUB.is_file():
        pytest.skip("publication_outputs/ not materialized in this checkout")
    assert _sha(PUB) == APPROVED_SHA, (
        "the publication route no longer ships the approved Figure 4 bytes; "
        "it must COPY the approved asset, never re-encode it")
    assert np.array_equal(_rgb(PUB), _rgb(FIG04))


# ---------------------------------------------------------------------------
# 5. Adversarial regressions on the producer's identity contracts.
#
# A gate that has never been observed to fire is a decoration. Each mutation
# below breaks exactly one contract and requires the producer to refuse.
# ---------------------------------------------------------------------------
def _producer_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_fig04_producer", PRODUCER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CANONICAL_PROFILE = {"pillow": "12.2.0", "pillow_major_minor": "12.2",
                     "zlib_runtime": "1.3.1", "canonical": True}
NONCANONICAL_PROFILE = {"pillow": "11.0.0", "pillow_major_minor": "11.0",
                        "zlib_runtime": "1.2.13", "canonical": False}


def test_producer_declares_the_confirmed_raw_rgb_digest():
    """The pinned digest must equal the frozen asset's real raw RGB."""
    mod = _producer_module()
    assert mod.EXPECTED_RAW_RGB_SHA256 == hashlib.sha256(
        _rgb(FIG04).tobytes()).hexdigest(), (
        "the producer's pinned raw-RGB digest does not match the shipped asset")
    assert mod.EXPECTED_PNG_SHA256 == APPROVED_SHA


def test_missing_donor_exits_nonzero_and_writes_nothing(tmp_path):
    out = tmp_path / "out"
    absent = tmp_path / "no_such_donor.png"
    proc = subprocess.run(
        [sys.executable, str(PRODUCER), "--out", str(out), "--src",
         str(absent)], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode != 0, "a missing donor was accepted"
    assert "donor not found" in (proc.stdout + proc.stderr)
    assert not out.exists() or not any(out.iterdir()), (
        "the producer wrote output despite having no donor")


def test_hash_mutated_donor_exits_nonzero(tmp_path):
    fake = tmp_path / "donor.png"
    data = bytearray(DONOR.read_bytes())
    data[-1] ^= 0xFF                      # still a file, no longer the donor
    fake.write_bytes(bytes(data))
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, str(PRODUCER), "--out", str(out), "--src",
         str(fake)], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode != 0, "a donor with the wrong hash was accepted"
    combined = proc.stdout + proc.stderr
    assert "donor" in combined.lower() and "sha256" in combined.lower()


@pytest.mark.parametrize("profile,label", [
    (CANONICAL_PROFILE, "canonical"),
    (NONCANONICAL_PROFILE, "noncanonical"),
])
def test_wrong_raw_pixel_digest_fails_on_every_stack(tmp_path, profile, label):
    """Pixel identity is portable: no encoder excuses a wrong image."""
    mod = _producer_module()
    mod.EXPECTED_RAW_RGB_SHA256 = "0" * 64
    with pytest.raises(mod.Fig04ContractError) as exc:
        mod.build(DONOR, tmp_path / f"out_{label}", encoder=profile)
    assert "raw RGB pixel sha256" in str(exc.value)


def test_wrong_encoded_digest_fails_under_canonical_policy():
    mod = _producer_module()
    with pytest.raises(mod.Fig04ContractError) as exc:
        mod.classify_encoded_identity("f" * 64, CANONICAL_PROFILE)
    assert "canonical encoder stack" in str(exc.value)


def test_different_valid_encoding_is_accepted_only_off_the_canonical_stack():
    """Same pixels, different PNG bytes: correct there, a violation here."""
    mod = _producer_module()
    other = "a" * 64
    assert mod.classify_encoded_identity(other, NONCANONICAL_PROFILE) == (
        "noncanonical-byte-encoding")
    with pytest.raises(mod.Fig04ContractError):
        mod.classify_encoded_identity(other, CANONICAL_PROFILE)
    # ... and the approved bytes are never called "noncanonical".
    assert mod.classify_encoded_identity(
        APPROVED_SHA, NONCANONICAL_PROFILE) == "canonical-byte-identity"
    assert mod.classify_encoded_identity(
        APPROVED_SHA, CANONICAL_PROFILE) == "canonical-byte-identity"


def test_a_real_reencoding_keeps_pixels_and_changes_bytes(tmp_path):
    """Demonstrates the phenomenon the split policy exists for."""
    from PIL import Image
    with Image.open(FIG04) as im:
        rgb = im.convert("RGB")
        alt = tmp_path / "reencoded.png"
        rgb.save(alt, format="PNG", compress_level=1)
    assert np.array_equal(_rgb(alt), _rgb(FIG04)), "re-encoding changed pixels"
    assert _sha(alt) != APPROVED_SHA, (
        "a deliberately different encoding produced identical bytes, so this "
        "machine cannot demonstrate the pixel/byte distinction")


def test_only_the_encoded_byte_check_may_ever_skip():
    """No skip may guard the pixel comparison or any tracked-input check."""
    import ast
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    skipping = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "skip"):
                skipping.add(node.name)
    assert skipping <= {
        "test_byte_identity_only_claimed_on_the_canonical_toolchain",
        "test_publication_route_ships_the_exact_approved_hash",
    }, (f"unexpected skip() in: "
        f"{sorted(skipping - {'test_byte_identity_only_claimed_on_the_canonical_toolchain', 'test_publication_route_ships_the_exact_approved_hash'})}")
    assert "test_pixel_identity_is_required_on_every_platform" not in skipping
