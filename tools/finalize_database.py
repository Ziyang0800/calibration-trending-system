"""Back up and finalize certificate storage without changing calibration measurements."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db
from certificate_store import archive_certificate


def measurement_fingerprint(connection):
    data = {}
    for table in ('assets', 'test_points', 'calibrations', 'calibration_readings'):
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info({table})') if row[1] != 'cert_pdf_path']
        quoted = ','.join('"' + column + '"' for column in columns)
        data[table] = connection.execute(f'SELECT {quoted} FROM {table} ORDER BY id').fetchall()
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def finalize(database, backup_dir=None, apply=False):
    database = Path(database).resolve(strict=True)
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    try:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity validation failed.')
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Database contains foreign-key violations.')
        before = measurement_fingerprint(connection)
        counts = {name: connection.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                  for name in ('assets', 'calibrations', 'test_points', 'calibration_readings')}
        references = connection.execute('SELECT id, cert_pdf_path FROM calibrations WHERE cert_pdf_path IS NOT NULL').fetchall()
        report = {'database': str(database), 'counts': counts, 'missing_certificates': [], 'archived_certificates': [],
                  'schema_version_before': connection.execute('PRAGMA user_version').fetchone()[0], 'applied': apply}
        if apply:
            if not backup_dir:
                raise ValueError('Applying changes requires a backup directory.')
            backup_dir = Path(backup_dir).resolve()
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f'calibration-{datetime.now():%Y%m%d_%H%M%S}-{uuid.uuid4().hex[:8]}.db'
            target = sqlite3.connect(backup)
            try:
                connection.backup(target)
                assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            finally:
                target.close()
            report['backup'] = str(backup)
    finally:
        connection.close()
    updates = []
    for calibration_id, original in references:
        source = Path(original)
        if not source.is_absolute():
            source = database.parent / source
        if not source.is_file():
            report['missing_certificates'].append({'calibration_id': calibration_id, 'path': original})
            continue
        if apply:
            archived, digest = archive_certificate(source, database)
            if archived != original:
                updates.append((archived, calibration_id))
            report['archived_certificates'].append({'calibration_id': calibration_id, 'path': archived, 'sha256': digest})
    if apply:
        connection = db.connect(str(database))
        try:
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                if measurement_fingerprint(connection) != before:
                    raise ValueError('Calibration data changed during finalization; stop the application and retry.')
                connection.executemany('UPDATE calibrations SET cert_pdf_path=? WHERE id=?', updates)
                if measurement_fingerprint(connection) != before:
                    raise ValueError('Measurement preservation check failed.')
                if connection.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('Foreign-key check failed after finalization.')
            report['schema_version_after'] = connection.execute('PRAGMA user_version').fetchone()[0]
            report['integrity'] = connection.execute('PRAGMA integrity_check').fetchone()[0]
            report['measurement_fingerprint'] = before
            report['certificate_links_updated'] = len(updates)
        finally:
            connection.close()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--backup-dir')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--report')
    args = parser.parse_args()
    result = finalize(args.database, args.backup_dir, args.apply)
    output = json.dumps(result, indent=2)
    if args.report:
        Path(args.report).write_text(output, encoding='utf-8')
    print(output)
