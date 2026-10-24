"""Content-addressed certificate archive; original selected files remain untouched."""
import hashlib
import os
import tempfile
from pathlib import Path


def archive_certificate(source, db_path):
    source = Path(source).resolve(strict=True)
    payload = source.read_bytes()
    if not payload.startswith(b'%PDF-'):
        raise ValueError('The selected certificate is not a PDF file.')
    digest = hashlib.sha256(payload).hexdigest()
    archive = Path(db_path).resolve().parent / 'certs'
    archive.mkdir(parents=True, exist_ok=True)
    target = archive / (digest + '.pdf')
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('The archived certificate failed its hash check.')
        return str(target), digest
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=archive, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return str(target), digest
