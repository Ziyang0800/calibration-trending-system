"""Rules tests: no browser needed.  python tests/run_all.py"""
import os, sys, json, tempfile
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logic
from harness import load_pack_module
ecal, ECAL_DIR = load_pack_module("ecal")


def rec(days, where="INU"):
    return {"Model_No": "X", "Serial_No": "S", "Current_Whereabout": where,
            "Cal_Due_Date_ISO": (date.today() + timedelta(days=days)).isoformat() + "T10:00:00"}


def test_valid():
    assert logic.evaluate("A", rec(200))["status"] == "Valid"

def test_expiring_still_valid():
    r = logic.evaluate("A", rec(30)); assert r["status"] == "Expiring Soon" and r["valid"]

def test_yesterday_is_expired():
    r = logic.evaluate("A", rec(-1)); assert r["status"] == "Expired" and not r["valid"]

def test_sent_for_cal():
    assert logic.evaluate("A", rec(200, "RCV"))["status"] == "Sent for Cal"

def test_not_in_use():
    assert logic.evaluate("A", rec(200, "XYZ"))["status"] == "Not in use"

def test_not_found():
    assert logic.evaluate("A", None)["status"] == "Not found"

def test_catalog_validation():
    good = json.load(open(os.path.join(ECAL_DIR, "ecal_catalog.json")))
    assert ecal.validate_catalog(good) == ""
    assert ecal.validate_catalog([]) != ""
    bad = json.loads(json.dumps(good)); next(iter(bad["models"].values()))["modules"].append("NOPE")
    assert "NOPE" in ecal.validate_catalog(bad)
    bad = json.loads(json.dumps(good)); del bad["connectors"]
    assert "connectors" in ecal.validate_catalog(bad)

def test_broken_local_catalog_is_reported():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "ecal_catalog.json"), "w").write('{"models": {')
    cat, err = ecal.load_catalog(d, ECAL_DIR)
    assert cat["models"] and "mistake" in err
    os.remove(os.path.join(d, "ecal_catalog.json"))
    assert ecal.load_catalog(d, ECAL_DIR)[1] == ""
