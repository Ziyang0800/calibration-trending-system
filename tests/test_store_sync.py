"""Regression tests for database sync cleanup on failures."""
import store


def test_sync_failure_always_releases_syncing_flag(monkeypatch, tmp_path):
    manager = store.DatabaseSyncManager({"network_db_path": str(tmp_path / "backup.db")})
    monkeypatch.setattr(store, "get_local_db_path", lambda: (_ for _ in ()).throw(RuntimeError("simulated local DB failure")))
    result = manager.sync_now()
    assert result["ok"] is False
    assert "simulated local DB failure" in result["error"]
    assert manager.is_syncing is False
