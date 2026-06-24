"""
Pickle detector — rejects pickle-format LangChain/other inputs.
Pickle deserialization is an arbitrary code execution vector.
This tool never deserializes pickle data under any circumstances.
"""

from __future__ import annotations

import io


# Python pickle magic bytes (protocol 0-5)
_PICKLE_MAGIC_BYTES = [
    b"\x80\x02",  # Protocol 2
    b"\x80\x03",  # Protocol 3
    b"\x80\x04",  # Protocol 4
    b"\x80\x05",  # Protocol 5
    b"(",         # Protocol 0 (MARK opcode)
    b"]",         # Protocol 0 (EMPTY_LIST)
    b"}",         # Protocol 0 (EMPTY_DICT)
    b"ccopy_reg", # Common pickle header
    b"cbuiltins", # Common pickle header
]

# File extensions associated with pickle data
_PICKLE_EXTENSIONS = {".pkl", ".pickle", ".pt", ".pth", ".joblib"}


class PickleDetectedError(Exception):
    """Raised when pickle-format input is detected."""

    def __init__(self, source: str) -> None:
        super().__init__(
            f"Pickle format detected in '{source}'. "
            "Loading pickle files is a security risk (arbitrary code execution). "
            "This tool does not accept pickle-format inputs. "
            "Please convert your data to JSON or YAML format and try again."
        )


def check_bytes(data: bytes, source: str = "input") -> None:
    """
    Raise PickleDetectedError if `data` looks like pickle-serialized content.
    Call this before processing any binary input from users.
    """
    if not data:
        return

    for magic in _PICKLE_MAGIC_BYTES:
        if data.startswith(magic):
            raise PickleDetectedError(source)

    # Check a slice — some pickle files have headers before magic bytes
    if len(data) > 2 and data[:2] in {b"\x80\x02", b"\x80\x03", b"\x80\x04", b"\x80\x05"}:
        raise PickleDetectedError(source)


def check_file_path(path: str) -> None:
    """
    Raise PickleDetectedError if the file extension suggests pickle format.
    Call this before opening any user-provided file path.
    """
    import os
    _, ext = os.path.splitext(path.lower())
    if ext in _PICKLE_EXTENSIONS:
        raise PickleDetectedError(path)


def check_file_object(f: io.IOBase, source: str = "file") -> None:
    """
    Raise PickleDetectedError if the first bytes of an open file look like pickle.
    Resets the file pointer to the start after checking.
    """
    if hasattr(f, "read") and hasattr(f, "seek"):
        header = f.read(16)  # type: ignore[attr-defined]
        f.seek(0)  # type: ignore[attr-defined]
        if isinstance(header, bytes):
            check_bytes(header, source)
