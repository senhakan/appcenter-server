from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import AuditLog
from app.services.ws_manager import ws_manager


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


def _tiny_png_bytes() -> bytes:
    # 1x1 transparent PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02"
        b"\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )


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


def test_settings_broadcast_self_update_supports_mode(client: TestClient, auth_headers: dict[str, str]) -> None:
    agent_uuid = 'agent-broadcast-safe-1'
    agent_headers = _register_agent(client, uuid=agent_uuid)
    hb = client.post(
        '/api/v1/agent/heartbeat',
        headers=agent_headers,
        json={'hostname': 'PC-BROADCAST', 'apps_changed': False, 'installed_apps': []},
    )
    assert hb.status_code == 200

    sent: list[tuple[str, dict]] = []
    old_agents = dict(ws_manager._agents)  # pylint: disable=protected-access
    old_schedule = ws_manager.schedule_send_to_agent
    try:
        ws_manager._agents.clear()  # pylint: disable=protected-access
        ws_manager._agents[agent_uuid] = object()  # pylint: disable=protected-access

        def _capture(uuid: str, message: dict) -> None:
            sent.append((uuid, message))

        ws_manager.schedule_send_to_agent = _capture  # type: ignore[assignment]

        resp = client.post(
            '/api/v1/settings/agents/broadcast',
            headers=auth_headers,
            json={'action': 'self_update', 'mode': 'force'},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data['targeted'] == 1
        assert "mode=force" in data['message']
        assert sent and sent[0][0] == agent_uuid
        assert sent[0][1]['type'] == 'server.broadcast.self_update'
        assert sent[0][1]['payload']['mode'] == 'force'

        restart_resp = client.post(
            '/api/v1/settings/agents/broadcast',
            headers=auth_headers,
            json={'action': 'restart'},
        )
        assert restart_resp.status_code == 422
    finally:
        ws_manager._agents.clear()  # pylint: disable=protected-access
        ws_manager._agents.update(old_agents)  # pylint: disable=protected-access
        ws_manager.schedule_send_to_agent = old_schedule


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


def test_agent_store_install_request_enqueues_command(client: TestClient, auth_headers: dict[str, str]) -> None:
    app_id = _upload_application(client, auth_headers, name='Store Install App')
    agent_headers = _register_agent(client, uuid='agent-store-install-1')

    install_req = client.post(f'/api/v1/agent/store/{app_id}/install', headers=agent_headers)
    assert install_req.status_code == 200
    assert install_req.json()['status'] == 'queued'

    hb = client.post(
        '/api/v1/agent/heartbeat',
        headers=agent_headers,
        json={'hostname': 'PC-STORE-INSTALL', 'apps_changed': False, 'installed_apps': []},
    )
    assert hb.status_code == 200
    commands = hb.json()['commands']
    assert any(c['app_id'] == app_id and c['action'] == 'install' for c in commands)

    # Idempotency: repeated click while task in-progress should not duplicate queue.
    install_req_2 = client.post(f'/api/v1/agent/store/{app_id}/install', headers=agent_headers)
    assert install_req_2.status_code == 200
    assert install_req_2.json()['status'] in {'already_queued', 'already_installed', 'queued'}


def test_deployment_task_assignment_and_status(client: TestClient, auth_headers: dict[str, str]) -> None:
    payload = {
        'display_name': 'Task App',
        'version': '1.0.0',
        'install_args': '/qn /norestart',
    }
    files = {'file': ('task.msi', b'abc123' * 1500, 'application/octet-stream')}
    upload = client.post('/api/v1/applications', headers=auth_headers, data=payload, files=files)
    assert upload.status_code == 200
    app_id = upload.json()['id']
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
    assert commands[0]['install_args'] == '/qn /norestart'

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


def test_store_does_not_mark_downloading_as_installed(client: TestClient, auth_headers: dict[str, str]) -> None:
    app_id = _upload_application(client, auth_headers, name='Store Downloading Visibility App')
    agent_headers = _register_agent(client, uuid='agent-store-downloading-1')

    deployment = client.post(
        '/api/v1/deployments',
        headers=auth_headers,
        json={
            'app_id': app_id,
            'target_type': 'Agent',
            'target_id': 'agent-store-downloading-1',
            'is_active': True,
            'priority': 5,
        },
    )
    assert deployment.status_code == 200

    hb = client.post(
        '/api/v1/agent/heartbeat',
        headers=agent_headers,
        json={'hostname': 'PC-STORE-DOWNLOAD', 'apps_changed': False, 'installed_apps': []},
    )
    assert hb.status_code == 200
    assert len(hb.json()['commands']) == 1

    store = client.get('/api/v1/agent/store', headers=agent_headers)
    assert store.status_code == 200
    rows = [a for a in store.json()['apps'] if a['id'] == app_id]
    assert len(rows) == 1
    assert rows[0]['installed'] is False
    assert rows[0]['install_state'] == 'downloading'


def test_api_error_shape_for_unauthorized(client: TestClient) -> None:
    unauthorized = client.get('/api/v1/settings')
    assert unauthorized.status_code == 401
    payload = unauthorized.json()
    assert payload['status'] == 'error'
    assert 'detail' in payload


def test_upload_with_icon_and_args_visible_in_store(client: TestClient, auth_headers: dict[str, str]) -> None:
    payload = {
        'display_name': '7Zip',
        'version': '23.01',
        'install_args': '/S',
        'uninstall_args': '/uninstall /quiet',
        'category': 'Utilities',
    }
    files = {
        'file': ('7zip.msi', b'payload' * 2000, 'application/octet-stream'),
        'icon': ('7zip.png', _tiny_png_bytes(), 'image/png'),
    }
    upload = client.post('/api/v1/applications', headers=auth_headers, data=payload, files=files)
    assert upload.status_code == 200
    app_data = upload.json()
    assert app_data['install_args'] == '/S'
    assert app_data['uninstall_args'] == '/uninstall /quiet'
    assert app_data['icon_url'].startswith('/uploads/icons/')

    agent_headers = _register_agent(client, uuid='agent-store-icon-1')
    store = client.get('/api/v1/agent/store', headers=agent_headers)
    assert store.status_code == 200
    matched = [app for app in store.json()['apps'] if app['id'] == app_data['id']]
    assert len(matched) == 1
    assert matched[0]['icon_url'] == app_data['icon_url']


def test_application_name_must_be_unique_case_insensitive(client: TestClient, auth_headers: dict[str, str]) -> None:
    first = client.post(
        '/api/v1/applications',
        headers=auth_headers,
        data={'display_name': '7Zip Unique', 'version': '1.0.0'},
        files={'file': ('first.msi', b'a' * 4096, 'application/octet-stream')},
    )
    assert first.status_code == 200

    dup = client.post(
        '/api/v1/applications',
        headers=auth_headers,
        data={'display_name': '  7zip unique  ', 'version': '2.0.0'},
        files={'file': ('second.msi', b'b' * 4096, 'application/octet-stream')},
    )
    assert dup.status_code == 409
    assert dup.json()['detail'] == 'Application name already exists'


def test_group_management_and_group_target_deployment(client: TestClient, auth_headers: dict[str, str]) -> None:
    app_id = _upload_application(client, auth_headers, name='Group Target App')
    agent_headers = _register_agent(client, uuid='agent-group-1')

    grp = client.post(
        '/api/v1/groups',
        headers=auth_headers,
        json={'name': 'Pilot Group', 'description': 'Test group'},
    )
    assert grp.status_code == 200
    group_id = grp.json()['id']

    assign = client.put(
        f'/api/v1/groups/{group_id}/agents',
        headers=auth_headers,
        json={'agent_uuids': ['agent-group-1']},
    )
    assert assign.status_code == 200

    deployment = client.post(
        '/api/v1/deployments',
        headers=auth_headers,
        json={
            'app_id': app_id,
            'target_type': 'Group',
            'target_id': str(group_id),
            'is_active': True,
            'priority': 5,
        },
    )
    assert deployment.status_code == 200

    hb = client.post(
        '/api/v1/agent/heartbeat',
        headers=agent_headers,
        json={'hostname': 'PC-GROUP', 'apps_changed': False, 'installed_apps': []},
    )
    assert hb.status_code == 200
    assert len(hb.json()['commands']) >= 1


def test_edit_endpoints_for_app_group_deployment(client: TestClient, auth_headers: dict[str, str]) -> None:
    app_id = _upload_application(client, auth_headers, name='Editable App')
    _register_agent(client, uuid='agent-edit-1')

    group = client.post('/api/v1/groups', headers=auth_headers, json={'name': 'Editable Group'})
    assert group.status_code == 200
    group_id = group.json()['id']

    app_update = client.put(
        f'/api/v1/applications/{app_id}',
        headers=auth_headers,
        json={'display_name': 'Editable App Renamed', 'install_args': '/S', 'category': 'Tools'},
    )
    assert app_update.status_code == 200
    assert app_update.json()['display_name'] == 'Editable App Renamed'
    assert app_update.json()['install_args'] == '/S'

    group_update = client.put(
        f'/api/v1/groups/{group_id}',
        headers=auth_headers,
        json={'name': 'Editable Group Renamed', 'description': 'Updated'},
    )
    assert group_update.status_code == 200
    assert group_update.json()['name'] == 'Editable Group Renamed'

    assign = client.put(
        f'/api/v1/groups/{group_id}/agents',
        headers=auth_headers,
        json={'agent_uuids': ['agent-edit-1']},
    )
    assert assign.status_code == 200

    dep = client.post(
        '/api/v1/deployments',
        headers=auth_headers,
        json={
            'app_id': app_id,
            'target_type': 'Group',
            'target_id': str(group_id),
            'priority': 3,
            'is_active': True,
        },
    )
    assert dep.status_code == 200
    dep_id = dep.json()['id']

    dep_update = client.put(
        f'/api/v1/deployments/{dep_id}',
        headers=auth_headers,
        json={
            'target_type': 'Agent',
            'target_id': 'agent-edit-1',
            'priority': 8,
            'is_mandatory': True,
        },
    )
    assert dep_update.status_code == 200
    assert dep_update.json()['target_type'] == 'Agent'
    assert dep_update.json()['target_id'] == 'agent-edit-1'
    assert dep_update.json()['priority'] == 8


def test_group_delete_is_soft_and_hidden_from_default_list(client: TestClient, auth_headers: dict[str, str]) -> None:
    grp = client.post('/api/v1/groups', headers=auth_headers, json={'name': 'Soft Delete Group'})
    assert grp.status_code == 200
    group_id = grp.json()['id']

    deleted = client.delete(f'/api/v1/groups/{group_id}', headers=auth_headers)
    assert deleted.status_code == 200
    assert deleted.json()['message'] == 'Group set to inactive'

    active_list = client.get('/api/v1/groups', headers=auth_headers)
    assert active_list.status_code == 200
    active_ids = {g['id'] for g in active_list.json()['items']}
    assert group_id not in active_ids

    all_list = client.get('/api/v1/groups?include_inactive=true', headers=auth_headers)
    assert all_list.status_code == 200
    matched = [g for g in all_list.json()['items'] if g['id'] == group_id]
    assert len(matched) == 1
    assert matched[0]['is_active'] is False


def test_application_icon_update_and_remove(client: TestClient, auth_headers: dict[str, str]) -> None:
    app_id = _upload_application(client, auth_headers, name='Icon Update App')

    update_icon = client.put(
        f'/api/v1/applications/{app_id}/icon',
        headers=auth_headers,
        files={'icon': ('icon.png', _tiny_png_bytes(), 'image/png')},
    )
    assert update_icon.status_code == 200
    assert (update_icon.json().get('icon_url') or '').startswith('/uploads/icons/')

    remove_icon = client.delete(f'/api/v1/applications/{app_id}/icon', headers=auth_headers)
    assert remove_icon.status_code == 200
    assert remove_icon.json()['icon_url'] is None


def test_audit_log_written_for_mutating_actions(client: TestClient, auth_headers: dict[str, str]) -> None:
    grp = client.post('/api/v1/groups', headers=auth_headers, json={'name': 'Audit Group'})
    assert grp.status_code == 200
    gid = grp.json()['id']

    upd = client.put(
        f'/api/v1/groups/{gid}',
        headers=auth_headers,
        json={'description': 'audit-check'},
    )
    assert upd.status_code == 200

    del_resp = client.delete(f'/api/v1/groups/{gid}', headers=auth_headers)
    assert del_resp.status_code == 200

    db_url = os.environ.get('DATABASE_URL', '')
    assert db_url.startswith('postgresql+psycopg2://')
    db = SessionLocal()
    try:
        rows = (
            db.query(AuditLog.action)
            .filter(AuditLog.resource_type == 'group', AuditLog.resource_id == str(gid))
            .all()
        )
    finally:
        db.close()
    actions = {r[0] for r in rows}
    assert 'group.create' in actions
    assert 'group.update' in actions
    assert 'group.deactivate' in actions


def test_agent_can_belong_to_multiple_groups(client: TestClient, auth_headers: dict[str, str]) -> None:
    agent_headers = _register_agent(client, uuid='agent-multi-group-1')

    g1 = client.post('/api/v1/groups', headers=auth_headers, json={'name': 'MG-Group-1'})
    g2 = client.post('/api/v1/groups', headers=auth_headers, json={'name': 'MG-Group-2'})
    assert g1.status_code == 200
    assert g2.status_code == 200
    g1_id = g1.json()['id']
    g2_id = g2.json()['id']

    a1 = client.put(
        f'/api/v1/groups/{g1_id}/agents',
        headers=auth_headers,
        json={'agent_uuids': ['agent-multi-group-1']},
    )
    a2 = client.put(
        f'/api/v1/groups/{g2_id}/agents',
        headers=auth_headers,
        json={'agent_uuids': ['agent-multi-group-1']},
    )
    assert a1.status_code == 200
    assert a2.status_code == 200

    agent_detail = client.get('/api/v1/agents/agent-multi-group-1', headers=auth_headers)
    assert agent_detail.status_code == 200
    gids = set(agent_detail.json().get('group_ids', []))
    assert g1_id in gids
    assert g2_id in gids

    app1 = _upload_application(client, auth_headers, name='MG App 1')
    app2 = _upload_application(client, auth_headers, name='MG App 2')

    d1 = client.post(
        '/api/v1/deployments',
        headers=auth_headers,
        json={'app_id': app1, 'target_type': 'Group', 'target_id': str(g1_id), 'is_active': True},
    )
    d2 = client.post(
        '/api/v1/deployments',
        headers=auth_headers,
        json={'app_id': app2, 'target_type': 'Group', 'target_id': str(g2_id), 'is_active': True},
    )
    assert d1.status_code == 200
    assert d2.status_code == 200

    hb = client.post(
        '/api/v1/agent/heartbeat',
        headers=agent_headers,
        json={'hostname': 'PC-MULTI', 'apps_changed': False, 'installed_apps': []},
    )
    assert hb.status_code == 200
    cmd_app_ids = {c.get('app_id') for c in hb.json().get('commands', [])}
    assert app1 in cmd_app_ids
    assert app2 in cmd_app_ids


def test_agent_register_accepts_platform_metadata(client: TestClient, auth_headers: dict[str, str]) -> None:
    reg = client.post(
        '/api/v1/agent/register',
        json={
            'uuid': 'agent-linux-meta-1',
            'hostname': 'LNX-01',
            'platform': 'linux',
            'arch': 'amd64',
            'distro': 'ubuntu',
            'distro_version': '24.04',
            'agent_version': '2.0.0',
        },
    )
    assert reg.status_code == 200
    details = client.get('/api/v1/agents/agent-linux-meta-1', headers=auth_headers)
    assert details.status_code == 200
    data = details.json()
    assert data['platform'] == 'linux'
    assert data['arch'] == 'amd64'
    assert data['distro'] == 'ubuntu'
    assert data['distro_version'] == '24.04'


def test_heartbeat_updates_common_agent_metadata(client: TestClient, auth_headers: dict[str, str]) -> None:
    agent_headers = _register_agent(client, uuid='agent-common-meta-1')

    hb = client.post(
        '/api/v1/agent/heartbeat',
        headers=agent_headers,
        json={
            'hostname': 'PC-COMMON',
            'platform': 'windows',
            'os_user': 'DOMAIN\\user1',
            'os_version': 'Windows 11 Pro',
            'arch': 'amd64',
            'distro': 'windows',
            'distro_version': '11',
            'cpu_model': 'Intel(R) Core(TM) i7',
            'ram_gb': 16,
            'disk_free_gb': 245,
            'apps_changed': False,
            'installed_apps': [],
        },
    )
    assert hb.status_code == 200

    details = client.get('/api/v1/agents/agent-common-meta-1', headers=auth_headers)
    assert details.status_code == 200
    data = details.json()
    assert data['platform'] == 'windows'
    assert data['os_user'] == 'DOMAIN\\user1'
    assert data['os_version'] == 'Windows 11 Pro'
    assert data['arch'] == 'amd64'
    assert data['distro'] == 'windows'
    assert data['distro_version'] == '11'
    assert data['cpu_model'] == 'Intel(R) Core(TM) i7'
    assert data['ram_gb'] == 16
    assert data['disk_free_gb'] == 245


def test_store_is_filtered_by_agent_platform(client: TestClient, auth_headers: dict[str, str]) -> None:
    win_upload = client.post(
        '/api/v1/applications',
        headers=auth_headers,
        data={'display_name': 'Platform Win App', 'version': '1.0.0', 'target_platform': 'windows'},
        files={'file': ('plat_win.msi', b'w' * 4096, 'application/octet-stream')},
    )
    assert win_upload.status_code == 200
    win_id = win_upload.json()['id']

    linux_upload = client.post(
        '/api/v1/applications',
        headers=auth_headers,
        data={'display_name': 'Platform Linux App', 'version': '1.0.0', 'target_platform': 'linux'},
        files={'file': ('plat_linux.deb', b'l' * 4096, 'application/octet-stream')},
    )
    assert linux_upload.status_code == 200
    linux_id = linux_upload.json()['id']

    win_headers = _register_agent(client, uuid='agent-win-store-1')
    linux_reg = client.post(
        '/api/v1/agent/register',
        json={'uuid': 'agent-linux-store-1', 'hostname': 'LNX-STORE', 'platform': 'linux', 'agent_version': '2.0.0'},
    )
    assert linux_reg.status_code == 200
    linux_headers = {'X-Agent-UUID': 'agent-linux-store-1', 'X-Agent-Secret': linux_reg.json()['secret_key']}

    win_store = client.get('/api/v1/agent/store', headers=win_headers)
    assert win_store.status_code == 200
    win_ids = {row['id'] for row in win_store.json()['apps']}
    assert win_id in win_ids
    assert linux_id not in win_ids

    linux_store = client.get('/api/v1/agent/store', headers=linux_headers)
    assert linux_store.status_code == 200
    linux_ids = {row['id'] for row in linux_store.json()['apps']}
    assert linux_id in linux_ids
    assert win_id not in linux_ids


def test_heartbeat_uses_platform_specific_update_settings(client: TestClient, auth_headers: dict[str, str]) -> None:
    win_up = client.post(
        '/api/v1/agent-update/upload',
        headers=auth_headers,
        data={'version': '9.9.9', 'platform': 'windows'},
        files={'file': ('agent_win.exe', b'win' * 3000, 'application/octet-stream')},
    )
    assert win_up.status_code == 200
    linux_up = client.post(
        '/api/v1/agent-update/upload',
        headers=auth_headers,
        data={'version': '2.2.2', 'platform': 'linux'},
        files={'file': ('agent_linux.deb', b'lnx' * 3000, 'application/octet-stream')},
    )
    assert linux_up.status_code == 200

    win_headers = _register_agent(client, uuid='agent-win-upd-1')
    linux_reg = client.post(
        '/api/v1/agent/register',
        json={'uuid': 'agent-linux-upd-1', 'hostname': 'LNX-UPD', 'platform': 'linux', 'agent_version': '2.0.0'},
    )
    assert linux_reg.status_code == 200
    linux_headers = {'X-Agent-UUID': 'agent-linux-upd-1', 'X-Agent-Secret': linux_reg.json()['secret_key']}

    win_hb = client.post(
        '/api/v1/agent/heartbeat',
        headers=win_headers,
        json={'hostname': 'WIN-UPD', 'apps_changed': False, 'installed_apps': []},
    )
    assert win_hb.status_code == 200
    assert win_hb.json()['config']['latest_agent_version'] == '9.9.9'

    linux_hb = client.post(
        '/api/v1/agent/heartbeat',
        headers=linux_headers,
        json={'hostname': 'LNX-UPD', 'platform': 'linux', 'apps_changed': False, 'installed_apps': []},
    )
    assert linux_hb.status_code == 200
    assert linux_hb.json()['config']['latest_agent_version'] == '2.2.2'


def test_download_rejects_platform_mismatch(client: TestClient, auth_headers: dict[str, str]) -> None:
    linux_upload = client.post(
        '/api/v1/applications',
        headers=auth_headers,
        data={'display_name': 'Linux Download Guard', 'version': '1.0.0', 'target_platform': 'linux'},
        files={'file': ('dl_guard.deb', b'abc' * 4096, 'application/octet-stream')},
    )
    assert linux_upload.status_code == 200
    linux_app_id = linux_upload.json()['id']

    win_headers = _register_agent(client, uuid='agent-win-dl-guard-1')
    denied = client.get(f'/api/v1/agent/download/{linux_app_id}', headers=win_headers)
    assert denied.status_code == 403
