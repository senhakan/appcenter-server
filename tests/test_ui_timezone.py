from __future__ import annotations


def test_settings_ui_timezone_validation(client, auth_headers):
    # Valid IANA timezone
    ok = client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={"values": {"ui_timezone": "Europe/Istanbul"}},
    )
    assert ok.status_code == 200, ok.text

    # Invalid timezone should be rejected
    bad = client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={"values": {"ui_timezone": "Not/AZone"}},
    )
    assert bad.status_code == 400, bad.text

