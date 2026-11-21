"""Generate the gateway encryption key once in its private named volume."""
from base64 import urlsafe_b64encode
import os
from pathlib import Path
from secrets import token_bytes
from stat import S_IMODE
from tempfile import NamedTemporaryFile


vault = Path("/srv/marsad/model-secrets")
key_path = vault / "master.key"
if not key_path.exists():
    with NamedTemporaryFile(dir=vault, prefix=".master-", delete=False) as candidate:
        temporary_path = Path(candidate.name)
        try:
            candidate.write(urlsafe_b64encode(token_bytes(32)) + b"\n")
            candidate.flush()
            os.fsync(candidate.fileno())
            try:
                os.link(temporary_path, key_path)
            except FileExistsError:
                pass
        finally:
            temporary_path.unlink()
if not key_path.is_file() or S_IMODE(key_path.stat().st_mode) != 0o600:
    raise SystemExit("Model vault key must be a private file.")
