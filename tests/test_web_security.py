"""Local web security and shared validation, without launching a server."""
import pytest
import db
import MainApp
from test_audit_regressions import create_event


@pytest.fixture
def web(tmp_path, monkeypatch):
    path=str(tmp_path/'web.db')
    aid,cid,points=create_event(path,True)
    monkeypatch.setitem(MainApp.app.config,'DB_PATH',path)
    monkeypatch.setitem(MainApp.app.config,'TESTING',True)
    monkeypatch.setattr(MainApp,'PENDING_DIR',str(tmp_path/'pending'))
    client=MainApp.app.test_client()
    return client,path,aid,cid


def token(client):
    with client.session_transaction() as session:
        session['csrf_token']='audit-token'
    return {'csrf_token':'audit-token'}


def test_csrf_and_remote_clients_are_rejected(web):
    client,path,aid,cid=web
    assert client.post(f'/calibrations/{cid}/delete').status_code==403
    assert client.get('/api/dashboard',environ_overrides={'REMOTE_ADDR':'192.0.2.1'}).status_code==403
    assert client.get('/api/dashboard',headers={'Host':'attacker.example'}).status_code==403
    assert client.post(f'/calibrations/{cid}/delete',data=token(client),headers={'Origin':'https://attacker.example'}).status_code==403
    c=db.connect(path);assert c.execute('select count(*) from calibrations').fetchone()[0]==1;c.close()


def test_token_path_traversal_is_rejected(web):
    client,_,_,_=web
    result=client.post('/import/cancel',data={**token(client),'row_count':'1','token_0':'../../victim'})
    assert result.status_code==400


def test_rendered_forms_have_csrf_tokens(web):
    client,_,_,_=web
    result=client.get('/import')
    assert result.status_code==200
    assert b'name="csrf_token"' in result.data


def test_web_editor_uses_atomic_validation(web):
    client,path,aid,cid=web
    result=client.post(f'/calibrations/{cid}/edit',data={**token(client),'cal_date':'invalid','reviewer_comment':'must not save'})
    assert result.status_code==400
    c=db.connect(path);assert c.execute('select reviewer_comment from calibrations').fetchone()[0] is None;c.close()


def test_web_scalar_cannot_import_multi_point_asset(web,tmp_path):
    client,path,aid,cid=web
    token_value='a'*32
    folder=tmp_path/'pending';folder.mkdir();(folder/(token_value+'.pdf')).write_bytes(b'%PDF-1.4')
    result=client.post('/import/confirm',data={**token(client),'row_count':'1','token_0':token_value,
        'include_0':'on','serial_0':'AUDIT','cal_date_0':'2021-01-01','measured_value_0':'1','mu_relative_0':'0.000001'})
    assert b'Point readings are required' in result.data
    c=db.connect(path);assert c.execute('select count(*) from calibrations').fetchone()[0]==1;c.close()
