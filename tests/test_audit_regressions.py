"""Regressions for the read-only audit findings; use temporary databases only."""
from datetime import date, timedelta
from pathlib import Path
import hashlib
import sqlite3
import threading
import pytest
import db
import queries
import service
import store
import cal_cert_importer as importer
from certificate_store import archive_certificate
from trending import compute_trend
from test_import_service import svc_and_db
from test_multi_point_certificate_import import FakePage, FakePdf


def create_event(path, multipoint=False):
    c = db.connect(path)
    aid = db.upsert_asset(c, 'AUDIT', 'TEST', 'TEST', 10 if multipoint else 1,
        category='dcv_reference' if multipoint else 'standard_resistor', unit='V' if multipoint else 'Ω')
    points = [db.upsert_test_point(c, aid, f'{v}V', 'Output', v, 'V', i) for i, v in enumerate((1, 10))] if multipoint else []
    cid = db.insert_calibration(c, aid, '2020-01-01', 1, 2e-6, 'test', pressure_hpa=1000, location='Lab A')
    for point in points:
        db.insert_calibration_reading(c, cid, point, 1, uncertainty=24.4)
    c.close()
    return aid, cid, points


def test_note_only_edit_preserves_all_metadata(svc_and_db):
    svc, path = svc_and_db
    _, cid, _ = create_event(path)
    assert svc.save_calibration_edit({'id': cid, 'reviewer_comment': 'reviewed'})['ok']
    c = db.connect(path)
    assert c.execute('SELECT measured_value,mu_relative,pressure_hpa,location,reviewer_comment FROM calibrations').fetchone() == (1, 2e-6, 1000, 'Lab A', 'reviewed')
    c.close()


@pytest.mark.parametrize('payload', [
    {'cal_date': 'bad'}, {'measured_value': 'nan'}, {'mu_relative': -1}, {'pressure_hpa': 0},
    {'test_point_readings': [{'tp_id': 999, 'measured_value': 2}]},
])
def test_invalid_edit_leaves_event_unchanged(svc_and_db, payload):
    svc, path = svc_and_db
    _, cid, _ = create_event(path)
    result = svc.save_calibration_edit({'id': cid, 'reviewer_comment': 'must not save', **payload})
    assert not result['ok']
    c = db.connect(path)
    assert c.execute('SELECT reviewer_comment FROM calibrations').fetchone()[0] is None
    c.close()


def test_point_edit_and_summary_are_consistent(svc_and_db):
    svc, path = svc_and_db
    _, cid, points = create_event(path, True)
    assert svc.save_calibration_edit({'id': cid, 'test_point_readings': [
        {'tp_id': points[0], 'measured_value': 1.0001, 'uncertainty': 30, 'excluded_from_regression': True}
    ]})['ok']
    cal = svc.get_calibration_for_edit(cid)
    assert cal['measured_value'] == pytest.approx(1.0001)
    assert cal['test_point_readings'][0]['uncertainty'] == 30
    assert cal['test_point_readings'][0]['excluded_from_regression']
    assert cal['test_point_readings'][1]['measured_value'] == 1


def test_database_failure_rolls_back_point_and_event(svc_and_db):
    svc, path = svc_and_db
    _, cid, points = create_event(path, True)
    c = db.connect(path)
    c.execute("CREATE TRIGGER fail_event BEFORE UPDATE ON calibrations BEGIN SELECT RAISE(ABORT, 'simulated storage error'); END")
    c.close()
    result = svc.save_calibration_edit({'id': cid, 'cal_date': '2021-01-01',
        'test_point_readings': [{'tp_id': points[0], 'measured_value': 2}]})
    assert not result['ok']
    cal = svc.get_calibration_for_edit(cid)
    assert cal['cal_date'] == '2020-01-01'
    assert cal['test_point_readings'][0]['measured_value'] == 1


def test_duplicate_edit_date_is_rejected(svc_and_db):
    svc, path = svc_and_db
    aid, cid, _ = create_event(path)
    c = db.connect(path)
    db.insert_calibration(c, aid, '2021-01-01', 2, 1e-6, 'test')
    c.close()
    assert not svc.save_calibration_edit({'id': cid, 'cal_date': '2021-01-01'})['ok']
    assert svc.get_calibration_for_edit(cid)['cal_date'] == '2020-01-01'


def test_flat_baseline_detects_a_jump():
    dates = [date(2020+i, 1, 1) for i in range(4)]
    rows, stats = compute_trend(dates, [1, 1, 1, 2], 1)
    assert stats and rows[-1]['out_of_trend']
    assert rows[-1]['lower'] == rows[-1]['upper'] == 1
    rows, _ = compute_trend(dates, [1, 1, 1, 1], 1)
    assert not rows[-1]['out_of_trend']


def test_empty_and_invalid_trend_inputs():
    assert compute_trend([], []) == ([], None)
    with pytest.raises(ValueError):
        compute_trend([date(2020,1,1)], [])
    with pytest.raises(ValueError):
        compute_trend([date(2020,1,1)]*2, [1,2])


