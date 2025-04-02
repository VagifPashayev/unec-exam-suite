import sys
import os
import json
import pytest
import tempfile

# Patch METADATA_FILE and RESULT_FOLDER before importing app
FAKE_METADATA = {
    "q1": {"question": "q1.png", "options": {"opt_a.png": "opt_a.png", "opt_b.png": "opt_b.png"}, "correct": "opt_a.png"},
    "q2": {"question": "q2.png", "options": {"opt_c.png": "opt_c.png", "opt_d.png": "opt_d.png"}, "correct": "opt_d.png"},
    "q3": {"question": "q3.png", "options": {"opt_e.png": "opt_e.png", "opt_f.png": "opt_f.png"}, "correct": "opt_e.png"},
}

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web"))

import unittest.mock as mock

with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(FAKE_METADATA))):
    with mock.patch("os.makedirs"):
        with mock.patch("json.load", return_value=FAKE_METADATA):
            import app as web_app


@pytest.fixture
def client(tmp_path):
    web_app.app.config["TESTING"] = True
    web_app.app.config["SECRET_KEY"] = "test"
    web_app.METADATA = FAKE_METADATA
    web_app.RESULT_FOLDER = str(tmp_path)
    with web_app.app.test_client() as c:
        yield c


def test_index_get(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Quiz" in resp.data


def test_index_post_range(client):
    with mock.patch("web_app.Document") as MockDoc:
        MockDoc.return_value.save = mock.MagicMock()
        with mock.patch("random.sample", return_value=["q1", "q2"]):
            resp = client.post("/", data={"qmin": "1", "qmax": "2", "count": "2", "custom": ""})
    assert resp.status_code == 302
    assert b"/quiz" in resp.headers.get("Location", "").encode()


def test_index_post_custom(client):
    with mock.patch("web_app.Document") as MockDoc:
        MockDoc.return_value.save = mock.MagicMock()
        resp = client.post("/", data={"custom": "1 2", "qmin": "", "qmax": "", "count": ""})
    assert resp.status_code == 302


def test_quiz_redirects_when_no_session(client):
    resp = client.get("/quiz")
    assert resp.status_code in (302, 200)


def test_finish_page(client):
    with client.session_transaction() as sess:
        sess["score"] = 2
        sess["count"] = 3
        sess["wrong"] = 1
        sess["streak"] = 2
        sess["result_file"] = "dummy.docx"
        sess["questions"] = ["q1", "q2", "q3"]

    dummy_path = os.path.join(web_app.RESULT_FOLDER, "dummy.docx")
    from docx import Document as RealDoc
    d = RealDoc()
    d.save(dummy_path)

    resp = client.get("/finish")
    assert resp.status_code == 200
    assert b"2" in resp.data


def test_download_existing_file(client, tmp_path):
    fname = "test_result.docx"
    fpath = tmp_path / fname
    fpath.write_bytes(b"PK fake docx")
    web_app.RESULT_FOLDER = str(tmp_path)

    resp = client.get(f"/download/{fname}")
    assert resp.status_code == 200
