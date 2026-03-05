from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_windows_ps1_upload_allowed_and_linux_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    ps1_name = f"PS1 App {uuid.uuid4()}"
    upload = client.post(
        "/api/v1/applications",
        headers=auth_headers,
        data={"display_name": ps1_name, "version": "1.0.0", "target_platform": "windows"},
        files={"file": ("install.ps1", b"Write-Output 'ok'\n", "text/plain")},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["file_type"] == "ps1"
    assert body["target_platform"] == "windows"

    wrong_platform_name = f"PS1 Linux Block {uuid.uuid4()}"
    blocked = client.post(
        "/api/v1/applications",
        headers=auth_headers,
        data={"display_name": wrong_platform_name, "version": "1.0.0", "target_platform": "linux"},
        files={"file": ("install.ps1", b"echo ok\n", "text/plain")},
    )
    assert blocked.status_code == 400
