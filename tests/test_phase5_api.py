from __future__ import annotations

from fastapi.testclient import TestClient


def _register_agent(client: TestClient, uuid: str = 'agent-test-1') -> dict[str, str]:
    reg = client.post(
        '/api/v1/agent/register',
        json={'uuid': uuid, 'hostname': 'PC-TEST', 'agent_version': '1.0.0'},
    )
    assert reg.status_code == 200
    secret = reg.json()['secret_key']
    return {'X-Agent-UUID': uuid, 'X-Agent-Secret': secret}


def _upload_application(client: TestClient, auth_headers: dict[str, str], name: str = 'Demo App') -> int:
    payload = {'display_name': name, 'version': '1.0.0'}
    files = {'file': ('demo.msi', b'abc123' * 1500, 'application/octet-stream')}
    upload = client.post('/api/v1/applications', headers=auth_headers, data=payload, files=files)
    assert upload.status_code == 200
    return upload.json()['id']


def test_dashboard_stats_and_settings(client: TestClient, auth_headers: dict[str, str]) -> None:
    stats = client.get('/api/v1/dashboard/stats', headers=auth_headers)
    assert stats.status_code == 200
    data = stats.json()
    assert 'total_agents' in data
    assert 'online_agents' in data
    assert 'active_deployments' in data

    settings = client.get('/api/v1/settings', headers=auth_headers)
    assert settings.status_code == 200
    assert settings.json()['total'] >= 10

    updated = client.put(
        '/api/v1/settings',
        headers=auth_headers,
        json={'values': {'heartbeat_interval_sec': '45', 'bandwidth_limit_kbps': '2048'}},
    )
    assert updated.status_code == 200

    settings_after = client.get('/api/v1/settings', headers=auth_headers)
    items = {x['key']: x['value'] for x in settings_after.json()['items']}
    assert items['heartbeat_interval_sec'] == '45'
    assert items['bandwidth_limit_kbps'] == '2048'


def test_agent_store_and_update_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    app_id = _upload_application(client, auth_headers, name='Store App')
    agent_headers = _register_agent(client, uuid='agent-store-1')

    store = client.get('/api/v1/agent/store', headers=agent_headers)
    assert store.status_code == 200
    store_apps = store.json()['apps']
    assert any(a['id'] == app_id for a in store_apps)

    update_upload = client.post(
        '/api/v1/agent-update/upload',
        headers=auth_headers,
        data={'version': '1.2.3'},
        files={'file': ('agent_installer.exe', b'xyz' * 4000, 'application/octet-stream')},
    )
    assert update_upload.status_code == 200
    update_info = update_upload.json()
    assert update_info['version'] == '1.2.3'
    assert update_info['download_url'].startswith('/api/v1/agent/update/download/')

    heartbeat = client.post(
        '/api/v1/agent/heartbeat',
        headers=agent_headers,
        json={'hostname': 'PC-STORE', 'apps_changed': False, 'installed_apps': []},
    )
    assert heartbeat.status_code == 200
    hb_cfg = heartbeat.json()['config']
    assert hb_cfg['latest_agent_version'] == '1.2.3'
    assert hb_cfg['agent_download_url']
    assert hb_cfg['agent_hash']

    update_download = client.get(update_info['download_url'], headers=agent_headers)
    assert update_download.status_code == 200
    assert len(update_download.content) > 0


def test_deployment_task_assignment_and_status(client: TestClient, auth_headers: dict[str, str]) -> None:
    app_id = _upload_application(client, auth_headers, name='Task App')
    agent_headers = _register_agent(client, uuid='agent-task-1')

    deployment = client.post(
        '/api/v1/deployments',
        headers=auth_headers,
        json={
            'app_id': app_id,
            'target_type': 'Agent',
            'target_id': 'agent-task-1',
            'is_active': True,
            'priority': 7,
        },
    )
    assert deployment.status_code == 200

    hb1 = client.post(
        '/api/v1/agent/heartbeat',
        headers=agent_headers,
        json={'hostname': 'PC-TASK', 'apps_changed': False, 'installed_apps': []},
    )
    assert hb1.status_code == 200
    commands = hb1.json()['commands']
    assert len(commands) == 1
    task_id = commands[0]['task_id']

    hb2 = client.post(
        '/api/v1/agent/heartbeat',
        headers=agent_headers,
        json={'hostname': 'PC-TASK', 'apps_changed': False, 'installed_apps': []},
    )
    assert hb2.status_code == 200
    assert len(hb2.json()['commands']) == 0

    status_update = client.post(
        f'/api/v1/agent/task/{task_id}/status',
        headers=agent_headers,
        json={
            'status': 'success',
            'progress': 100,
            'message': 'Installation completed',
            'exit_code': 0,
            'installed_version': '1.0.0',
        },
    )
    assert status_update.status_code == 200
    assert status_update.json()['status'] == 'ok'


def test_api_error_shape_for_unauthorized(client: TestClient) -> None:
    unauthorized = client.get('/api/v1/settings')
    assert unauthorized.status_code == 401
    payload = unauthorized.json()
    assert payload['status'] == 'error'
    assert 'detail' in payload
