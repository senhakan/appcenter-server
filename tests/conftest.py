from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_ROOT = Path('/tmp/appcenter_pytest')
TEST_DB = TEST_ROOT / 'test.db'
TEST_UPLOADS = TEST_ROOT / 'uploads'
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

shutil.rmtree(TEST_ROOT, ignore_errors=True)
TEST_ROOT.mkdir(parents=True, exist_ok=True)
TEST_UPLOADS.mkdir(parents=True, exist_ok=True)

os.environ['DATABASE_URL'] = f"sqlite:////{TEST_DB.as_posix().lstrip('/')}"
os.environ['UPLOAD_DIR'] = str(TEST_UPLOADS)

from app.main import app  # noqa: E402  pylint: disable=wrong-import-position


@pytest.fixture(scope='session')
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope='session')
def auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'})
    assert login.status_code == 200
    token = login.json()['access_token']
    return {'Authorization': f'Bearer {token}'}
