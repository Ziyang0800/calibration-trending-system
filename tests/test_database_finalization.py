from pathlib import Path
import sqlite3
import pytest
import db
from tools.finalize_database import finalize, measurement_fingerprint


def test_finalize_archives_paths_and_preserves_measurements(tmp_path):
    database=tmp_path/'local.db'
    c=db.connect(str(database))
    aid=db.upsert_asset(c,'FINAL','TEST','TEST',1)
    pdf=tmp_path/'original.pdf';pdf.write_bytes(b'%PDF-1.4\nverified source')
    db.insert_calibration(c,aid,'2026-01-01',1.000001,1e-6,'test',cert_pdf_path=str(pdf))
    db.insert_calibration(c,aid,'2025-01-01',1,1e-6,'test',cert_pdf_path=str(tmp_path/'missing.pdf'))
    before=measurement_fingerprint(c);c.close()
    result=finalize(database,tmp_path/'backups',apply=True)
    assert result['integrity']=='ok' and result['certificate_links_updated']==1
    assert len(result['missing_certificates'])==1
    c=sqlite3.connect(database)
    assert measurement_fingerprint(c)==before
    path=c.execute("select cert_pdf_path from calibrations where cal_date='2026-01-01'").fetchone()[0]
    assert Path(path).parent==tmp_path/'certs'
    assert Path(path).read_bytes()==pdf.read_bytes()
    c.close()
    backup=sqlite3.connect(result['backup'])
    assert backup.execute("select cert_pdf_path from calibrations where cal_date='2026-01-01'").fetchone()[0]==str(pdf)
    backup.close()
    assert finalize(database,tmp_path/'backups',apply=True)['certificate_links_updated']==0


def test_finalize_requires_backup_for_apply(tmp_path):
    database=tmp_path/'local.db';db.connect(str(database)).close()
    before=database.read_bytes()
    assert finalize(database)['applied'] is False
    with pytest.raises(ValueError,match='backup'):
        finalize(database,apply=True)
    assert database.read_bytes()==before