@pytest.mark.parametrize('mode', ['reset', 'excluded', 'missing_latest', 'short'])
def test_multi_point_status_requires_usable_history(svc_and_db, mode):
    _, path = svc_and_db
    aid, first, points = create_event(path, True)
    c = db.connect(path)
    for i in range(1, 2 if mode == 'short' else 4):
        cid = db.insert_calibration(c, aid, f'{2020+i}-01-01', 1, 0, 'test',
            is_adjusted=mode=='reset' and i==3)
        for point in points:
            if mode=='missing_latest' and i==3 and point==points[-1]:
                continue
            db.insert_calibration_reading(c, cid, point, 1, uncertainty=1)
    if mode == 'excluded':
        c.execute('UPDATE calibrations SET excluded_from_regression=1 WHERE id=?', (first,))
        c.commit()
    assert queries.list_assets(c)[0]['status'] == 'insufficient_data'
    if mode != 'missing_latest':
        assert all(p['status']=='insufficient_data' for p in queries.get_asset_detail(c, aid)['test_points'])
    c.close()


@pytest.mark.parametrize('category,text,points', [
 ('dcv_reference', '10 10.000 000 000 35\n10 10.000 999 999 99\n1 0.999 999 999 24.4',
  [{'id':1,'point_name':'10V','nominal_value':10},{'id':2,'point_name':'1V','nominal_value':1}]),
 ('ac_divider', '1kHz 10.0001 3 ppm\n1kHz 10.9999 5 ppm\n20kHz 10.0002 6 ppm',
  [{'id':1,'point_name':'1 kHz'},{'id':2,'point_name':'20 kHz'}]),
])
def test_ambiguous_certificate_rows_remain_blank(monkeypatch, category, text, points):
    monkeypatch.setattr(importer.pdfplumber, 'open', lambda _: FakePdf([FakePage(text)]))
    result = importer.extract_multi_point_measurements('fake', category, points)
    assert not result['ok']
    assert [r['test_point_id'] for r in result['readings']] == [2]


def test_certificate_is_archived_and_hash_verified(tmp_path):
    pdf = tmp_path/'input.pdf'
    payload = b'%PDF-1.4\ncertificate\n%%EOF'
    pdf.write_bytes(payload)
    archived, digest = archive_certificate(pdf, tmp_path/'local.db')
    pdf.unlink()
    assert Path(archived).read_bytes() == payload
    assert digest == hashlib.sha256(payload).hexdigest()
    Path(archived).write_bytes(b'corrupt')
    pdf.write_bytes(payload)
    with pytest.raises(ValueError):
        archive_certificate(pdf, tmp_path/'local.db')


def test_missing_certificate_blocks_import(svc_and_db):
    svc, path = svc_and_db
    aid, _, _ = create_event(path)
    result = svc.commit_imported_certificate({'asset_id':aid,'cal_date':'2021-01-01',
        'measured_value':1,'mu_relative':1e-6,'pdf_path':str(Path(path).parent/'missing.pdf')})
    assert not result['ok']
    c=db.connect(path)
    assert c.execute('SELECT count(*) FROM calibrations').fetchone()[0] == 1
    c.close()


def test_backups_never_replace_shared_database_and_include_documents(monkeypatch, tmp_path):
    local = str(tmp_path/'local.db')
    create_event(local)
    document=tmp_path/'cert.pdf';document.write_bytes(b'%PDF-1.4')
    c=db.connect(local);c.execute('UPDATE calibrations SET cert_pdf_path=?',(str(document),));c.commit();c.close()
    shared=tmp_path/'shared.db';shared.write_bytes(b'existing shared content')
    monkeypatch.setattr(store,'get_local_db_path',lambda:local)
    monkeypatch.setattr(threading.Thread,'start',lambda self:None)
    manager=store.DatabaseSyncManager({'network_db_path':str(shared)})
    results=[manager.sync_now(),manager.sync_now()]
    assert all(r['ok'] for r in results)
    assert results[0]['target'] != results[1]['target']
    assert shared.read_bytes()==b'existing shared content'
    for result in results:
        folder=Path(result['target'])
        assert (folder/'manifest.json').is_file()
        assert len(list((folder/'documents').iterdir()))==1
        c=sqlite3.connect(folder/'calibration.db')
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        c.close()
    assert not manager.is_syncing


def test_newer_database_is_not_migrated(tmp_path):
    path=tmp_path/'future.db'
    c=sqlite3.connect(path);c.execute('pragma user_version=999');c.close()
    with pytest.raises(ValueError,match='newer'):
        db.connect(str(path))
    c=sqlite3.connect(path)
    assert c.execute('pragma user_version').fetchone()[0]==999
    c.close()


def test_one_volt_drift_uses_point_nominal(svc_and_db):
    svc,path=svc_and_db
    aid,_,points=create_event(path,True)
    c=db.connect(path)
    for i in range(1,4):
        cid=db.insert_calibration(c,aid,f'{2020+i}-01-01',1+i*1e-6,0,'test')
        for point in points:
            db.insert_calibration_reading(c,cid,point,1+i*1e-6,uncertainty=24.4)
    c.close()
    detail=svc.get_asset_detail(aid,points[0])
    assert '+1.00 ppm/year' in detail['traceability']['annual_drift_rate']
