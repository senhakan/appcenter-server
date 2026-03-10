# Guacamole Re-enable Rehberi

Bu dizin, Guacamole entegrasyonunu tekrar devreye almak icin tek referans noktasi olarak tutulur.

## 1. Container'lari Ac

```bash
cd /root/appcenter/server/config/guacamole
docker compose -f docker-compose.guacamole.yml up -d
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Beklenen:
- `guacd`
- `guacamole`
- `guac-db`

## 2. Nginx Entegrasyonu

`nginx.guacamole.conf.snippet` icerigi ana vhost icine eklenir:
- hedef: `/etc/nginx/custom-conf/appcenter.akgun.com.tr.conf`

Sonra:
```bash
nginx -t && sudo systemctl reload nginx
```

## 3. Server Bootstrap Config

`server/config/server.ini` veya canlida `/opt/appcenter/server/config/server.ini`
icinde guncellenecek alanlar:

```ini
[remote_support]
guac_reverse_vnc_host = appcenter.akgun.com.tr
guac_reverse_vnc_port = 4822
```

## 4. Kod Entegrasyonu (ornek)

Not: Asagidaki bloklar geri alma icin referans ornektir; birebir kopyala-yapistir yerine mevcut kod tabanina gore uyarlayin.

### 4.1 Service katmani (`app/services/guacamole_service.py`)

```python
from dataclasses import dataclass
import httpx

@dataclass
class GuacViewerTicket:
    token: str
    data_source: str
    connection_id: str
    connection_type: str = "c"

def build_viewer_ticket(session, agent_ip: str) -> GuacViewerTicket:
    # 1) /api/tokens ile login
    # 2) connection upsert (name = appcenter-rs-<session_id>)
    # 3) ticket bilgisi don
    ...
```

### 4.2 API endpoint (`app/api/v1/remote_support.py`)

```python
@router.get("/remote-support/sessions/{session_id}/viewer-ticket")
def get_remote_session_viewer_ticket(session_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    s = rs.get_session(db, session_id)
    ticket = guac.build_viewer_ticket(s, agent_ip="10.0.0.10")
    return {
        "status": "ok",
        "viewer": {
            "enabled": True,
            "tunnel_path": "/guacamole/websocket-tunnel",
            "token": ticket.token,
            "data_source": ticket.data_source,
            "connection_id": ticket.connection_id,
            "connection_type": ticket.connection_type,
        },
    }
```

### 4.3 Viewer UI (`app/templates/remote_support/session.html`)

```html
<script src="/guacamole/guacamole-common-js/all.min.js"></script>
<script>
  // /viewer-ticket endpoint'inden token alip
  // Guacamole.WebSocketTunnel ile baglan
</script>
```

## 5. Hizli Dogrulama

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/guacamole/
curl -sS -H 'Host: appcenter.akgun.com.tr' -o /dev/null -w '%{http_code}\n' http://127.0.0.1/guacamole/
docker logs --tail 50 guacamole
docker logs --tail 50 guacd
```
