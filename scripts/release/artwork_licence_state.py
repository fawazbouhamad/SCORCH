#!/usr/bin/env python3
"""The single source of truth for the Figure 1 / Figure 4 artwork licence state.

Three separate places used to answer "is CC BY in force over the artwork?", and
all three answered it by asking whether a receipt FILE EXISTED. A file called
``docs/FIGURE_01_04_CC_BY_AUTHORIZATION_RECEIPT.json`` containing
``{"schema_version": "1.0.0"}`` was therefore enough to flip the publication
builder and the repository guards into asserting an active copyright licence
over a coauthor's artwork. That is the defect this module exists to remove.

Activation now requires a receipt that VALIDATES: correct schema, the exact
contracted login, a body that is exactly the contracted authorization text,
well-formed timestamps, and exactly the seven contracted artwork paths whose
recorded hashes still match the files on disk. Anything less is not ACTIVE.

Deliberately dependency-light - standard library only. The publication builder
imports this, and it must not acquire netCDF4 or the deposit contract as a
transitive dependency just to render a licence row.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.dont_write_bytecode = True

#: The two coherent states. Anything else is INCONSISTENT and is never
#: rounded up to ACTIVE.
PENDING = "pending"
ACTIVE = "active"
INCONSISTENT = "inconsistent"

TRACKED_CONTRACT_REL = "scripts/release/finalizer_contract.json"

#: "Figure 1"/"Fig. 4" but never "Figure 11"/"Fig. 10"; plus the path tokens.
ARTWORK_RX = re.compile(
    r"fig0[14]\b|Figure_0[14]|Figure [14](?!\d)|Fig\. [14](?!\d)", re.I)
CCBY_RX = re.compile(r"CC BY 4\.0|Creative Commons Attribution 4\.0", re.I)

#: An ISO-8601 UTC instant, as GitHub renders comment timestamps. Shape only -
#: a shape test accepts 2026-13-45T99:99:99Z, so the value is also PARSED.
TIMESTAMP_RX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def parse_timestamp(value):
    """Parse an ISO-8601 UTC instant, or return None if it is not one.

    Shape and validity are different questions. ``2026-13-45T99:99:99Z`` has
    the right shape and is not a date, and a receipt carrying it would sail
    past a regex while recording an impossible moment.
    """
    from datetime import datetime, timezone
    text = str(value or "")
    if not TIMESTAMP_RX.match(text):
        return None
    # Fractional seconds are PRESERVED. Truncating to whole seconds made
    # ...T00:00:00.001Z and ...T00:00:00.999Z compare equal, so an ordering
    # check could not tell an edit that preceded an activation from one that
    # followed it.
    core = text[:-1]
    fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in core else "%Y-%m-%dT%H:%M:%S"
    try:
        return datetime.strptime(core, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _reject_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def loads_strict(text):
    """Parse JSON, rejecting duplicate keys anywhere in the document."""
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_hex(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def normalize_prose(text):
    """Whitespace-normalize so hard wrapping cannot defeat an exact match."""
    return " ".join(str(text).replace("\r\n", "\n").split())


def repository_root(start=None):
    """The repository root, derived from this file unless told otherwise."""
    if start is not None:
        return Path(start)
    return Path(__file__).resolve().parents[2]


def load_trusted_contract(repo_root=None):
    """Read the tracked contract. Raises on missing or malformed JSON."""
    path = repository_root(repo_root) / TRACKED_CONTRACT_REL
    return loads_strict(path.read_text(encoding="utf-8"))


def receipt_path(repo_root=None, contract=None):
    root = repository_root(repo_root)
    contract = contract if contract is not None else load_trusted_contract(root)
    return root / contract["authorization_receipt"]["tracked_path"]


def resolve_receipt_path(repo_root=None, contract=None):
    """The receipt path, or the reason it is not one. ``(path, issues)``.

    The contracted path names a location INSIDE the repository, and a receipt
    is a plain file sitting at it. Neither was enforced. ``Path.is_file()``
    follows symlinks and answers True for a link pointing anywhere at all, so a
    symlink at the contracted path aimed at a valid receipt OUTSIDE the
    repository - in a sibling checkout, in a temp directory, on a network
    share - was read, validated, and could carry the artwork to ACTIVE. The
    document that licences a coauthor's copyright has to be in the repository
    that claims the licence.

    So the path must resolve inside the root, and it must be a REGULAR FILE by
    ``lstat`` - not a symlink, not a directory, not a FIFO, socket or device -
    and the bytes are then read with ``O_NOFOLLOW`` so the check and the read
    cannot end up talking about two different objects.

    ``(None, [])`` means the receipt is simply absent, which is the ordinary
    pre-authorization state and not a defect.
    """
    import stat as _stat

    root = repository_root(repo_root)
    contract = contract if contract is not None else load_trusted_contract(root)
    rel = contract["authorization_receipt"]["tracked_path"]
    path = root / rel

    try:
        info = os.lstat(str(path))
    except FileNotFoundError:
        return None, []
    except OSError as exc:
        return None, [("RECEIPT_PATH_INVALID",
                       f"{rel} could not be inspected: {exc}")]

    if _stat.S_ISLNK(info.st_mode):
        try:
            target = os.readlink(str(path))
        except OSError:
            target = "<unreadable>"
        return None, [(
            "RECEIPT_PATH_INVALID",
            f"{rel} is a SYMLINK to {target!r}. A receipt is a regular file "
            f"tracked in this repository; a link at the contracted path names "
            f"a document this repository does not contain, and whatever that "
            f"document says it is not evidence about this repository")]
    if not _stat.S_ISREG(info.st_mode):
        return None, [(
            "RECEIPT_PATH_INVALID",
            f"{rel} is not a regular file (mode {info.st_mode:#o}); a "
            f"directory, FIFO, socket or device at the contracted path is not "
            f"a receipt")]

    try:
        resolved = Path(os.path.realpath(str(path)))
        root_real = Path(os.path.realpath(str(root)))
        inside = root_real in resolved.parents
    except OSError as exc:
        return None, [("RECEIPT_PATH_INVALID",
                       f"{rel} could not be resolved: {exc}")]
    if not inside:
        return None, [(
            "RECEIPT_PATH_INVALID",
            f"{rel} resolves to {resolved}, which is outside the repository "
            f"{root_real}")]
    return path, []


#: The Windows extended-length path prefix that
#: ``GetFinalPathNameByHandleW`` puts in front of its answer.
WINDOWS_LONG_PREFIX = chr(92) * 2 + "?" + chr(92)


class ReceiptOpenRefused(Exception):
    """The receipt could not be opened in a way that is safe to trust."""

    def __init__(self, why):
        super().__init__(why)
        self.why = why


def _windows_component_handle(kernel32, wintypes, ctypes, path, *, directory):
    """Open one component AS ITSELF and refuse any reparse point.

    ``FILE_FLAG_OPEN_REPARSE_POINT`` is the whole point: without it a junction
    opens as its target and the check has already been defeated. Windows has no
    ``openat``, so components are opened by accumulated path rather than
    relative to a directory descriptor - but each one is inspected before the
    next is opened, which is what makes this the equivalent of the POSIX walk.
    """
    GENERIC_READ = 0x80000000
    SHARE_ALL = 0x1 | 0x2 | 0x4
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    FILE_TYPE_DISK = 0x0001
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    kernel32.CreateFileW.restype = wintypes.HANDLE
    handle = kernel32.CreateFileW(
        ctypes.c_wchar_p(str(path)), wintypes.DWORD(GENERIC_READ),
        wintypes.DWORD(SHARE_ALL), None, wintypes.DWORD(OPEN_EXISTING),
        wintypes.DWORD(FILE_FLAG_BACKUP_SEMANTICS
                       | FILE_FLAG_OPEN_REPARSE_POINT), None)
    if handle in (INVALID_HANDLE_VALUE, None, 0):
        raise ReceiptOpenRefused(
            f"{path} could not be opened safely (WinError "
            f"{ctypes.get_last_error()})")

    class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
        _fields_ = [("dwFileAttributes", wintypes.DWORD),
                    ("ftCreationTime", wintypes.FILETIME),
                    ("ftLastAccessTime", wintypes.FILETIME),
                    ("ftLastWriteTime", wintypes.FILETIME),
                    ("dwVolumeSerialNumber", wintypes.DWORD),
                    ("nFileSizeHigh", wintypes.DWORD),
                    ("nFileSizeLow", wintypes.DWORD),
                    ("nNumberOfLinks", wintypes.DWORD),
                    ("nFileIndexHigh", wintypes.DWORD),
                    ("nFileIndexLow", wintypes.DWORD)]

    info = BY_HANDLE_FILE_INFORMATION()
    ok = kernel32.GetFileInformationByHandle(wintypes.HANDLE(handle),
                                             ctypes.byref(info))

    def _refuse(why):
        kernel32.CloseHandle(wintypes.HANDLE(handle))
        raise ReceiptOpenRefused(why)

    if not ok:
        _refuse(f"{path}: the opened handle could not be inspected "
                f"(WinError {ctypes.get_last_error()})")
    if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
        _refuse(f"the path component {path} is a SYMLINK, junction or other "
                f"reparse point; every component of the receipt path must be "
                f"a real directory or file inside this repository")
    is_dir = bool(info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
    if directory and not is_dir:
        _refuse(f"the path component {path} is not a directory")
    if not directory:
        if is_dir:
            _refuse(f"{path} is not a regular file (it is a directory)")
        if kernel32.GetFileType(wintypes.HANDLE(handle)) != FILE_TYPE_DISK:
            _refuse(f"{path} is not a regular file (it is a pipe, console or "
                    f"character device)")
    return handle


def _windows_final_path(kernel32, wintypes, ctypes, handle, what):
    """The fully resolved path of an OPEN handle."""
    size = 260
    while True:
        buf = ctypes.create_unicode_buffer(size)
        need = kernel32.GetFinalPathNameByHandleW(
            wintypes.HANDLE(handle), buf, wintypes.DWORD(size),
            wintypes.DWORD(0))
        if need == 0:
            raise ReceiptOpenRefused(
                f"the final path of {what} could not be resolved (WinError "
                f"{ctypes.get_last_error()})")
        if need < size:
            break
        size = need + 1
    final = buf.value
    return final[4:] if final.startswith(WINDOWS_LONG_PREFIX) else final


def _windows_safe_open(root, rel):
    """Walk EVERY component from the repository root, refusing reparse points.

    ``O_NOFOLLOW`` DOES NOT EXIST on Windows. The first version of this module
    asked for it through a ``getattr`` defaulting to zero, which contributes
    nothing at all to the flag word, so the "no-follow" read followed links
    exactly like an ordinary ``open()``. The version after that opened only the
    FINAL component as itself - which says nothing whatever about ``docs``.

    Now the ROOT IS OPENED FIRST and held open for the whole operation, and
    each component below it is opened and inspected in turn before the next is
    opened. A junction anywhere along the path is refused at the component that
    carries it, exactly as the POSIX walk refuses it, and the containment check
    still compares two paths that both came from open handles.

    Returns ``(fd, final_path, root_final_path)``.
    """
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes
    except ImportError as exc:                              # pragma: no cover
        raise ReceiptOpenRefused(
            f"the Windows safe-open primitive is unavailable ({exc}); this "
            f"module will not fall back to a following open")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    parts = [p for p in Path(rel).parts if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise ReceiptOpenRefused(
            f"the contracted receipt path {rel!r} is not a plain path inside "
            f"the repository")

    # The ROOT HANDLE is opened before anything else and stays open until the
    # receipt has been opened.
    root_handle = _windows_component_handle(kernel32, wintypes, ctypes,
                                            Path(root), directory=True)
    open_handles = [root_handle]
    try:
        root_final = _windows_final_path(kernel32, wintypes, ctypes,
                                         root_handle, "the repository root")
        walked = Path(root)
        for name in parts[:-1]:
            walked = walked / name
            open_handles.append(_windows_component_handle(
                kernel32, wintypes, ctypes, walked, directory=True))
        target = walked / parts[-1]
        handle = _windows_component_handle(kernel32, wintypes, ctypes, target,
                                           directory=False)
        try:
            final = _windows_final_path(kernel32, wintypes, ctypes, handle,
                                        str(target))
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
        except BaseException:
            kernel32.CloseHandle(wintypes.HANDLE(handle))
            raise
    finally:
        for extra in open_handles:
            kernel32.CloseHandle(wintypes.HANDLE(extra))
    return fd, final, root_final


def _posix_safe_open(root, rel):
    """Walk EVERY component from the repository root with ``openat``.

    Opening the final path with ``O_NOFOLLOW`` protects the final component and
    nothing else: ``docs`` can be a symlink to another tree and the receipt
    inside it is reached without a single link being followed *at the last
    step*. Resolving the result with ``realpath`` afterwards is not a fix
    either - it asks the filesystem a second, separate question about a NAME,
    and the answer can differ from what the descriptor actually refers to.

    So no name is resolved. The repository root is opened once, and each
    component is opened relative to the previous descriptor with
    ``O_DIRECTORY | O_NOFOLLOW``: a link anywhere along the chain is refused
    where it sits, by the kernel, rather than detected afterwards. The final
    component is opened from that verified chain and must be a regular file.
    Containment is then structural - the descriptor was reached from the root
    and never left it - and needs no path comparison at all.
    """
    import stat as _stat
    for needed in ("O_NOFOLLOW", "O_DIRECTORY"):
        if not hasattr(os, needed):                         # pragma: no cover
            raise ReceiptOpenRefused(
                f"{needed} is unavailable on this platform; this module will "
                f"not fall back to a resolving open")

    parts = [p for p in Path(rel).parts if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise ReceiptOpenRefused(
            f"the contracted receipt path {rel!r} is not a plain path inside "
            f"the repository")

    try:
        root_fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise ReceiptOpenRefused(
            f"the repository root {root} could not be opened: {exc}")
    #: Every directory descriptor opened during the walk, ROOT INCLUDED, so the
    #: cleanup below closes all of them exactly once.
    chain = [root_fd]
    try:
        for name in parts[:-1]:
            try:
                chain.append(os.open(
                    name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=chain[-1]))
            except OSError as exc:
                raise ReceiptOpenRefused(
                    f"the path component {name!r} of {rel} is a symlink or is "
                    f"not a directory ({exc}); every component of the receipt "
                    f"path must be a real directory inside this repository")
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW,
                         dir_fd=chain[-1])
        except OSError as exc:
            raise ReceiptOpenRefused(
                f"{rel} could not be opened safely: {exc}")
        try:
            info = os.fstat(fd)
            if not _stat.S_ISREG(info.st_mode):
                raise ReceiptOpenRefused(
                    f"{rel} is not a regular file (mode {info.st_mode:#o}); a "
                    f"directory, FIFO, socket or device at the contracted "
                    f"path is not a receipt")
        except ReceiptOpenRefused:
            os.close(fd)
            raise
        except OSError as exc:
            os.close(fd)
            raise ReceiptOpenRefused(f"{rel} could not be validated: {exc}")
    finally:
        for extra in chain:
            try:
                os.close(extra)
            except OSError:                                 # pragma: no cover
                pass
    #: Containment is structural, so there is no path to report and nothing
    #: for the caller to re-resolve.
    return fd, None


def safe_read_within(anchor, path):
    """ONE fail-closed operation: open safely, validate the HANDLE, read it.

    Inspecting a pathname and then opening it is two operations with a window
    between them, and the whole class of attack on these files lives in that
    window: ``lstat`` says regular file, the path is swapped for a link, the
    read follows it. Here there is nothing to swap, and - just as importantly -
    NO PATHNAME IS RESOLVED AFTER THE OPEN. A ``realpath`` performed once the
    descriptor is in hand is a second, independent question about a name, and
    its answer is not required to describe the object the descriptor refers to.

    * On POSIX containment is STRUCTURAL: the walk starts at ``anchor`` and
      opens each component with ``O_DIRECTORY | O_NOFOLLOW``, so the descriptor
      cannot have left the anchor and there is nothing to compare.
    * On Windows both sides of the comparison come from OPENED HANDLES -
      ``GetFinalPathNameByHandleW`` on the anchor and on the leaf - and neither
      is passed back through ``os.path.realpath``.

    ``anchor`` is the containment boundary: the REPOSITORY ROOT for a tracked
    file, and the VOLUME ROOT for an external evidence file, which lives outside
    any repository but whose every component is still walked and refused if it
    carries a link, a junction or a non-directory.

    Raises ReceiptOpenRefused. It never returns bytes whose provenance it has
    not established, and it never falls back to a weaker open.
    """
    path = Path(path)
    root = Path(anchor)
    try:
        rel = path.relative_to(root)
    except ValueError:
        raise ReceiptOpenRefused(
            f"{path} is not inside {root}")
    if os.name == "nt":
        fd, final, root_final = _windows_safe_open(root, rel)
    else:
        fd, final = _posix_safe_open(root, rel)
        root_final = None
    try:
        if final is not None:
            inside = (final.casefold().startswith(
                root_final.casefold().rstrip("\\/") + os.sep)
                or final.casefold().startswith(
                    root_final.casefold().rstrip("\\/") + "/"))
            if not inside:
                raise ReceiptOpenRefused(
                    f"the opened file is at {final}, which is outside "
                    f"{root_final}. Both paths come from opened handles, so a "
                    f"junction on a parent directory is caught as surely as a "
                    f"link on the file itself - and neither side was "
                    f"re-resolved from a name afterwards")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            return handle.read()
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:                                 # pragma: no cover
                pass


def safe_read_receipt(path, repo_root):
    """The repository-contained case: anchor is the repository root."""
    return safe_read_within(repo_root, path)


def volume_anchor(path):
    """The VOLUME ROOT of an absolute path: ``C:\\`` or ``/``.

    The external evidence file is not inside any repository, so there is no
    tree to be contained by - but "outside the repository" must not become
    "unchecked". Anchoring at the volume root means EVERY component of the
    supplied path, from the drive letter down, is opened and inspected by the
    same walk that protects the tracked receipt: a junction on any parent, a
    symlink on the leaf, or a device where a file was expected is refused
    where it sits.
    """
    path = Path(path)
    if not path.is_absolute():
        raise ReceiptOpenRefused(
            f"{path} is not an absolute path; the original approval evidence "
            f"is named absolutely so that every component of the name can be "
            f"walked and checked")
    return Path(path.anchor)


def safe_read_external_evidence(path):
    """Read the ORIGINAL approval evidence, component-safe and no-follow.

    Same primitive as the receipt, anchored at the volume root instead of the
    repository, because this file deliberately lives OUTSIDE the tree. Fails
    closed: any refusal is a refusal, never a fallback to ``open()``.
    """
    return safe_read_within(volume_anchor(path), path)


def read_receipt_bytes(path, repo_root=None):
    """The single safe-open operation, under its historical name.

    There is deliberately no variant of this that reads without a repository to
    be contained by: ``repo_root`` defaults to this module's own repository
    rather than to "no containment check".
    """
    return safe_read_within(repository_root(repo_root), path)


# ---------------------------------------------------------------------------
# Receipt validation - the whole point of this module
# ---------------------------------------------------------------------------
#: The receipt field that says HOW the approval was obtained, and its two
#: values. Absent means the GitHub route: a receipt predating the second route
#: cannot retroactively have said which one it used.
SOURCE_FIELD = "approval_source"
GITHUB_SOURCE = "github_pr_comment"
EXTERNAL_SOURCE = "external_evidence"


def _strict_json(text):
    """``json.loads`` that REFUSES duplicate keys.

    ``{"custodian": "someone else", "custodian": "Fawaz Bouhamad"}`` parses
    silently in stock json and keeps the LAST value, so a record could carry a
    reviewed-looking field beside the one that actually takes effect.
    """
    def _no_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError(f"duplicate key {key!r}")
            seen[key] = value
        return seen
    return json.loads(text, object_pairs_hook=_no_duplicates)


#: The only ambient variables a git subprocess here inherits. An ALLOWLIST,
#: not a denylist, for the same reason the finalizer uses one: a denylist has
#: to have heard of the variable that redirects the answer.
_GIT_ENV_ALLOWLIST = ("PATH", "SYSTEMROOT", "SystemRoot", "COMSPEC", "ComSpec",
                      "PATHEXT", "WINDIR", "windir", "TEMP", "TMP", "TMPDIR",
                      "LANG", "LC_ALL")


def _git_env(root):
    """The environment every git subprocess in this module runs under.

    ``GIT_DIR`` and ``GIT_INDEX_FILE`` alone point a command at a DIFFERENT
    repository from the one named with ``-C``, so "what is committed at this
    path" could be answered by somebody else's tree - which, for a function
    whose entire job is to prove that an approval record is committed, is the
    whole game. Global and system configuration are neutralised rather than
    inherited, so a hostile ``~/.gitconfig`` cannot introduce an alias or a
    filter, and upward discovery is stopped above the repository.
    """
    env = {key: os.environ[key] for key in _GIT_ENV_ALLOWLIST
           if key in os.environ}
    env.update({
        # No system config, and no global config: point both at a path that
        # cannot hold settings, so HOME is irrelevant and need not be trusted.
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        # Reading the tree must not write the index or the reflog.
        "GIT_OPTIONAL_LOCKS": "0",
        # If `root` turns out not to be a repository, refuse rather than
        # walking up and answering about whatever repository encloses it.
        "GIT_CEILING_DIRECTORIES": str(Path(root).resolve().parent),
    })
    return env


def _git_blob(root, rel):
    """``(blob_id, blob_bytes)`` for ``rel`` at HEAD, or ``(None, None)``."""
    import subprocess
    env = _git_env(root)
    try:
        ident = subprocess.run(
            ["git", "-C", str(root), "rev-parse", f"HEAD:{rel}"],
            capture_output=True, env=env)
        blob = subprocess.run(
            ["git", "-C", str(root), "cat-file", "blob", f"HEAD:{rel}"],
            capture_output=True, env=env)
    except OSError:                                         # pragma: no cover
        return None, None
    if ident.returncode != 0 or blob.returncode != 0:
        return None, None
    blob_id = ident.stdout.decode("ascii", "replace").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", blob_id):
        return None, None
    return blob_id, blob.stdout


#: What each declared source type must actually LOOK LIKE on disk.
#:
#: The record says how the approval arrived; the evidence file is the thing
#: that arrived. Nothing required the two to agree, so a record could declare
#: ``approval_email`` - which the custodian attestation and the operator guide
#: both describe as "the complete message with its full headers" - while the
#: preserved file was a ``.docx`` or a screenshot ``.png``. Those are not the
#: original message: they are a transcription of it, with the headers that
#: carry the provenance discarded.
#:
#: A CONSISTENCY check and nothing more. It does not authenticate the mail, and
#: no format check could - see the custodian trust model in the operator guide.
#: It refuses the case where the record's own claim about what it preserved is
#: contradicted by the file it preserved.
EVIDENCE_FORMATS = {
    "approval_email": (
        frozenset("eml msg mbox mht mhtml emlx".split()),
        "the complete original message as received - .eml, .msg or .mbox - "
        "so that its headers are preserved. A PDF, a screenshot or a word "
        "processor document is a transcription of a message, not the message"),
    "signed_approval_form": (
        frozenset("pdf png jpg jpeg tif tiff".split()),
        "the signed form as scanned or exported - .pdf, or a .png/.jpg/.tiff "
        "scan - so that the signature itself is preserved"),
}


def evidence_format_issues(source_type, filename, *, code):
    """Refuse an evidence file whose format contradicts its declared source."""
    spec = EVIDENCE_FORMATS.get(str(source_type))
    if spec is None:
        return []
    allowed, expectation = spec
    ext = Path(str(filename)).suffix.lower().lstrip(".")
    if ext in allowed:
        return []
    return [(code,
             f"the record declares source_type {source_type!r} but the "
             f"preserved evidence is {filename!r} (.{ext or 'no extension'}). "
             f"That source type means {expectation}")]


def approval_record_receipt_issues(receipt, contract, root):
    """Prove the tracked approval record the receipt RESTS ON, at HEAD.

    An external receipt is a claim about a second file: "the approval this
    licence rests on is recorded at <path>, whose bytes hash to <sha256> and
    whose committed blob is <sha1>". Until r3m nothing checked that the file
    existed - so a receipt naming a record that had never been written, or one
    naming a record whose bytes had since been edited, still read as ACTIVE,
    and the guards happily asserted CC BY over a coauthor's artwork on the
    strength of a self-consistent JSON file somebody could type.

    So the record is re-read here, from the tree, EVERY time a receipt is
    validated - by the builder, by the guards, and by the finalizer:

    * read through the component-safe, no-follow walk, so a link at the path or
      a junction on any parent directory is a refusal and not a redirection;
    * TRACKED at HEAD, because a record that exists only in a working copy has
      no history, no review and no author;
    * its bytes on disk EQUAL to the blob at HEAD, so the reviewed record and
      the read record are the same object;
    * its SHA-256 and its git blob identity RECOMPUTED and equal to the two the
      receipt commits to; and
    * its approved paragraph, its seven-artwork scope, its evidence metadata
      and its custodian attestation equal to the receipt's.

    None of this authenticates the human approval - see the custodian trust
    model in the operator guide. It establishes that the receipt and the
    committed record are one consistent, unaltered pair.
    """
    issues = []
    ext = (contract.get("approval_sources") or {}).get(EXTERNAL_SOURCE) or {}
    rel = ext.get("tracked_record_path")
    if not rel:
        return [("RECEIPT_APPROVAL_RECORD_UNVERIFIABLE",
                 "the contract enables external evidence but declares no "
                 "tracked_record_path, so the record a receipt rests on cannot "
                 "be located")]
    root = Path(root)
    path = root / rel

    if not os.path.lexists(str(path)):
        return [("RECEIPT_APPROVAL_RECORD_ABSENT",
                 f"the receipt rests on {rel}, which does not exist. A receipt "
                 f"naming an approval record that is not in the tree is not "
                 f"evidence of anything")]
    try:
        disk = safe_read_within(root, path)
    except ReceiptOpenRefused as exc:
        return [("RECEIPT_APPROVAL_RECORD_UNREADABLE",
                 f"{rel} could not be read safely: {exc.why}")]

    blob_id, blob = _git_blob(root, rel)
    if blob_id is None:
        return [("RECEIPT_APPROVAL_RECORD_UNTRACKED",
                 f"{rel} is not tracked at HEAD; an approval record that was "
                 f"never committed has no history, no review and no author")]
    if disk != blob:
        return [("RECEIPT_APPROVAL_RECORD_MODIFIED",
                 f"{rel} on disk ({sha256_hex(disk.decode('utf-8', 'replace'))}"
                 f", {len(disk)} B) differs from its committed blob {blob_id} "
                 f"({len(blob)} B); the record being read is not the record "
                 f"that was reviewed and committed")]

    got_sha = hashlib.sha256(disk).hexdigest()
    if receipt.get("approval_record_sha256") != got_sha:
        issues.append((
            "RECEIPT_APPROVAL_RECORD_MISMATCH",
            f"the receipt commits to approval_record_sha256 "
            f"{receipt.get('approval_record_sha256')!r}; {rel} hashes "
            f"{got_sha}"))
    if receipt.get("approval_record_blob_sha1") != blob_id:
        issues.append((
            "RECEIPT_APPROVAL_RECORD_MISMATCH",
            f"the receipt commits to approval_record_blob_sha1 "
            f"{receipt.get('approval_record_blob_sha1')!r}; {rel} is committed "
            f"as blob {blob_id}"))

    try:
        record = _strict_json(disk.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        issues.append(("RECEIPT_APPROVAL_RECORD_MALFORMED",
                       f"{rel} is not a strict JSON object: {exc}"))
        return sorted(set(issues))
    if not isinstance(record, dict):
        return sorted(set(issues)) + [
            ("RECEIPT_APPROVAL_RECORD_MALFORMED", f"{rel} is not an object")]

    # --- the RECORD must be well-formed IN ITSELF ---------------------------
    # Not merely consistent with the receipt. A record and a receipt that agree
    # with each other can still both be wrong: the durable path validated only
    # that they matched, so a committed record missing its custodian
    # attestation entirely, or declaring an invented source_type, or carrying
    # no schema_version, passed every check as long as the receipt written
    # beside it repeated the same defect. `find_external_approval` applies
    # these at finalization; they belong here too, because the builder and the
    # guards read the receipt for years afterwards and never call it.
    missing = [f for f in (ext.get("required_fields") or [])
               if f not in record]
    if missing:
        issues.append(("RECEIPT_APPROVAL_RECORD_MALFORMED",
                       f"{rel} is missing required field(s) {missing}; a "
                       f"receipt may not rest on an incomplete record"))
    want_schema = ext.get("schema_version")
    if want_schema is not None and record.get("schema_version") != want_schema:
        issues.append((
            "RECEIPT_APPROVAL_RECORD_SCHEMA_VERSION",
            f"{rel} declares schema_version "
            f"{record.get('schema_version')!r}, the contract admits "
            f"{want_schema!r}"))
    allowed_types = ext.get("allowed_source_types") or []
    if allowed_types and record.get("source_type") not in allowed_types:
        issues.append((
            "RECEIPT_APPROVAL_RECORD_SOURCE_TYPE",
            f"{rel} declares source_type {record.get('source_type')!r}, which "
            f"is not one of {allowed_types}"))
    else:
        # The record's claim about HOW the approval arrived, against the name
        # of the file it says it preserved. Checked on the RECORD's filename,
        # which is the one that outlives the finalization.
        rec_evidence = record.get("evidence")
        rec_evidence = rec_evidence if isinstance(rec_evidence, dict) else {}
        issues.extend(evidence_format_issues(
            record.get("source_type"),
            rec_evidence.get("filename") or receipt.get("evidence_filename"),
            code="RECEIPT_APPROVAL_RECORD_EVIDENCE_FORMAT"))

    # --- the receipt must say what the record says --------------------------
    if str(record.get("source_type")) != str(receipt.get("source_type")):
        issues.append((
            "RECEIPT_DISAGREES_WITH_APPROVAL_RECORD",
            f"receipt source_type={receipt.get('source_type')!r} but {rel} "
            f"records {record.get('source_type')!r}"))
    if str(record.get("approval_date")) != str(receipt.get("approval_date")):
        issues.append((
            "RECEIPT_DISAGREES_WITH_APPROVAL_RECORD",
            f"receipt approval_date={receipt.get('approval_date')!r} but {rel} "
            f"records {record.get('approval_date')!r}"))
    if normalize_prose(str(record.get("approved_text") or "")) != \
            normalize_prose(str(receipt.get("approved_text") or "")):
        issues.append((
            "RECEIPT_DISAGREES_WITH_APPROVAL_RECORD",
            f"the paragraph the receipt carries is not the paragraph {rel} "
            f"records as approved"))

    want_paths = sorted(contract["ccby_artwork_paths"])
    rec_art = record.get("licensed_artwork")
    if not isinstance(rec_art, dict) or sorted(rec_art) != want_paths:
        got = sorted(rec_art) if isinstance(rec_art, dict) else rec_art
        issues.append((
            "RECEIPT_DISAGREES_WITH_APPROVAL_RECORD",
            f"{rel} approves {got!r}; the contracted scope is exactly "
            f"{want_paths}"))
    else:
        rcp_art = receipt.get("licensed_artwork")
        rcp_art = rcp_art if isinstance(rcp_art, dict) else {}
        for art_rel in want_paths:
            if rec_art[art_rel] != rcp_art.get(art_rel):
                issues.append((
                    "RECEIPT_DISAGREES_WITH_APPROVAL_RECORD",
                    f"{art_rel}: {rel} approves {rec_art[art_rel]}, the "
                    f"receipt licenses {rcp_art.get(art_rel)!r}. The approval "
                    f"covers the bytes that were shown"))

    evidence = record.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    for rec_field, rcp_field in (("filename", "evidence_filename"),
                                 ("bytes", "evidence_bytes"),
                                 ("sha256", "evidence_sha256")):
        if evidence.get(rec_field) != receipt.get(rcp_field):
            issues.append((
                "RECEIPT_DISAGREES_WITH_APPROVAL_RECORD",
                f"receipt {rcp_field}={receipt.get(rcp_field)!r} but {rel} "
                f"records evidence.{rec_field}={evidence.get(rec_field)!r}"))

    attestation = record.get("custodian_attestation")
    attestation = attestation if isinstance(attestation, dict) else {}
    for rec_field, rcp_field in (("custodian", "custodian"),
                                 ("attested_at", "attested_at")):
        if attestation.get(rec_field) != receipt.get(rcp_field):
            issues.append((
                "RECEIPT_DISAGREES_WITH_APPROVAL_RECORD",
                f"receipt {rcp_field}={receipt.get(rcp_field)!r} but {rel} "
                f"records custodian_attestation.{rec_field}="
                f"{attestation.get(rec_field)!r}"))
    if normalize_prose(str(attestation.get("statement") or "")) != \
            normalize_prose(str(ext.get("attestation_statement") or "")):
        issues.append((
            "RECEIPT_APPROVAL_RECORD_ATTESTATION",
            f"the custodian attestation in {rel} is not EXACTLY the contracted "
            f"statement"))
    return sorted(set(issues))


def _external_receipt_issues(receipt, contract, root, record=None):
    """Every defect in a receipt written from a preserved email or a form.

    The GitHub receipt's authority is a live comment that can be re-fetched.
    This one's authority is a TRACKED APPROVAL RECORD plus a private original,
    so what it must prove is different: that it names the record it rests on by
    both digests, that it names the evidence by digest and length, that the
    paragraph it carries is the contracted one, and that the seven artwork
    identities still hold in the tree. Nothing here can be satisfied by a
    boolean, and nothing here can be written by hand without the record and the
    evidence agreeing with it.
    """
    issues = []
    spec = contract["authorization_receipt"]
    repo = contract["repository"]
    sources = (contract.get("approval_sources") or {})
    ext = sources.get(EXTERNAL_SOURCE) or {}

    if EXTERNAL_SOURCE not in (sources.get("enabled") or []):
        issues.append(("RECEIPT_APPROVAL_SOURCE",
                       f"the receipt claims {EXTERNAL_SOURCE!r} but that "
                       f"source is not enabled in approval_sources.enabled"))
    required = spec.get("required_fields_external_evidence") or []
    for field in required:
        if field not in receipt:
            issues.append(("RECEIPT_FIELD_MISSING",
                           f"required field {field!r} is absent"))
    if issues:
        return sorted(set(issues))

    if receipt["schema_version"] != spec["schema_version"]:
        issues.append(("RECEIPT_SCHEMA_VERSION",
                       f"schema_version {receipt['schema_version']!r} != "
                       f"{spec['schema_version']!r}"))
    if receipt["repository"] != f"{repo['owner']}/{repo['name']}":
        issues.append(("RECEIPT_REPOSITORY",
                       f"repository {receipt['repository']!r} is not the "
                       f"contracted one"))
    if receipt["source_type"] not in (ext.get("allowed_source_types") or []):
        issues.append(("RECEIPT_SOURCE_TYPE",
                       f"source_type {receipt['source_type']!r} is not one of "
                       f"{ext.get('allowed_source_types')}"))
    if receipt["approval_record_path"] != ext.get("tracked_record_path"):
        issues.append(("RECEIPT_APPROVAL_RECORD_PATH",
                       f"approval_record_path "
                       f"{receipt['approval_record_path']!r} is not the "
                       f"contracted {ext.get('tracked_record_path')!r}"))
    if receipt["custodian"] != ext.get("custodian"):
        issues.append(("RECEIPT_CUSTODIAN",
                       f"custodian {receipt['custodian']!r} is not the "
                       f"contracted {ext.get('custodian')!r}"))

    want_text = normalize_prose(contract["authorization"]["text"])
    if normalize_prose(str(receipt["approved_text"])) != want_text:
        issues.append(("RECEIPT_APPROVED_TEXT",
                       "approved_text is not EXACTLY the contracted approval "
                       "paragraph"))
    if sha256_hex(receipt["approved_text"]) != receipt["approved_text_sha256"]:
        issues.append(("RECEIPT_APPROVED_TEXT_SHA256",
                       "approved_text_sha256 does not hash its own text"))

    for field, pattern, what in (
            ("approval_record_sha256", r"[0-9a-f]{64}", "a 64-hex digest"),
            ("evidence_sha256", r"[0-9a-f]{64}", "a 64-hex digest"),
            ("approval_record_blob_sha1", r"[0-9a-f]{40}", "a 40-hex blob id"),
            ("starting_head", r"[0-9a-f]{40}", "a 40-hex commit")):
        if not re.fullmatch(pattern, str(receipt[field] or "")):
            issues.append((f"RECEIPT_{field.upper()}",
                           f"{field} {receipt[field]!r} is not {what}"))

    size = receipt["evidence_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        issues.append(("RECEIPT_EVIDENCE_BYTES",
                       f"evidence_bytes {size!r} is not a positive integer"))
    if not str(receipt["evidence_filename"] or "").strip():
        issues.append(("RECEIPT_EVIDENCE_FILENAME",
                       "evidence_filename is empty"))

    stamps = {}
    for field in ("approval_date", "attested_at", "activated_at"):
        value = str(receipt.get(field) or "")
        parsed = parse_timestamp(value) if value else None
        if parsed is None:
            issues.append((f"RECEIPT_{field.upper()}",
                           f"{field} {value!r} is not a real ISO-8601 UTC "
                           f"instant"))
            continue
        stamps[field] = parsed
    # The order the evidence chain actually happened in: the coauthor approved,
    # the custodian attested to holding that approval, and only then did a
    # finalization act on it.
    if {"approval_date", "attested_at"} <= set(stamps) and \
            stamps["attested_at"] < stamps["approval_date"]:
        issues.append(("RECEIPT_TIMESTAMP_ORDER",
                       f"attested_at {receipt['attested_at']} precedes the "
                       f"approval it attests to ({receipt['approval_date']})"))
    if {"attested_at", "activated_at"} <= set(stamps) and \
            stamps["activated_at"] < stamps["attested_at"]:
        issues.append(("RECEIPT_TIMESTAMP_ORDER",
                       f"activated_at {receipt['activated_at']} precedes the "
                       f"custodian attestation ({receipt['attested_at']}); the "
                       f"required order is approval_date <= attested_at <= "
                       f"activated_at"))

    if receipt["finalizer_version"] != contract["finalizer_version"]:
        issues.append(("RECEIPT_FINALIZER_VERSION",
                       f"finalizer_version {receipt['finalizer_version']!r} "
                       f"!= {contract['finalizer_version']!r}"))

    artwork = receipt["licensed_artwork"]
    want_paths = sorted(contract["ccby_artwork_paths"])
    if not isinstance(artwork, dict) or sorted(artwork) != want_paths:
        got = sorted(artwork) if isinstance(artwork, dict) else artwork
        issues.append(("RECEIPT_ARTWORK_SCOPE",
                       f"receipt licenses {got!r}; the contracted scope is "
                       f"exactly {want_paths}"))
    else:
        for rel in want_paths:
            path = root / rel
            if not path.is_file():
                issues.append(("RECEIPT_ARTWORK_MISSING",
                               f"{rel} is licensed by the receipt but absent"))
                continue
            got = sha256_file(path)
            if artwork[rel] != got:
                issues.append((
                    "RECEIPT_ARTWORK_MISMATCH",
                    f"{rel}: receipt records {artwork[rel]}, tree has {got}"))

    # --- the TRACKED RECORD this receipt rests on, always -------------------
    # Not conditional on `record`. The builder and the guards run long after
    # any finalization and have no live approval to compare against, and they
    # are exactly the callers a hand-written receipt was aimed at.
    issues.extend(approval_record_receipt_issues(receipt, contract, root))

    # --- the approval this run actually resolved, when we have one ----------
    if record is not None:
        for field in ("source_type", "approval_date", "approved_text",
                      "approved_text_sha256", "approval_record_path",
                      "approval_record_sha256", "approval_record_blob_sha1",
                      "evidence_filename", "evidence_sha256", "evidence_bytes",
                      "custodian", "attested_at"):
            if receipt.get(field) != record.get(field):
                issues.append((
                    "RECEIPT_DISAGREES_WITH_APPROVAL_RECORD",
                    f"receipt {field}={receipt.get(field)!r} but the approval "
                    f"resolved from the tracked record and its original "
                    f"evidence says {record.get(field)!r}"))
    return sorted(set(issues))


def validate_receipt(receipt, contract, repo_root=None, *, record=None):
    """Aggregate EVERY defect in a receipt. Returns sorted (code, why) tuples.

    ``record`` is the live authorization when one is available (during a real
    finalization). Without it the receipt is still validated against the
    contract and the tree - which is what the builder and the guards do, long
    after the API call that produced it.
    """
    root = repository_root(repo_root)
    issues = []
    spec = contract["authorization_receipt"]
    repo = contract["repository"]

    if not isinstance(receipt, dict):
        return [("RECEIPT_MALFORMED", "receipt is not a JSON object")]

    # WHICH SOURCE licensed the artwork decides which fields a receipt must
    # carry. A receipt written from a preserved email carries no comment id and
    # no permalink, because there is no comment; requiring the GitHub field set
    # of it would either refuse a valid approval or invite fabricated fields.
    # A receipt with no discriminator at all is read as the GitHub route, which
    # is what every receipt written before the second route existed would be.
    source = receipt.get(SOURCE_FIELD, GITHUB_SOURCE)
    if source not in (GITHUB_SOURCE, EXTERNAL_SOURCE):
        return [("RECEIPT_APPROVAL_SOURCE",
                 f"approval_source {source!r} is not one of "
                 f"{(GITHUB_SOURCE, EXTERNAL_SOURCE)}")]
    if source == EXTERNAL_SOURCE:
        return sorted(set(_external_receipt_issues(receipt, contract, root,
                                                   record)))

    for field in spec["required_fields"]:
        if field not in receipt:
            issues.append(("RECEIPT_FIELD_MISSING",
                           f"required field {field!r} is absent"))
    if issues:
        return sorted(set(issues))

    want_login = contract["authorization"]["required_login"]
    want_text = normalize_prose(contract["authorization"]["text"])

    if receipt["schema_version"] != spec["schema_version"]:
        issues.append(("RECEIPT_SCHEMA_VERSION",
                       f"schema_version {receipt['schema_version']!r} != "
                       f"{spec['schema_version']!r}"))
    if receipt["repository"] != f"{repo['owner']}/{repo['name']}":
        issues.append(("RECEIPT_REPOSITORY",
                       f"repository {receipt['repository']!r} is not the "
                       f"contracted one"))
    # A positive, non-boolean INTEGER equal to the contracted number. In JSON,
    # `true` and `1.0` both compare equal to 1, so a value check alone would
    # accept either as the pull request this receipt belongs to.
    pull_request = receipt["pull_request"]
    if (isinstance(pull_request, bool)
            or not isinstance(pull_request, int)
            or pull_request <= 0
            or pull_request != repo["pull_request"]):
        issues.append(("RECEIPT_PULL_REQUEST",
                       f"pull_request {pull_request!r} "
                       f"({type(pull_request).__name__}) is not the positive "
                       f"integer {repo['pull_request']!r}"))
    if str(receipt["login"]).lower() != want_login.lower():
        issues.append(("RECEIPT_LOGIN",
                       f"login {receipt['login']!r} is not the contracted "
                       f"{want_login!r}"))
    if normalize_prose(receipt["body"]) != want_text:
        issues.append(("RECEIPT_BODY",
                       "body is not EXACTLY the contracted authorization text"))
    if sha256_hex(receipt["body"]) != receipt["body_sha256"]:
        issues.append(("RECEIPT_BODY_SHA256",
                       "body_sha256 does not hash its own body"))
    # comment_id must be a real positive integer, not "0", not True, not "12x".
    comment_id = receipt["comment_id"]
    if isinstance(comment_id, bool) or not isinstance(comment_id, int) or \
            comment_id <= 0:
        issues.append(("RECEIPT_COMMENT_ID",
                       f"comment_id {comment_id!r} is not a positive integer"))

    stamps = {}
    for field in ("created_at", "updated_at", "activated_at"):
        value = str(receipt.get(field) or "")
        if not value:
            issues.append((f"RECEIPT_{field.upper()}", f"{field} is empty"))
            continue
        parsed = parse_timestamp(value)
        if parsed is None:
            issues.append((f"RECEIPT_{field.upper()}",
                           f"{field} {value!r} is not a real ISO-8601 UTC "
                           f"instant"))
            continue
        stamps[field] = parsed
    if {"created_at", "updated_at"} <= set(stamps) and \
            stamps["created_at"] > stamps["updated_at"]:
        issues.append(("RECEIPT_TIMESTAMP_ORDER",
                       f"created_at {receipt['created_at']} is after "
                       f"updated_at {receipt['updated_at']}"))
    if {"updated_at", "activated_at"} <= set(stamps) and \
            stamps["activated_at"] < stamps["updated_at"]:
        issues.append(("RECEIPT_TIMESTAMP_ORDER",
                       f"activated_at {receipt['activated_at']} precedes "
                       f"updated_at {receipt['updated_at']}; the required "
                       f"order is created_at <= updated_at <= activated_at"))
    if {"created_at", "activated_at"} <= set(stamps) and \
            stamps["activated_at"] < stamps["created_at"]:
        issues.append(("RECEIPT_TIMESTAMP_ORDER",
                       f"activated_at {receipt['activated_at']} precedes the "
                       f"authorization it records ({receipt['created_at']})"))

    # The API issue URL, exactly.
    want_issue = (contract["authorization"].get("expected_issue_url")
                  or f"https://api.github.com/repos/{repo['owner']}"
                     f"/{repo['name']}/issues/{repo['pull_request']}")
    if receipt.get("issue_url") != want_issue:
        issues.append(("RECEIPT_ISSUE_URL",
                       f"issue_url {receipt.get('issue_url')!r} is not "
                       f"exactly {want_issue!r}"))
    if receipt["finalizer_version"] != contract["finalizer_version"]:
        issues.append(("RECEIPT_FINALIZER_VERSION",
                       f"finalizer_version {receipt['finalizer_version']!r} "
                       f"!= {contract['finalizer_version']!r}"))
    if not re.fullmatch(r"[0-9a-f]{40}", str(receipt["starting_head"] or "")):
        issues.append(("RECEIPT_STARTING_HEAD",
                       f"starting_head {receipt['starting_head']!r} is not a "
                       f"40-hex commit"))
    issues.extend(_permalink_issues(receipt.get("permalink"), repo,
                                    receipt.get("comment_id")))

    # --- scope: EXACTLY the seven contracted artwork paths, hashes intact ---
    artwork = receipt["licensed_artwork"]
    want_paths = sorted(contract["ccby_artwork_paths"])
    if not isinstance(artwork, dict) or sorted(artwork) != want_paths:
        got = sorted(artwork) if isinstance(artwork, dict) else artwork
        issues.append((
            "RECEIPT_ARTWORK_SCOPE",
            f"receipt licenses {got!r}; the contracted scope is exactly "
            f"{want_paths}"))
    else:
        for rel in want_paths:
            path = root / rel
            if not path.is_file():
                issues.append(("RECEIPT_ARTWORK_MISSING",
                               f"{rel} is licensed by the receipt but absent"))
                continue
            got = sha256_file(path)
            if artwork[rel] != got:
                issues.append((
                    "RECEIPT_ARTWORK_MISMATCH",
                    f"{rel}: receipt records {artwork[rel]}, tree has {got}"))

    # --- the live authorization, when we have one -------------------------
    if record is not None:
        for field in ("comment_id", "login", "body", "body_sha256",
                      "created_at", "updated_at", "permalink", "issue_url"):
            if receipt.get(field) != record.get(field):
                issues.append((
                    "RECEIPT_DISAGREES_WITH_LIVE_COMMENT",
                    f"receipt {field}={receipt.get(field)!r} but the live "
                    f"comment says {record.get(field)!r}"))
    return sorted(set(issues))


def _permalink_issues(url, repo, comment_id=None):
    """The permalink must be an HTTPS github.com comment on the right PR.

    The fragment must name the SAME comment the receipt records. A permalink
    pointing at a different comment on the right pull request would otherwise
    pass, and the durable evidence would point somewhere other than the
    authorization it claims to record.
    """
    url = str(url or "")
    parsed = urlparse(url)
    want_path = f"/{repo['owner']}/{repo['name']}/pull/{repo['pull_request']}"
    if parsed.scheme != "https":
        return [("RECEIPT_PERMALINK", f"permalink {url!r} is not HTTPS")]
    if parsed.netloc.lower() != "github.com":
        return [("RECEIPT_PERMALINK",
                 f"permalink host {parsed.netloc!r} is not github.com; a "
                 f"foreign host whose PATH mentions the repository is not the "
                 f"repository")]
    if parsed.path != want_path:
        return [("RECEIPT_PERMALINK",
                 f"permalink path {parsed.path!r} is not {want_path!r}")]
    if comment_id is not None and not isinstance(comment_id, bool) and \
            isinstance(comment_id, int):
        want_fragment = f"issuecomment-{comment_id}"
        if parsed.fragment != want_fragment:
            return [("RECEIPT_PERMALINK",
                     f"permalink fragment {parsed.fragment!r} is not exactly "
                     f"{want_fragment!r}")]
    elif not parsed.fragment.startswith("issuecomment-"):
        return [("RECEIPT_PERMALINK",
                 f"permalink {url!r} is not a top-level issue comment")]
    return []


# ---------------------------------------------------------------------------
# The state
# ---------------------------------------------------------------------------
def artwork_licence_state(repo_root=None, contract=None, *,
                          archive_licence_text=None, record=None):
    """Classify the artwork licence state. Returns ``(state, issues, detail)``.

    ACTIVE requires a receipt that VALIDATES, not a receipt that merely
    exists. PENDING requires no valid receipt and every licence surface
    withholding the grant. Disagreement between surfaces is INCONSISTENT and
    is reported as such rather than resolved in either direction.
    """
    root = repository_root(repo_root)
    try:
        contract = (contract if contract is not None
                    else load_trusted_contract(root))
    except (OSError, ValueError) as exc:
        return INCONSISTENT, [("CONTRACT_UNREADABLE", str(exc))], {}

    issues = []
    detail = {}
    rel = contract["authorization_receipt"]["tracked_path"]
    detail["_receipt_path"] = rel
    detail["_receipt_valid"] = False

    # The PATH is validated before the CONTENTS. A symlink at the contracted
    # path can point at a perfectly well-formed receipt; reading it first and
    # asking questions later is how a document outside the repository ends up
    # licensing this repository's artwork.
    path, path_issues = resolve_receipt_path(root, contract)
    issues.extend(path_issues)
    detail["_receipt_present"] = bool(path_issues) or path is not None

    receipt_ok = False
    if path is not None:
        # The pre-check above is diagnostics. THIS is the operation the state
        # rests on: one fail-closed safe open that validates the handle it
        # actually got, refuses reparse points and special files, and requires
        # the handle's final resolved path to be inside the repository. Nothing
        # is read through the pathname the pre-check inspected.
        try:
            body = safe_read_receipt(path, root)
        except ReceiptOpenRefused as exc:
            issues.append(("RECEIPT_PATH_INVALID", exc.why))
            body = None
        if body is None:
            receipt = None
        else:
            try:
                receipt = loads_strict(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                issues.append(("RECEIPT_MALFORMED",
                               f"{Path(rel).name}: {exc}"))
                receipt = None
        if receipt is not None:
            problems = validate_receipt(receipt, contract, root, record=record)
            issues.extend(problems)
            receipt_ok = not problems
            detail["_receipt_valid"] = receipt_ok

    for rel in contract["licence_records"]:
        record_path = root / rel
        if not record_path.is_file():
            issues.append(("LICENCE_RECORD_MISSING", f"{rel} is missing"))
            detail[rel] = None
            continue
        detail[rel] = classify_claim(
            record_path.read_text(encoding="utf-8", errors="replace"),
            contract)

    member = contract["archive_topology"]["licence_member"]
    if archive_licence_text is not None:
        detail[f"archive:{member}"] = classify_claim(archive_licence_text,
                                                     contract)

    claims = [v for k, v in detail.items()
              if not k.startswith("_") and v is not None]
    unknown = sorted(k for k, v in detail.items()
                     if not k.startswith("_") and v is None)
    if unknown:
        issues.append(("LICENCE_STATE_UNREADABLE",
                       f"no artwork licence claim found in {unknown}"))

    all_pending = bool(claims) and all(c == PENDING for c in claims)
    all_active = bool(claims) and all(c == ACTIVE for c in claims)

    if all_pending and not unknown:
        if receipt_ok:
            issues.append(("LICENCE_STATE_INCONSISTENT",
                           "a VALID D6 receipt exists but every record still "
                           "withholds the grant"))
            return INCONSISTENT, sorted(set(issues)), detail
        return PENDING, sorted(set(issues)), detail

    if all_active and not unknown:
        if not receipt_ok:
            issues.append((
                "LICENCE_STATE_INCONSISTENT",
                "CC BY is asserted over the artwork but no VALID D6 receipt "
                "records who authorized it; a receipt that merely exists is "
                "not an authorization"))
            return INCONSISTENT, sorted(set(issues)), detail
        return ACTIVE, sorted(set(issues)), detail

    pending = sorted(k for k, v in detail.items() if v == PENDING)
    active = sorted(k for k, v in detail.items() if v == ACTIVE)
    issues.append(("LICENCE_STATE_INCONSISTENT",
                   f"surfaces disagree - pending={pending} active={active} "
                   f"unreadable={unknown}"))
    return INCONSISTENT, sorted(set(issues)), detail


#: An ACTIVE marker must be a complete affirmative scoped clause, not a token.
MIN_ACTIVE_MARKER = 40

#: Words that make a clause a DENIAL, an exclusion or a deferral rather than a
#: grant. "Figures 1 and 4 are NOT licensed under CC BY 4.0" must never be
#: registrable as the marker that means the licence is in force.
NEGATION_RX = re.compile(
    r"\bnot|\bno|\bnever|\bexclud|\bpending|\bwithh|\bunless|\buntil"
    r"|\bnot yet in force"
    r"|\brequires? (?:separate )?written authorization", re.I)


def normalized_blocks(text):
    """Every sentence, line and table cell of ``text``, whitespace-normalized.

    Classification compares WHOLE BLOCKS. Substring containment cannot tell a
    grant from a denial that quotes it, and an ACTIVE claim is too consequential
    to infer from a fragment appearing somewhere in a document.

    Sentence splitting is applied to each table CELL as well as to the whole
    line. A licence table states the claim inside a cell that also carries
    rights sentences the claim does not touch ("...; they are NOT software and
    are NOT GPL-3.0-only."), and splitting only the whole row tears sentences
    across cell boundaries - so the grant sentence was never a block of
    anything and a correctly activated table could not be recognised. This
    only ADDS blocks that were always there structurally; it never relaxes the
    exact-equality test that decides the state.
    """
    pieces = []
    for line in str(text).splitlines():
        for unit in [line] + line.split("|"):
            pieces.append(unit)
            pieces.extend(re.split(r"(?<=[.!?])\s+", unit))
    return {normalize_prose(piece) for piece in pieces if piece.strip()}


#: Figure 1 and Figure 4 must each be named. "Figures 1 and 4" satisfies both.
#: "Figure 1" alone does not license Figure 4 and must never register as the
#: marker meaning the whole artwork grant is in force.
FIG1_RX = re.compile(r"fig01\b|Figure_01|Figures? 1(?!\d)|Figs?\. 1(?!\d)"
                     r"|Figures 1 and 4|Figures 1 & 4", re.I)
#: NOTE the absence of a bare ``and 4`` alternative. It used to be here, and it
#: meant that "Figure 1 artwork is licensed under CC BY 4.0, AND 4 COPIES
#: EXIST." named Figure 4 as far as this rule was concerned - a sentence about
#: how many copies there are registered as the grant over a second figure it
#: never mentions. Figure 4 must be named as a figure.
FIG4_RX = re.compile(r"fig04\b|Figure_04|Figures? 4(?!\d)|Figs?\. 4(?!\d)"
                     r"|Figures 1 and 4|Figures 1 & 4", re.I)

#: A PRESENT-TENSE AFFIRMATIVE grant. Naming the artwork and naming the licence
#: is not a grant: "Figures 1 and 4 and CC BY 4.0 are discussed in Section 2"
#: names both and asserts nothing. There has to be a construction that puts the
#: licence IN FORCE, now.
#: The grant must be made OF THE ARTWORK, by a copula whose subject is the
#: artwork itself. The alternatives that used to be here - "the project
#: licenses ...", "we grant ...", "... applies to ..." - are UNRELATED GRANTING
#: VERBS in this context: their subject is somebody or something other than the
#: Figure 1 / Figure 4 artwork, so "The project licenses data; Figure 1 and
#: Figure 4 artwork and CC BY 4.0 are discussed." satisfied the grant test with
#: a clause that grants nothing over either figure.
GRANT_RX = re.compile(
    r"\b(?:is|are)\s+(?:hereby\s+)?"
    r"(?:licen[sc]ed|released|distributed|made available|published)\b"
    r"|\b(?:is|are)\s+in\s+force\b", re.I)

#: Concession and contrast. "X is licensed under CC BY 4.0, ALTHOUGH approval
#: is required" states the grant and then takes it back; the clause as a whole
#: is not an assertion that the licence is in force.
CONTRAST_RX = re.compile(
    r"\balthough\b|\bthough\b|\bhowever\b|\bbut\b|\bwhereas\b|\byet\b"
    r"|\bnotwithstanding\b|\bcaveat\b|\bwith the exception\b"
    r"|\bother than\b|\bsave (?:for|that)\b|\bin principle\b"
    r"|\bnominally\b|\bostensibly\b|\bwould otherwise\b", re.I)

#: An outstanding authorization. A clause that says permission is required has
#: not recorded permission, whichever way round it puts the words.
AUTHORIZATION_PENDING_RX = re.compile(
    r"\b(?:approval|authoriz\w+|authoris\w+|permission|consent|sign-?off)\b"
    r"[^.]{0,40}?\b(?:is|are|remains?|will be|to be)\s+"
    r"(?:still\s+)?(?:required|needed|outstanding|pending|awaited|sought)\b"
    r"|\b(?:requires?|needs?|awaits?|pending)\s+"
    r"(?:separate\s+|prior\s+|written\s+){0,2}"
    r"(?:approval|authoriz\w+|authoris\w+|permission|consent|sign-?off)\b",
    re.I)

#: ONE anchored, simple affirmative clause. The pieces are named so the shape
#: is readable: a SUBJECT that jointly identifies Figure 1 and Figure 4, a
#: copula, an affirmative granting participle, and CC BY 4.0 placed in force
#: over that subject. Anything before the subject or after the licence - a
#: second sentence, a subordinate clause, a conjunction dragging in another
#: proposition - is outside the grammar, and a trailing parenthetical is the
#: only decoration allowed.
_SUBJECT = (r"(?:the\s+)?"
            r"(?:figures?\s+1\s+(?:and|&)\s+(?:figure\s+)?4"
            r"|figs?\.?\s+1\s+(?:and|&)\s+(?:fig\.?\s*)?4)"
            r"(?:\s+(?:slide\s+|schematic\s+|manuscript\s+)?"
            r"(?:artwork|figures|images|panels|rasters))?")
_COPULA = r"(?:is|are)\s+(?:hereby\s+)?"
_GRANTED = r"(?:licen[sc]ed|released|distributed|made\s+available|published)"
_LICENCE_NAME = (r"(?:(?:the\s+)?creative\s+commons\s+attribution\s+4\.0"
                 r"(?:\s+international)?"
                 r"(?:\s+(?:licen[sc]e|public\s+licen[sc]e))?"
                 r"|CC\s*BY\s*4\.0)")
#: The ONLY parentheticals a registrable marker may carry, enumerated.
#:
#: Allowing arbitrary `([^()]*)` was a hole the size of the clause itself: the
#: grammar checked the subject and the predicate and then accepted anything at
#: all in brackets after them, so
#:
#:     Figures 1 and 4 are licensed under CC BY 4.0 (without authorization).
#:     Figures 1 and 4 are licensed under CC BY 4.0 (approval denied).
#:     Figures 1 and 4 are licensed under CC BY 4.0 (authorization revoked).
#:     Figures 1 and 4 are licensed under CC BY 4.0 (only after consent).
#:     Figures 1 and 4 are licensed under CC BY 4.0 (expires tomorrow).
#:
#: all registered as grants in force. A parenthetical is not decoration - it
#: qualifies the sentence it hangs off - so nothing goes in one unless it has
#: been enumerated here as harmless.
#:
#: Two kinds are allowed, and no others: an ALIAS that renames the licence
#: already named in the predicate, and the TEST-ONLY decoration the synthetic
#: fixtures carry so that test wording can never be mistaken for authored
#: wording.
ALLOWED_PARENTHETICALS = (
    r"CC\s*BY\s*4\.0",
    r"(?:the\s+)?creative\s+commons\s+attribution\s+4\.0"
    r"(?:\s+international)?(?:\s+(?:licen[sc]e|public\s+licen[sc]e))?",
    r"TEST-ONLY\s+SYNTHETIC\s+WORDING(?:,\s*VARIANT\s+[A-Z0-9]+)?",
)
_ALLOWED_PARENTHETICAL_RX = re.compile(
    r"|".join(f"(?:{alt})" for alt in ALLOWED_PARENTHETICALS), re.I)
_PARENTHETICAL_RX = re.compile(r"\(([^()]*)\)")
_TAIL = (r"(?:\s*\((?:"
         + r"|".join(f"(?:{alt})" for alt in ALLOWED_PARENTHETICALS)
         + r")\))*\s*\.?")
ACTIVE_CLAUSE_RX = re.compile(
    rf"^{_SUBJECT}\s+{_COPULA}{_GRANTED}\s+under\s+{_LICENCE_NAME}{_TAIL}$",
    re.I)

#: Conditional, deferred and hypothetical constructions. A licence that MAY be
#: granted, WOULD be granted, or is granted SUBJECT TO something is not a
#: licence in force, and the wording that says so must never be registrable as
#: the wording that says it is.
CONDITIONAL_RX = re.compile(
    r"\bif\b|\bmay\b|\bmight\b|\bcould\b|\bwould\b|\bshould\b|\bshall\b"
    r"|\bsubject to\b|\bprovided that\b|\bprovided\b|\bupon\b|\bonce\b"
    r"|\bafter approval\b|\bpending approval\b|\bon approval\b|\bexcept\b"
    r"|\bconditional\b|\bcontingent\b|\bwhen approved\b|\bif approved\b"
    r"|\bwill be\b|\bto be\b", re.I)


def active_marker_shape_issues(marker):
    """Is ``marker`` a registrable ACTIVE marker at all?

    Returns a list of (code, why). This is the CENTRAL definition of what an
    active marker may look like, and every surface that could turn wording into
    an ACTIVE classification runs it: the classifier, the emitted publication
    row, and the activation planner. Enforcing it in the planner alone left the
    classifier able to register a marker the planner would have rejected.

    A registrable marker names Figure 1 AND Figure 4 - separately, so a clause
    covering only one of them cannot stand for both - names CC BY 4.0, carries
    an explicit present-tense affirmative granting construction, and contains
    no conditional, deferred or hypothetical language. A generic token like
    "CC BY 4.0" is refused outright: it appears in a dozen unrelated sentences,
    several of which say the licence does NOT apply.
    """
    text = normalize_prose(marker)
    issues = []
    if len(text) < MIN_ACTIVE_MARKER:
        issues.append(("CCBY_ACTIVE_MARKER_GENERIC",
                       f"{marker!r} is too short to be a scoped clause "
                       f"({len(text)} < {MIN_ACTIVE_MARKER} characters)"))
    if not FIG1_RX.search(text):
        issues.append(("CCBY_ACTIVE_MARKER_UNSCOPED",
                       f"{marker!r} does not name Figure 1; a clause covering "
                       f"only one of the two figures must never register as "
                       f"the grant over both"))
    if not FIG4_RX.search(text):
        issues.append(("CCBY_ACTIVE_MARKER_UNSCOPED",
                       f"{marker!r} does not name Figure 4; a clause covering "
                       f"only one of the two figures must never register as "
                       f"the grant over both"))
    if not CCBY_RX.search(text):
        issues.append(("CCBY_ACTIVE_MARKER_UNSCOPED",
                       f"{marker!r} does not name CC BY 4.0"))
    if NEGATION_RX.search(text):
        issues.append(("CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE",
                       f"{marker!r} reads as a denial, exclusion or deferral, "
                       f"not as a grant in force"))
    if CONDITIONAL_RX.search(text):
        issues.append((
            "CCBY_ACTIVE_MARKER_CONDITIONAL",
            f"{marker!r} is conditional, deferred or hypothetical. A licence "
            f"that MAY be granted, or is granted IF or AFTER something else "
            f"happens, is not a licence in force"))
    elif not GRANT_RX.search(text):
        # Only asked when the clause is not already conditional, so the
        # operator sees the ONE reason it was refused rather than two.
        issues.append((
            "CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE",
            f"{marker!r} names the artwork and the licence but contains no "
            f"present-tense affirmative granting construction whose subject is "
            f"the artwork; mentioning both is not asserting one, and a grant "
            f"made by some other subject over some other thing is not a grant "
            f"over these two figures"))
    if AUTHORIZATION_PENDING_RX.search(text):
        issues.append((
            "CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE",
            f"{marker!r} says an approval, authorization, permission or "
            f"consent is still required. A clause that records the permission "
            f"as outstanding is the opposite of the clause that records it as "
            f"given"))
    if CONTRAST_RX.search(text):
        issues.append((
            "CCBY_ACTIVE_MARKER_QUALIFIED",
            f"{marker!r} qualifies or contradicts itself with a concession or "
            f"contrast. A grant stated and then withdrawn in the same breath "
            f"is not a grant in force"))
    issues.extend(_simple_clause_issues(marker, text))
    return issues


#: Sentence terminators and clause separators, once the abbreviations that
#: legitimately carry a full stop have been taken out of the way.
_ABBREVIATION_RX = re.compile(
    r"\bFigs?\.|\b(?:e\.g|i\.e|cf|etc|vs|no|approx|ca)\.", re.I)


def _simple_clause_issues(marker, text):
    """The marker must be ONE simple clause, and must match the grammar.

    Two separate failures used to slip through everything above.

    A marker could be a whole PARAGRAPH: "Figure 1 is licensed under CC BY 4.0.
    Figure 4 is discussed elsewhere." names both figures, names the licence,
    reads as affirmative and is conditional in no way - and it licenses one
    figure while merely mentioning the other. Only the second sentence supplies
    "Figure 4", and it says nothing about licensing.

    And a marker could satisfy every keyword test while being ungrammatical as
    a grant: the tests above are all SEARCHES, so a document could scatter the
    subject, the verb and the licence across unrelated propositions and pass
    every one of them. The grammar below is ANCHORED - the marker in its
    entirety has to be the clause, with nothing before the subject and nothing
    after the licence but a parenthetical.
    """
    issues = []
    for inner in _PARENTHETICAL_RX.findall(text):
        if not _ALLOWED_PARENTHETICAL_RX.fullmatch(inner.strip()):
            issues.append((
                "CCBY_ACTIVE_MARKER_PARENTHETICAL",
                f"{marker!r} carries the parenthetical ({inner.strip()}), "
                f"which is not one of the enumerated harmless ones. A "
                f"parenthetical qualifies the sentence it hangs off - "
                f"'(without authorization)', '(approval denied)', "
                f"'(expires tomorrow)' - so only a licence alias or the "
                f"TEST-ONLY decoration may appear in one"))
    probe = _ABBREVIATION_RX.sub("X", text)
    if ";" in probe or ":" in probe or re.search(r"[.!?]\s+\S", probe):
        issues.append((
            "CCBY_ACTIVE_MARKER_COMPOUND",
            f"{marker!r} is more than one clause. A registrable marker is a "
            f"single simple sentence: across two of them, one can name Figure "
            f"1 and grant the licence while the other merely mentions Figure "
            f"4, and the pair reads as a grant over both"))
    if not ACTIVE_CLAUSE_RX.match(text):
        issues.append((
            "CCBY_ACTIVE_MARKER_UNGRAMMATICAL",
            f"{marker!r} is not an anchored affirmative clause of the required "
            f"shape: a subject that jointly identifies Figure 1 and Figure 4, "
            f"a present-tense copula, an affirmative granting participle, and "
            f"CC BY 4.0 placed in force over that subject - and nothing else "
            f"except a trailing parenthetical"))
    return issues


#: The token that marks wording as belonging to the test fixtures. It exists
#: so a synthetic clause can never be mistaken for an authored one - which only
#: works if production actually refuses it.
SYNTHETIC_MARKER_TOKEN = "TEST-ONLY"


def is_synthetic_contract(contract):
    """Whether this contract has DECLARED itself a test fixture.

    Opt-in, and opt-in only. A contract that says nothing is production, so the
    real contract cannot become "synthetic" by omission - which is the failure
    direction that matters.
    """
    return bool((contract or {}).get("synthetic_fixture"))


#: The key by which a contract opts OUT of the reviewed-prose pins, the
#: code-owned scope pins and the TEST-ONLY wording refusal.
SYNTHETIC_FIXTURE_KEY = "synthetic_fixture"


def production_contract_issues(contract):
    """A PRODUCTION contract may not carry ``synthetic_fixture`` at all.

    ``is_synthetic_contract`` is opt-in so that the test fixtures can drive
    activation with invented wording, and every guard that consults it returns
    early - the reviewed-prose digests, the code-owned scope pins and the
    TEST-ONLY wording refusal all switch off together. That is correct for a
    fixture built in a temporary directory and catastrophic for the tracked
    contract: committing one line, ``"synthetic_fixture": true``, would disable
    the entire legal-scope apparatus while every guard still reported PASS.

    So the production loader refuses the KEY, not merely the value ``true``.
    ``false``, ``0`` and ``null`` are refused too: a production contract has no
    business discussing whether it is a fixture, and accepting the falsey forms
    would leave a reviewer diffing a one-character change from ``false`` to
    ``true`` as the only thing between the release and an unpinned scope.
    """
    if SYNTHETIC_FIXTURE_KEY in (contract or {}):
        return [(
            "CONTRACT_DECLARES_SYNTHETIC_FIXTURE",
            f"the tracked contract carries {SYNTHETIC_FIXTURE_KEY!r}="
            f"{(contract or {}).get(SYNTHETIC_FIXTURE_KEY)!r}. That key exists "
            f"so TEST fixtures can opt out of the reviewed-prose pins, the "
            f"code-owned artwork-scope pins and the TEST-ONLY wording refusal. "
            f"A production contract may not carry it in ANY form - present and "
            f"false is refused as surely as present and true, because the "
            f"difference between them is one character in a file the release "
            f"then trusts to define what it is licensing")]
    return []


def synthetic_wording_issues(contract):
    """Every place TEST-ONLY wording has reached a PRODUCTION contract.

    The synthetic clause exists so the tests can drive the ACTIVE state without
    anybody having to write draft licence prose. That protection is worth
    nothing if the same wording can reach a production contract, activation
    plan, publication row or replacement - at which point the repository would
    be asserting a copyright licence over a coauthor's artwork in wording whose
    own text says it is not real.
    """
    contract = contract or {}
    if is_synthetic_contract(contract):
        return []
    issues = []
    token = SYNTHETIC_MARKER_TOKEN

    def _check(where, value):
        if value and token in str(value):
            issues.append((
                "CCBY_TESTONLY_WORDING_IN_PRODUCTION",
                f"{where} carries {token} wording: {str(value)[:120]!r}. That "
                f"wording belongs to the test fixtures and must never appear "
                f"in a production contract, activation plan, publication row "
                f"or replacement"))

    markers = contract.get("artwork_licence_markers") or {}
    for slot in ("active", "pending"):
        for marker in markers.get(slot) or []:
            _check(f"artwork_licence_markers.{slot}", marker)
    rows = contract.get("publication_outputs_artwork_row") or {}
    if isinstance(rows, dict):
        for slot, row in rows.items():
            _check(f"publication_outputs_artwork_row.{slot}", row)
    plan = contract.get("ccby_activation_plan") or {}
    for entry in plan.get("replacements") or []:
        if isinstance(entry, dict):
            for key in ("from", "to", "file"):
                _check(f"ccby_activation_plan.replacements.{key}",
                       entry.get(key))
        else:
            _check("ccby_activation_plan.replacements", entry)
    return sorted(set(issues))


def registrable_active_markers(contract):
    """The contract's active markers that are ACTUALLY registrable.

    A marker that fails the shape test can never produce an ACTIVE
    classification. Filtering here rather than at each call site is what makes
    the rule central: a badly-shaped marker simply does not exist as far as the
    classifier is concerned, so a document carrying it stays UNCLASSIFIED and
    the state machine reports LICENCE_STATE_UNREADABLE instead of quietly
    asserting a grant nobody wrote.
    """
    markers = (contract or {}).get("artwork_licence_markers") or {}
    return [m for m in (markers.get("active") or [])
            if m and not active_marker_shape_issues(m)]


def classify_claim(text, contract=None):
    """Classify one document's claim about the Figure 1 / Figure 4 artwork.

    Decided by the EXACT markers in the trusted contract, never by broad
    vocabulary. The previous implementation scanned whole documents for words
    like ``prohibited``, ``must not``, ``may not`` and ``no CC BY``. Those
    match a great deal of legitimate unrelated prose - a "prohibited-region
    invariance" note, or a sentence correctly stating that the underlying ERA5
    data carries no CC BY licence - so a record could read as artwork-PENDING
    for reasons having nothing to do with the artwork. Worse, such a sentence
    would still be there after a correct activation, so ACTIVE could never be
    reached.

    Every unrelated ERA5, GHCN, Natural Earth, software and font restriction is
    therefore invisible to this function.
    """
    contract = contract if contract is not None else load_trusted_contract()
    markers = contract.get("artwork_licence_markers") or {}
    for marker in markers.get("pending") or []:
        if marker and marker in text:
            return PENDING
    # ACTIVE requires EXACT normalized block equality, never containment. A
    # denial that quotes the grant contains it as a substring.
    #
    # And only a REGISTRABLE marker counts. The shape test - both figures
    # named, CC BY 4.0 named, an affirmative present-tense grant, no
    # conditional language - is applied HERE, in the shared classifier, not
    # only in the activation planner. Enforcing it in the planner alone meant a
    # contract carrying "Figure 1 may be licensed after approval" in the active
    # slot would be refused at activation time but still classify an existing
    # document as ACTIVE if that sentence happened to be in it.
    blocks = normalized_blocks(text)
    for marker in registrable_active_markers(contract):
        if normalize_prose(marker) in blocks:
            return ACTIVE
    # EXACT MARKERS ONLY. There is deliberately no "any Figure 1/4 sentence
    # mentioning CC BY counts as active" fallback: that reads
    #
    #     "Figure 1 is NOT licensed under CC BY 4.0."
    #
    # - a DENIAL of the grant - as an assertion of it, because the sentence
    # mentions both the artwork and the licence. Negation, exclusion and
    # "requires written authorization" phrasings are all indistinguishable
    # from a grant at that level of analysis. An unrecognised document is
    # therefore UNCLASSIFIED, which the state machine reports as
    # LICENCE_STATE_UNREADABLE rather than resolving in either direction.
    return None


def is_active(repo_root=None, contract=None):
    """Convenience predicate for callers that only need the boolean."""
    state, _issues, _detail = artwork_licence_state(repo_root, contract)
    return state == ACTIVE


# ---------------------------------------------------------------------------
# Authored wording - served, never invented
# ---------------------------------------------------------------------------
def publication_artwork_row(repo_root=None, contract=None):
    """The publication-output licence-table row for the Fig. 1 / Fig. 4 art.

    Both wordings come from the TRUSTED TRACKED CONTRACT. This module does not
    author either of them, and in particular will not synthesize the active
    one: activating CC BY rewrites a legal claim about a coauthor's copyright,
    and that prose is the authors' to write.
    """
    root = repository_root(repo_root)
    contract = (contract if contract is not None
                else load_trusted_contract(root))
    rows = contract.get("publication_outputs_artwork_row") or {}
    state, issues, _detail = artwork_licence_state(root, contract)

    if state == PENDING:
        row = rows.get("pending")
        if not row:
            raise RuntimeError(
                "ARTWORK_ROW_PENDING_MISSING: the trusted contract carries no "
                "pending publication row")
        return _checked_row(row, state, contract)
    if state == ACTIVE:
        row = rows.get("active")
        if not row:
            raise RuntimeError(
                "ARTWORK_ROW_ACTIVE_UNAUTHORED: the artwork licence is ACTIVE "
                "but the trusted contract carries no author-written active "
                "publication row. This tool will not invent the licence "
                "prose.")
        return _checked_row(row, state, contract)
    raise RuntimeError(
        f"ARTWORK_LICENCE_STATE_INCONSISTENT: refusing to render a licence "
        f"row while the state is {state}: {issues}")


def _checked_row(row, state, contract):
    """The emitted row must itself classify as the state it is emitted for.

    Central, so neither the builder nor any caller can publish a row that
    contradicts the repository. Without it the "active" slot could hold
    "Figures 1 and 4 are NOT licensed under CC BY 4.0" - a DENIAL - and it
    would be shipped verbatim as the active grant.
    """
    if not str(row).strip():
        raise RuntimeError(
            f"ARTWORK_ROW_EMPTY: the {state} publication row is empty")
    if state == ACTIVE:
        # The marker shape rule applies to what is PUBLISHED, not only to what
        # the classifier will later recognise. A contract whose active markers
        # are all unregistrable cannot emit an active row at all, and the row
        # itself must carry one of the registrable ones.
        registrable = registrable_active_markers(contract)
        if not registrable:
            markers = ((contract or {}).get("artwork_licence_markers")
                       or {}).get("active") or []
            reasons = [why for m in markers
                       for _code, why in active_marker_shape_issues(m)]
            raise RuntimeError(
                f"ARTWORK_ROW_ACTIVE_MARKER_UNREGISTRABLE: none of the "
                f"contract's active markers is a complete affirmative "
                f"present-tense grant naming BOTH Figure 1 and Figure 4 and "
                f"CC BY 4.0: {reasons[:4]}")
        row_blocks = normalized_blocks(row)
        if not any(normalize_prose(m) in row_blocks for m in registrable):
            raise RuntimeError(
                f"ARTWORK_ROW_ACTIVE_MARKER_ABSENT: the active publication "
                f"row carries none of the registrable active markers, so what "
                f"would be published does not assert the grant it is emitted "
                f"to assert: {str(row)[:120]!r}")
    claim = classify_claim(row, contract)
    if claim != state:
        raise RuntimeError(
            f"ARTWORK_ROW_STATE_MISMATCH: the {state} publication row "
            f"classifies as {claim!r}, not {state!r}. A row carrying no "
            f"registered {state} marker - or carrying the opposite one - must "
            f"never be emitted: {str(row)[:120]!r}")
    return row
