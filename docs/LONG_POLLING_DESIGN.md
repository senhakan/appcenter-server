# Agent Long Polling Sinyal Mekanizmasi - Tasarim Dokumani

**Tarih:** 2026-02-26
**Durum:** Karar Bekleniyor
**Ilgili:** Remote Support hizli iletim, genel agent sinyal altyapisi

---

## 1. Problem Tanimi

Uzak destek oturumu olusturuldugunda istek agent'a heartbeat response ile iletiliyor. Heartbeat 60sn aralikla calistigindan, admin "Baglan" dediginde agent'a iletim **0-60sn** gecikebiliyor.

**Hedef:** 1-2sn gecikme, minimum altyapi degisikligi, minimum sistem yuku.

### Neden Heartbeat Suresini Kisaltmak Cozum Degil

| Heartbeat Suresi | 500 Agent Trafigi | Yillik HTTP Istek |
|------------------|-------------------|-------------------|
| 60sn (mevcut) | ~8.3 req/sn | ~262M |
| 10sn | ~50 req/sn | ~1.58B |
| 2sn | ~250 req/sn | ~7.9B |

Her heartbeat'te DB sorgusu, JSON serialize/deserialize ve agent state guncelleme yapildigi icin 2sn'ye dusurmek sunucu CPU ve PostgreSQL yuku acisindan kabul edilemez.

---

## 2. Alternatif Cozumlerin Karsilastirmasi

| Kriter | Long Polling | SSE | WebSocket | Kisa Aralikli Poll |
|--------|-------------|-----|-----------|-------------------|
| Gecikme | <1sn | <1sn | <100ms | 0-N sn |
| Server karmasikligi | Dusuk | Orta | Yuksek | Sifir |
| Agent karmasikligi | Dusuk | Orta (Go SSE client) | Yuksek (WS kutuphanesi) | Sifir |
| Yeni bagimllik | Yok (asyncio stdlib) | Yok | Agent: gorilla/websocket | Yok |
| Proxy/firewall uyumu | Mukemmel (standart HTTP) | Iyi (bazi proxy sorunlu) | Sorunlu olabilir | Mukemmel |
| Nginx config degisikligi | Yok* | Yok | Upgrade header gerekir | Yok |
| Auth mekanizmasi | Mevcut header auth | Mevcut header auth | Handshake + token | Mevcut header auth |
| Cift yonlu veri | Hayir | Hayir | Evet | Hayir |
| Idle kaynak kullanimi | 1 coroutine + 1 TCP soketi/agent | 1 coroutine + 1 TCP soketi/agent | 1 coroutine + 1 TCP soketi/agent | Yok |
| Online tespit | Evet (baglanti durumu) | Evet | Evet | Hayir (mevcut 2dk) |

*Not: Nginx varsayilan `proxy_read_timeout` 60sn, long poll timeout 55sn ile uyumlu.

**Secilen yaklasim: Long Polling** — Sifir yeni bagimllik, minimum kod, mevcut HTTP altyapisina tam uyumlu.

---

## 3. Mimari Tasarim

### 3.1 Genel Akis

```
Agent baslatildiginda:
  1. Normal heartbeat baslar (60sn aralik, mevcut davranis)
  2. SignalListener goroutine baslar:
     GET /api/v1/agent/signal?timeout=55
     ├── Sinyal gelirse → {"status":"signal","reason":"remote_support"}
     │   └── Agent hemen heartbeat gonderir (TriggerNow)
     │       └── Heartbeat response'ta detayli bilgi (session, task vs.) gelir
     └── 55sn timeout → {"status":"timeout"}
         └── Hemen yeni istek acar (reconnect)
```

### 3.2 Sinyal Tetikleme Akisi (Remote Support Ornegi)

```
Admin UI: "Baglan" tiklar
  → POST /api/v1/remote-support/sessions
  → rs.create_session() (DB kaydi)
  → notify_agent(agent_uuid)          ← asyncio.Event.set()
  → Agent'in long-poll baglantisi aninda uyanir  ← <1sn
  → Agent hemen heartbeat gonderir (TriggerNow)
  → Heartbeat response'ta remote_support_request gelir
  → sessionMgr.HandleRequest() baslar
  → Kullaniciya onay dialogu gosterilir
```

### 3.3 Signal Kanalinin Genel Amacli Kullanimi

Long-poll kanali sadece remote support icin degil, herhangi bir agent sinyali icin kullanilabilir:

```json
{"status": "signal", "reason": "remote_support"}
{"status": "signal", "reason": "new_task"}
{"status": "signal", "reason": "config_changed"}
{"status": "signal", "reason": "update_available"}
```

Agent her sinyal icin ayni seyi yapar: **hemen heartbeat gonder**. Tum detayli bilgi heartbeat response'ta zaten mevcuttur. Bu sayede:
- Yeni sinyal tipi eklemek = server'da 1 satir `notify_agent()` cagrisi
- Agent'ta hicbir degisiklik gerekmez
- Mevcut heartbeat response yapisi degismez

### 3.4 Online/Offline Tespit Bonusu

Long-poll baglantisi dogal olarak agent'in canli oldugunu gosterir:

- Agent `GET /signal` istegi actiysa → **canli**
- Baglanti koptuysa → **offline** (TCP RST veya timeout)
- Gecikme: 0-5sn (mevcut 2dk yerine)

Ek kod: `_active_listeners` dict'i ile hangi agent'larin su an bagli oldugu takip edilir.

---

## 4. Detayli Implementasyon Plani

### 4.1 Server: Yeni dosya `app/services/agent_signal.py` (~40 satir)

In-memory sinyal registry. `asyncio.Event` tabanlı.

```python
import asyncio
from datetime import datetime, timezone

# Agent UUID → asyncio.Event eslesmesi
_agent_events: dict[str, asyncio.Event] = {}
# Agent UUID → baglanti zamani (online tespit icin)
_active_listeners: dict[str, datetime] = {}


def get_or_create_event(agent_uuid: str) -> asyncio.Event:
    """Agent icin Event olustur veya mevcut olani dondur."""
    if agent_uuid not in _agent_events:
        _agent_events[agent_uuid] = asyncio.Event()
    return _agent_events[agent_uuid]


def notify_agent(agent_uuid: str) -> None:
    """Agent'a sinyal gonder. Thread-safe: sync context'ten cagirilabilir."""
    event = _agent_events.get(agent_uuid)
    if event is None:
        return  # Agent su an bagli degil, heartbeat fallback devreye girer
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(event.set)
    except RuntimeError:
        event.set()


def mark_listener_active(agent_uuid: str) -> None:
    """Agent long-poll baglantisi actiysa kaydet."""
    _active_listeners[agent_uuid] = datetime.now(timezone.utc)


def mark_listener_inactive(agent_uuid: str) -> None:
    """Agent long-poll baglantisi kapandiysa cikar."""
    _active_listeners.pop(agent_uuid, None)


def remove_event(agent_uuid: str) -> None:
    """Agent icin Event'i temizle."""
    _agent_events.pop(agent_uuid, None)
    _active_listeners.pop(agent_uuid, None)


def is_agent_listening(agent_uuid: str) -> bool:
    """Agent su an long-poll ile bagli mi?"""
    return agent_uuid in _active_listeners


def get_listening_agent_uuids() -> set[str]:
    """Su an bagli olan tum agent UUID'lerini dondur."""
    return set(_active_listeners.keys())


def active_listener_count() -> int:
    """Diagnostik: kac agent bagli?"""
    return len(_active_listeners)


def clear_all() -> None:
    """Server shutdown'da temizlik."""
    _agent_events.clear()
    _active_listeners.clear()
```

**Neden in-memory:**
- Server restart'ta agent'lar zaten reconnect eder (backoff ile)
- DB'ye yazma gereksiz I/O uretir
- asyncio.Event DB'de saklanamaz

**Thread safety notu:**
- FastAPI sync endpoint'ler (heartbeat, remote_support) threadpool'da calisir
- `notify_agent()` sync context'ten cagrilacagi icin `call_soon_threadsafe` kullanilir
- `get_or_create_event()` ve `mark_listener_*` sadece async endpoint icinden cagrilir (ayni event loop)

### 4.2 Server: `app/api/v1/agent.py` - Yeni endpoint (+30 satir)

```python
import asyncio
from fastapi import Query
from app.services import agent_signal

@router.get("/signal")
async def wait_for_signal(
    timeout: int = Query(default=55, ge=5, le=55),
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
    db: Session = Depends(get_db),
):
    """
    Long-poll endpoint: Agent bu istegi acar, sinyal gelene kadar bekler.
    Sinyal gelirse aninda response doner; timeout olursa bos response doner.
    """
    _authenticate_agent(db, x_agent_uuid, x_agent_secret)

    event = agent_signal.get_or_create_event(x_agent_uuid)
    event.clear()  # Onceki set durumunu temizle (stale sinyal onleme)
    agent_signal.mark_listener_active(x_agent_uuid)

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return {"status": "signal", "reason": "wake"}
    except asyncio.TimeoutError:
        return {"status": "timeout"}
    finally:
        event.clear()
        agent_signal.mark_listener_inactive(x_agent_uuid)
```

**Onemli notlar:**
- `async def` olmali (asyncio.Event.wait kullanabilmesi icin)
- `_authenticate_agent()` sync DB erisimi yapar, FastAPI bunu threadpool'da calistirir
- `timeout` max 55sn — nginx varsayilan `proxy_read_timeout` 60sn'den kucuk
- `finally` blogu: agent baglantisi kopsa bile temizlik yapilir

**Neden `event.clear()` basta cagiriliyor:**
Agent reconnect ettiginde onceki `notify_agent()` cagrisi Event'i set etmis olabilir. Bu durumda agent hemen doner ve heartbeat gonderir — istenmeyen bir durum degil ama gereksiz heartbeat uretir. `clear()` ile bu onlenir.

**Potansiyel concern - Event.clear() ile sinyal kaybi:**
```
T1: Agent baglanti acar, event.clear() cagrilir
T2: Admin session olusturur, notify_agent() → event.set()
T3: Agent event.wait() baslar, event zaten set → aninda doner
```
Bu senaryo sorunsuz: `clear()` ile `wait()` arasinda gelen sinyal kaybolmaz cunku Event set durumunu korur.

**Gercek kayip senaryosu ve cozumu:**
```
T1: Agent'in onceki long-poll timeout oldu, TCP response dondu
T2: Admin session olusturur, notify_agent() → event yok veya set (ama agent dinlemiyor)
T3: Agent yeni long-poll istegi acar (50ms sonra)
T4: Agent event.clear() cagirir ← BURADA T2'nin sinyali temizlenir
```
Cozum: `notify_agent()` cagrildiginda Event yoksa bir sey olmaz — agent yeni baglandiginda heartbeat zaten gonderir. Ama 50ms penceresi icinde event varsa ve set edilmisse, `clear()` onu temizler. Bu durumda heartbeat 60sn fallback devreye girer.

**Bu riski azaltma:**
- `clear()` yerine `event.wait()` oncesinde kontrol eklenebilir
- Veya `clear()` tamamen kaldirilabilir (cift heartbeat kabul edilebilir yan etki)
- Pratikte 50ms penceresi cok dar, olasilik cok dusuk

**Onerilen yaklasim:** `clear()` kaldir, cift heartbeat kabul et. Daha guvenli:
```python
event = agent_signal.get_or_create_event(x_agent_uuid)
# clear() YOK — onceki sinyal varsa hemen doner, agent heartbeat atar
agent_signal.mark_listener_active(x_agent_uuid)
try:
    await asyncio.wait_for(event.wait(), timeout=timeout)
    return {"status": "signal", "reason": "wake"}
except asyncio.TimeoutError:
    return {"status": "timeout"}
finally:
    event.clear()  # Sadece cikista temizle
    agent_signal.mark_listener_inactive(x_agent_uuid)
```

### 4.3 Server: `app/api/v1/remote_support.py` - notify hook'lari (+3 satir)

Uc yere tek satir eklenir:

```python
from app.services import agent_signal

# create_remote_session() icinde, session olusturulduktan sonra:
def create_remote_session(...):
    session = rs.create_session(db, body.agent_uuid, user.id, body.reason, body.max_duration_min)
    agent_signal.notify_agent(body.agent_uuid)  # ← YENi
    return {...}

# end_remote_session() icinde:
def end_remote_session(...):
    rs.end_session(db, session_id, ended_by="admin")
    # Session'in agent_uuid'sini almak icin once session'i okumak gerekir
    # rs.end_session zaten session'i dondurmuyor, DB'den agent_uuid alinmali
    # Alternatif: end_session'dan agent_uuid donsun
    return {...}

# cancel_remote_session() icinde:
def cancel_remote_session(...):
    rs.cancel_pending_session(db, session_id, admin_user_id=user.id)
    # Ayni sekilde agent_uuid gerekir
    return {...}
```

**Dikkat:** `end_remote_session` ve `cancel_remote_session` su an `session_id` aliyor ama `agent_uuid` bilgisi yok. Cozum secenekleri:
1. `rs.end_session()` ve `rs.cancel_pending_session()` fonksiyonlarindan `agent_uuid` dondur
2. Endpoint icinde once `rs.get_session(db, session_id)` ile agent_uuid'yi al
3. `rs` service fonksiyonlari icinde `notify_agent()` cagir (service katmaninda)

**Onerilen:** Secenek 3 — service katmaninda `notify_agent()` cagirmak en temiz yaklasim. Endpoint'ler degismez, `remote_support_service.py` icinde:

```python
# remote_support_service.py icinde:
from app.services import agent_signal

def create_session(db, agent_uuid, ...):
    # ... mevcut kod ...
    agent_signal.notify_agent(agent_uuid)
    return session

def end_session(db, session_id, ...):
    session = _get_session(db, session_id)
    # ... mevcut kod ...
    agent_signal.notify_agent(session.agent_uuid)

def cancel_pending_session(db, session_id, ...):
    session = _get_session(db, session_id)
    # ... mevcut kod ...
    agent_signal.notify_agent(session.agent_uuid)
```

### 4.4 Server: `app/main.py` - Shutdown temizligi (+3 satir)

```python
from app.services import agent_signal

@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_upload_dir(settings.upload_dir)
    init_db()
    seed_initial_data()
    start_scheduler()
    yield
    stop_scheduler()
    agent_signal.clear_all()  # ← YENi: Tum Event'leri temizle
```

### 4.5 Agent: `internal/api/client.go` - WaitForSignal metodu (+45 satir)

```go
// SignalResponse long-poll signal endpoint'inden donen cevap.
type SignalResponse struct {
    Status string `json:"status"` // "signal" veya "timeout"
    Reason string `json:"reason"` // "wake", "remote_support", vs.
}

// NewClient guncellenmis hali - longPollHTTP eklenir
func NewClient(cfg config.ServerConfig) *Client {
    return &Client{
        baseURL: strings.TrimRight(cfg.URL, "/"),
        httpClient: &http.Client{
            Timeout: 30 * time.Second,
        },
        longPollHTTP: &http.Client{
            Timeout: 65 * time.Second,  // Server timeout (55sn) + margin
        },
    }
}

// WaitForSignal server'dan sinyal bekler (long polling).
// Sinyal gelirse SignalResponse doner, timeout olursa status="timeout" doner.
func (c *Client) WaitForSignal(
    ctx context.Context,
    agentUUID, secret string,
    timeoutSec int,
) (*SignalResponse, error) {
    url := fmt.Sprintf("%s/api/v1/agent/signal?timeout=%d", c.baseURL, timeoutSec)
    req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
    if err != nil {
        return nil, err
    }
    req.Header.Set("X-Agent-UUID", agentUUID)
    req.Header.Set("X-Agent-Secret", secret)

    resp, err := c.longPollHTTP.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    if resp.StatusCode >= 300 {
        return nil, httpErrorFromResponse(http.MethodGet, url, resp)
    }

    var out SignalResponse
    if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
        return nil, err
    }
    return &out, nil
}
```

**Client struct degisikligi:**
```go
type Client struct {
    baseURL      string
    httpClient   *http.Client  // Normal istekler (30sn timeout)
    longPollHTTP *http.Client  // Long-poll istekleri (65sn timeout)
}
```

**Neden ayri HTTP client:**
- Normal istekler 30sn timeout ile calisir (heartbeat, task report, vs.)
- Long-poll istekleri 55sn server timeout + 10sn margin = 65sn timeout gerektirir
- Ayni client kullanilirsa normal istekler de 65sn timeout ile calisir — istenmeyen durum

### 4.6 Agent: Yeni dosya `internal/heartbeat/signal.go` (~80 satir)

```go
package heartbeat

import (
    "context"
    "log"
    "math"
    "time"

    "appcenter-agent/internal/api"
)

const (
    signalPollTimeoutSec = 55
    signalMinBackoff     = 2 * time.Second
    signalMaxBackoff     = 60 * time.Second
)

// SignalListener long-poll ile server'dan sinyal bekler.
// Sinyal geldiginde onSignal callback'ini cagirarak immediate heartbeat tetikler.
type SignalListener struct {
    client    *api.Client
    agentUUID string
    secretKey string
    logger    *log.Logger
    onSignal  func() // Genelde sender.TriggerNow
}

func NewSignalListener(
    client *api.Client,
    agentUUID, secretKey string,
    logger *log.Logger,
    onSignal func(),
) *SignalListener {
    return &SignalListener{
        client:    client,
        agentUUID: agentUUID,
        secretKey: secretKey,
        logger:    logger,
        onSignal:  onSignal,
    }
}

// Start long-poll dongusunu baslatir. Context iptal edilene kadar calisir.
func (s *SignalListener) Start(ctx context.Context) {
    consecutiveErrors := 0
    s.logger.Println("signal listener started")

    for {
        // Context kontrolu
        select {
        case <-ctx.Done():
            s.logger.Println("signal listener stopped")
            return
        default:
        }

        resp, err := s.client.WaitForSignal(ctx, s.agentUUID, s.secretKey, signalPollTimeoutSec)

        if ctx.Err() != nil {
            s.logger.Println("signal listener stopped (context cancelled)")
            return
        }

        if err != nil {
            consecutiveErrors++
            backoff := calcBackoff(consecutiveErrors, signalMinBackoff, signalMaxBackoff)
            s.logger.Printf("signal poll error (attempt %d, retry in %v): %v",
                consecutiveErrors, backoff, err)
            select {
            case <-ctx.Done():
                return
            case <-time.After(backoff):
                continue
            }
        }

        // Basarili istek — hata sayacini sifirla
        consecutiveErrors = 0

        if resp.Status == "signal" {
            s.logger.Printf("signal received: reason=%s", resp.Reason)
            if s.onSignal != nil {
                s.onSignal()
            }
            // Sinyal islendi, hemen yeni long-poll ac
            continue
        }

        // resp.Status == "timeout" → normal, hemen yeni istek ac
        // (log basma — gereksiz gurultu)
        continue
    }
}

func calcBackoff(attempt int, min, max time.Duration) time.Duration {
    backoff := time.Duration(math.Pow(2, float64(attempt-1))) * min
    if backoff > max {
        return max
    }
    return backoff
}
```

**Exponential backoff detayi:**
- 1. hata: 2sn
- 2. hata: 4sn
- 3. hata: 8sn
- 4. hata: 16sn
- 5. hata: 32sn
- 6+ hata: 60sn (max)
- Basarili istekle sifirlanir

### 4.7 Agent: `internal/heartbeat/heartbeat.go` - TriggerNow (+15 satir)

```go
type Sender struct {
    // ... mevcut alanlar ...
    triggerCh chan struct{} // ← YENi: Signal listener'dan tetikleme
}

func NewSender(...) *Sender {
    return &Sender{
        // ... mevcut init ...
        triggerCh: make(chan struct{}, 1), // Buffered, 1 — coklu sinyal tek heartbeat
    }
}

// TriggerNow aninda heartbeat gonderimi tetikler.
// Non-blocking: kanal doluysa (zaten tetiklenmis) bir sey yapmaz.
func (s *Sender) TriggerNow() {
    select {
    case s.triggerCh <- struct{}{}:
    default:
        // Zaten bir tetikleme bekliyor
    }
}

func (s *Sender) Start(ctx context.Context) {
    ticker := time.NewTicker(time.Duration(s.cfg.Heartbeat.IntervalSec) * time.Second)
    defer ticker.Stop()

    s.sendOnce(ctx, false)

    for {
        select {
        case <-ctx.Done():
            s.logger.Println("heartbeat stopped")
            return
        case <-ticker.C:
            s.sendOnce(ctx, false)
        case <-s.triggerCh:                    // ← YENi
            s.logger.Println("heartbeat triggered by signal")
            s.sendOnce(ctx, false)
            ticker.Reset(time.Duration(s.cfg.Heartbeat.IntervalSec) * time.Second) // ← Ticker sifirla
        }
    }
}
```

**Neden `ticker.Reset()`:**
Signal ile heartbeat gonderildikten sonra ticker sifirlanir. Aksi halde:
- T=0: Normal heartbeat
- T=30: Signal → heartbeat
- T=60: Normal heartbeat (signal'den sadece 30sn sonra — gereksiz)

Reset ile: T=30 signal → sonraki normal heartbeat T=90'da olur.

**Neden buffered channel (size 1):**
- Birden fazla hizli sinyal gelirse (ornegin admin art arda session olusturup iptal ederse) sadece 1 heartbeat tetiklenir
- Non-blocking `select` ile `TriggerNow()` hicbir zaman bloklanmaz

### 4.8 Agent: `cmd/service/core.go` - SignalListener baslatma (+6 satir)

```go
// Mevcut kod: sender baslatildiktan sonra
sender := heartbeat.NewSender(client, cfg, logger, pollResults, taskQueue, invManager, remoteProvider)
go sender.Start(ctx)

// ← YENi: Signal listener baslatma
signalListener := heartbeat.NewSignalListener(
    client,
    cfg.Agent.UUID,
    cfg.Agent.SecretKey,
    logger,
    sender.TriggerNow,
)
go signalListener.Start(ctx)
```

---

## 5. Nginx Konfigurasyonu

### Mevcut Durum

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    # proxy_read_timeout ayari YOK → nginx varsayilani: 60sn
}
```

### Gerekli Degisiklik

**Degisiklik gerekmiyor.** Server timeout 55sn < nginx timeout 60sn.

Ama guvenlik icin `/api/v1/agent/signal` icin ozel location eklenebilir (opsiyonel):

```nginx
# OPSIYONEL — sadece ileride timeout arttirilmak istenirse
location /api/v1/agent/signal {
    proxy_pass http://127.0.0.1:8000;
    proxy_read_timeout 65s;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

---

## 6. Kaynak Kullanimi Analizi

### 6.1 Server Tarafi (500 Agent)

| Kaynak | Miktar | Aciklama |
|--------|--------|----------|
| asyncio coroutine | 500 | Her biri ~1-2 KB stack |
| asyncio.Event | 500 | Her biri ~200 byte |
| TCP soketi | 500 | Idle, veri akisi yok |
| Toplam RAM | ~1-2 MB | Ihmal edilebilir |
| CPU (idle) | ~0% | Event.wait() CPU tuketmez |
| CPU (sinyal) | Ihmal edilebilir | Event.set() + response serialize |
| File descriptor | 500 | Linux varsayilani 1024, `ulimit -n` ile arttirilabilir |

### 6.2 Agent Tarafi (Her Agent)

| Kaynak | Miktar | Aciklama |
|--------|--------|----------|
| Goroutine | 1 | SignalListener |
| TCP baglanti | 1 | Idle HTTP GET |
| RAM | ~10 KB | Goroutine stack + HTTP buffers |
| CPU (idle) | 0% | Bloklanan goroutine CPU tuketmez |
| Ag trafigi (idle) | ~0 | TCP keepalive haric |

### 6.3 File Descriptor Limiti

```bash
# Mevcut limiti kontrol et:
ulimit -n

# Gerekirse arttir (systemd service icin):
# /etc/systemd/system/appcenter.service
[Service]
LimitNOFILE=65535
```

500 agent + diger HTTP baglantilari + PostgreSQL + dosya islemleri icin 1024 yeterli olabilir ama 4096+ onerilir.

### 6.4 Reconnect Trafigi Karsilastirmasi

| Senaryo | Istek/sn (500 agent) | Aylik HTTP istek |
|---------|---------------------|-----------------|
| Mevcut heartbeat (60sn) | ~8.3 | ~21.6M |
| Long-poll reconnect (55sn) | ~9.1 | ~23.7M |
| **Toplam (heartbeat + long-poll)** | **~17.4** | **~45.3M** |

Long-poll mevcut heartbeat'in uzerine ~%9 ek trafik ekler. Ihmal edilebilir.

---

## 7. Sorunsal Senaryolar ve Cozumleri

### 7.1 Agent Long-Poll Bagli Degilken Sinyal Gelirse

**Senaryo:** Agent henuz baglanti kurmamis veya reconnect arasindayken admin session olusturur.

**Davranis:**
- `notify_agent()` Event'i set eder (veya Event yoksa no-op)
- Agent sonraki long-poll isteginde Event set durumunu gorur → aninda doner
- Eger Event yoksa (agent hic baglanmamis): **heartbeat 60sn fallback** devreye girer

**Kabul edilebilirlik:** 50ms reconnect penceresi + 60sn fallback. Gercek kayip olasiligi cok dusuk.

### 7.2 Server Restart / Crash

**Senaryo:** Server restart edildiginde tum Event'ler ve aktif baglantilar kaybolur.

**Davranis:**
1. Agent'in HTTP istegi `Connection refused` veya `502 Bad Gateway` alir
2. SignalListener exponential backoff ile retry baslar (2sn → 4sn → 8sn → ...)
3. Server ayaga kalktiginda agent reconnect eder
4. Basarili baglanti ile hata sayaci sifirlanir
5. Normal isleyise donulur

**Kurtarma suresi:** Server restart + backoff = tipik olarak 5-15sn.

### 7.3 Agent Offline (Ag Kesintisi)

**Senaryo:** Agent'in ag baglantisi kopar.

**Davranis (Server tarafi):**
- TCP soketi kapanir (RST veya timeout)
- `finally` blogu calisir: `mark_listener_inactive()` + `event.clear()`
- Agent otomatik olarak offline olarak isaretlenir

**Davranis (Agent tarafi):**
- HTTP istegi hata doner (connection reset, timeout, vs.)
- SignalListener exponential backoff ile retry
- Ag geri geldiginde reconnect
- Normal heartbeat de ayni sekilde etkilenir

### 7.4 Coklu Hizli Sinyal (Rapid Fire)

**Senaryo:** Admin hizli sekilde session olustur → iptal → olustur yapar.

**Davranis:**
- `asyncio.Event.set()` idempotent — birden fazla set() tek `wait()` donus tetikler
- Agent tek heartbeat gonderir
- Heartbeat response'ta guncel durum (son pending session) gelir
- TriggerNow channel buffered(1) — coklu sinyal tek heartbeat uretir

**Sonuc:** Gereksiz heartbeat cascade olmaz.

### 7.5 Proxy/Firewall 60sn Timeout

**Senaryo:** Aradaki proxy veya firewall idle baglantilari 60sn'de keser.

**Davranis:**
- Server timeout 55sn, proxy'den 5sn once cevap doner
- Agent normal timeout response alir, hemen reconnect eder
- Sorun olmaz

**Eger proxy timeout < 55sn ise:**
- Agent beklenmedik hata alir (connection reset)
- SignalListener backoff ile retry
- Cozum: Server timeout'u config yapilabilir (`SIGNAL_POLL_TIMEOUT_SEC` env)
- Veya agent'ta timeout parametresi config'e alinir

### 7.6 Uvicorn Worker Restart (Graceful)

**Senaryo:** Uvicorn worker'lar yeniden baslatilirsa (config reload, memory limit vs.)

**Davranis:**
- Mevcut baglantilar kapanir
- In-memory Event dict'i kaybolur
- Agent'lar reconnect eder (backoff)
- Yeni worker'da yeni Event'ler olusturulur

**Not:** AppCenter tek worker ile calisir (PostgreSQL + in-memory state), bu senaryo dusuk olasilikli.

### 7.7 PostgreSQL Connection Pool + Long-Poll

**Senaryo:** Long-poll endpoint'i DB erisimi yapar mi? Connection pool'u etkiler mi?

**Davranis:**
- `_authenticate_agent()` baglanti basinda bir kere DB'ye erisr (SELECT agents WHERE uuid=...)
- 55sn bekleme sirasinda DB baglantisi **TUTULMAZ** (SQLAlchemy session Depends ile inject edilir, response donunce kapanir)
- DB lock uzerinde **sifir etki**

**Dikkat:** `Depends(get_db)` FastAPI'da request bitince session'i kapatir. Ama async endpoint'te `await` sirasinda session acik kalabilir mi? Hayir — `_authenticate_agent()` sync cagri, threadpool'da calisir ve bitmeden response donmez. Session kullanimi sadece auth icin, sonra `await` baslar.

Daha guvenli yaklasim: Auth'u `await` oncesinde yapmak ve DB session'ini erken kapatmak:
```python
@router.get("/signal")
async def wait_for_signal(..., db: Session = Depends(get_db)):
    agent = _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    # DB session burada kapanir (Depends lifecycle)
    # ... await event.wait() ...
```
FastAPI'da `Depends(get_db)` response donene kadar session'i acik tutar. Bu durumda 55sn boyunca session acik kalir.

**Cozum:** DB session'ini manuel yonet:
```python
@router.get("/signal")
async def wait_for_signal(
    timeout: int = Query(default=55, ge=5, le=55),
    x_agent_uuid: str = Header(..., alias="X-Agent-UUID"),
    x_agent_secret: str = Header(..., alias="X-Agent-Secret"),
):
    # Manuel DB session — auth bitince hemen kapat
    db = next(get_db())
    try:
        _authenticate_agent(db, x_agent_uuid, x_agent_secret)
    finally:
        db.close()

    # DB session kapandi, artik sadece asyncio Event bekliyor
    event = agent_signal.get_or_create_event(x_agent_uuid)
    agent_signal.mark_listener_active(x_agent_uuid)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return {"status": "signal", "reason": "wake"}
    except asyncio.TimeoutError:
        return {"status": "timeout"}
    finally:
        event.clear()
        agent_signal.mark_listener_inactive(x_agent_uuid)
```

**Bu cok onemli:** 500 agent × 55sn modelinde gereksiz acik session birakilirsa pool baskisi olusur. Bu nedenle long-poll endpoint'inde auth sonrasi DB session'in erken kapatilmasi **zorunludur**.

### 7.8 Agent Secret Degisirse

**Senaryo:** Agent yeniden register olur ve secret_key degisir.

**Davranis:**
- Mevcut long-poll istegi auth ile kurulmus, devam eder
- Sonraki reconnect'te yeni secret kullanilir
- Eski secret ile 401 alinirsa → backoff → agent config'den yeni secret okur

**Pratikte:** Secret degisimi cok nadir (sadece re-register). Sorun teskil etmez.

### 7.9 Ayni Agent'tan Coklu Long-Poll Baglantisi

**Senaryo:** Bug veya yeniden baslatma sirasinda ayni UUID ile 2 long-poll istegi acilik olur.

**Davranis:**
- Her ikisi de ayni `asyncio.Event` uzerinde bekler
- Signal geldiginde **her ikisi de** uyanir
- 2 heartbeat tetiklenir (TriggerNow channel buffered(1) oldugu icin sadece 1 heartbeat gider)
- Ilk baglanti kapandiginda `mark_listener_inactive()` cagrilir ama ikincisi hala aktif
- **Sorun:** `_active_listeners` dict tek UUID tutugu icin ikisi birbirini ezer

**Cozum (basit):** Pratikte sorun degil — agent tek instance calisir, coklu baglanti sadece gecici durum (eski baglanti timeout'a yakin + yeni baglanti).

**Cozum (saglam, gerekirse):** `_active_listeners` da `set[connection_id]` olarak tutulabilir. Ama over-engineering — ilk versiyonda gereksiz.

### 7.10 Server Yuku Altinda (Yuksek CPU/IO)

**Senaryo:** Sunucu yogun islem altinda, long-poll response'lari gecikir.

**Davranis:**
- asyncio Event.set() aninda tum bekleyen coroutine'leri uyandirir
- Ama event loop mesgulse response gonderimi gecikebilir
- Agent timeout'a yaklasirsa normal timeout response doner

**Etki:** Signal iletim suresi 1sn yerine 2-3sn olabilir. Kabul edilebilir.

### 7.11 Bellek Sizintisi (Memory Leak)

**Senaryo:** Agent'lar baglantip ayrilir, Event'ler temizlenmez.

**Onlem:**
- `finally` blogu her durumda (hata, timeout, sinyal) `mark_listener_inactive()` cagrilir
- `remove_event()` sadece agent tamamen offline oldugunda cagrilir
- Event nesneleri cok kucuk (~200 byte), 10.000 event bile ~2MB

**Ek onlem (opsiyonel):** Periyodik temizlik scheduler'i — 1 saatte bir kullanilmayan Event'leri temizle:
```python
def cleanup_stale_events(max_idle_seconds: int = 300):
    now = datetime.now(timezone.utc)
    stale = [uuid for uuid, ts in _active_listeners.items()
             if (now - ts).total_seconds() > max_idle_seconds]
    for uuid in stale:
        remove_event(uuid)
```

### 7.12 Agent Baslangicinda Server Erisilemedigi Durum

**Senaryo:** Agent baslatilir ama server erisilelemez.

**Davranis:**
- SignalListener ilk istekte hata alir
- Backoff baslar: 2sn → 4sn → 8sn → ... → 60sn
- Bu sirada normal heartbeat de basarisiz olur (ayni durum)
- Server erisilebilir oldugunda her ikisi de normal calisir

**Not:** SignalListener ve heartbeat birbirinden bagimsiz calisir. Biri basarisiz olsa bile digeri etkilenmez.

---

## 8. Guvenlik Degerlendirmesi

### 8.1 DoS/Kaynak Tuketimi

**Risk:** Kotu niyetli istemci binlerce long-poll baglantisi acabilir.

**Onlemler:**
- `_authenticate_agent()` her istekte cagrilir — gecersiz credential ile baglanti reddedilir
- Nginx `limit_conn` ile agent basina baglanti siniri konabilir (opsiyonel)
- `timeout` parametresi max 55sn ile sinirli (Query validation: `ge=5, le=55`)
- uvicorn `--limit-concurrency` ayari ile toplam es zamanli baglanti siniri

### 8.2 Replay Attack

**Risk:** Yakalanan long-poll istegi tekrar gonderilir.

**Onlem:** Mevcut auth mekanizmasi (UUID + Secret header) yeterli. Long-poll istegi state degistirmez (sadece okuma), replay zararsiz.

### 8.3 Bilgi Sizintisi

Long-poll response'ta sadece `{"status":"signal","reason":"wake"}` doner. Hassas bilgi icermez. Detayli bilgi heartbeat response'ta gelir (mevcut guvenlik modeli).

---

## 9. Test Plani

### 9.1 Birim Testleri (Server)

```python
# tests/test_agent_signal.py

import asyncio
import pytest
from app.services.agent_signal import (
    get_or_create_event, notify_agent, is_agent_listening,
    mark_listener_active, mark_listener_inactive, clear_all,
    active_listener_count,
)

def test_get_or_create_event_creates_new():
    clear_all()
    event = get_or_create_event("agent-1")
    assert isinstance(event, asyncio.Event)
    assert not event.is_set()

def test_get_or_create_event_reuses_existing():
    clear_all()
    e1 = get_or_create_event("agent-1")
    e2 = get_or_create_event("agent-1")
    assert e1 is e2

def test_notify_agent_sets_event():
    clear_all()
    event = get_or_create_event("agent-1")
    notify_agent("agent-1")
    assert event.is_set()

def test_notify_agent_nonexistent_is_noop():
    clear_all()
    notify_agent("nonexistent")  # Hata firlatmamali

def test_listener_tracking():
    clear_all()
    assert not is_agent_listening("agent-1")
    mark_listener_active("agent-1")
    assert is_agent_listening("agent-1")
    assert active_listener_count() == 1
    mark_listener_inactive("agent-1")
    assert not is_agent_listening("agent-1")

@pytest.mark.asyncio
async def test_signal_endpoint_timeout():
    """Signal endpoint timeout donmeli."""
    clear_all()
    event = get_or_create_event("agent-1")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(event.wait(), timeout=0.1)

@pytest.mark.asyncio
async def test_signal_endpoint_immediate_wake():
    """Signal set edilmisse hemen donmeli."""
    clear_all()
    event = get_or_create_event("agent-1")
    event.set()
    await asyncio.wait_for(event.wait(), timeout=1.0)
    assert True  # Timeout olmadan tamamlandi
```

### 9.2 Entegrasyon Testi (Server Endpoint)

```bash
# Terminal 1: Long-poll istegi ac (5sn timeout ile test)
curl -v \
  -H "X-Agent-UUID: <test-uuid>" \
  -H "X-Agent-Secret: <test-secret>" \
  "http://127.0.0.1:8000/api/v1/agent/signal?timeout=5"
# 5sn sonra: {"status":"timeout"}

# Terminal 2: Signal gonder (session olustur)
# → Terminal 1 aninda {"status":"signal","reason":"wake"} donmeli
```

### 9.3 Manuel Uctan Uca Test

1. Agent baslatilir, log'da `signal listener started` gorunur
2. Admin UI'dan remote support session olusturulur
3. Agent log'da 1-2sn icinde `signal received: reason=wake` gorunur
4. Ardindan `heartbeat triggered by signal` gorunur
5. Agent onay popup'i gosterir

### 9.4 Hata Testi

1. Server durdurulur → Agent log'da `signal poll error` + backoff gorunur
2. Server baslatilir → Agent reconnect eder, `signal listener started` gorunmez ama istek basarili olur
3. Ag kablosu cekilir → Agent connection error + backoff
4. Ag geri gelir → Agent reconnect + normal isleyis

### 9.5 Yuk Testi (Opsiyonel)

```python
# 500 es zamanli long-poll baglantisi simule et
import asyncio
import aiohttp

async def simulate_agent(session, uuid):
    url = f"http://127.0.0.1:8000/api/v1/agent/signal?timeout=55"
    headers = {"X-Agent-UUID": uuid, "X-Agent-Secret": "test"}
    async with session.get(url, headers=headers) as resp:
        return await resp.json()

async def main():
    async with aiohttp.ClientSession() as session:
        tasks = [simulate_agent(session, f"agent-{i}") for i in range(500)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        print(f"Success: {sum(1 for r in results if not isinstance(r, Exception))}")
        print(f"Error: {sum(1 for r in results if isinstance(r, Exception))}")

asyncio.run(main())
```

---

## 10. Degisecek Dosyalar Ozeti

| Dosya | Islem | Satir |
|-------|-------|-------|
| `server/app/services/agent_signal.py` | **YENi** | ~50 |
| `server/app/api/v1/agent.py` | Degisiklik | +30 |
| `server/app/services/remote_support_service.py` | Degisiklik | +6 |
| `server/app/main.py` | Degisiklik | +2 |
| `server/tests/test_agent_signal.py` | **YENi** | ~50 |
| `agent/internal/api/client.go` | Degisiklik | +45 |
| `agent/internal/heartbeat/signal.go` | **YENi** | ~80 |
| `agent/internal/heartbeat/heartbeat.go` | Degisiklik | +20 |
| `agent/cmd/service/core.go` | Degisiklik | +8 |

**Toplam:** 3 yeni dosya, 6 degisiklik, ~290 satir yeni kod.

---

## 11. Konfigürasyon

### Server (.env)

```bash
# Mevcut — degisiklik yok
# Opsiyonel eklenti (varsayilan 55sn, genelde degistirilmez):
# SIGNAL_POLL_MAX_TIMEOUT_SEC=55
```

### Agent (config.yaml)

```yaml
# Mevcut — degisiklik yok
# Signal listener heartbeat.interval_sec ile birlikte calisir
# Devre disi birakmak icin opsiyonel:
# signal:
#   enabled: true
#   timeout_sec: 55
```

### Nginx

```nginx
# Degisiklik GEREKMIYOR (varsayilan proxy_read_timeout=60s > server timeout=55s)
# Opsiyonel: signal icin ozel timeout
# location /api/v1/agent/signal {
#     proxy_pass http://127.0.0.1:8000;
#     proxy_read_timeout 65s;
# }
```

---

## 12. Rollback / Devre Disi Birakma

### Hizli Devre Disi Birakma (Server)

Signal endpoint'ini devre disi birakma:
```python
# agent.py signal endpoint'ine:
@router.get("/signal")
async def wait_for_signal(...):
    return {"status": "disabled"}
```

Agent hemen timeout response gibi isler, backoff'a girer, heartbeat fallback devam eder.

### Tam Geri Alma

1. Server'dan `agent_signal.py` ve endpoint degisikliklerini geri al
2. Agent'tan `signal.go`, `TriggerNow` ve `core.go` degisikliklerini geri al
3. Her iki taraf bagimsiz geri alinabilir:
   - Sadece server geri alinirsa: Agent 401 veya 404 alir → backoff → heartbeat devam
   - Sadece agent geri alinirsa: Server endpoint kullanilmaz → kaynak tuketimi sifir

---

## 13. Gelecek Gelistirmeler (Bu Fazda Yapilmayacak)

1. **Dashboard'da canli agent durumu:** `is_agent_listening()` ile "canli bagli" badge'i
2. **Deployment hizli iletim:** Task olusturuldugunda `notify_agent()` cagrisi
3. **Config push:** Ayar degistiginde ilgili agent'lara sinyal
4. **Agent update bildirimi:** Yeni versiyon yuklendiginde tum agent'lara sinyal
5. **Metrik:** `active_listener_count()` health endpoint'ine ekleme
6. **Graceful reconnect:** Agent versiyon guncelleme sirasinda signal baglantisini duzgun kapatma

---

## 14. Karar Kontrol Listesi

- [ ] Long polling yaklasimi onaylandi mi?
- [ ] DB session yonetimi (Senaryo 7.7) — manuel session mu, Depends mu?
- [ ] Event.clear() stratejisi — basta mi, sadece sonda mi?
- [ ] notify_agent() nereye konulacak — endpoint mi, service katmani mi?
- [ ] Online tespit ozelligi bu fazda mi, sonra mi?
- [ ] Agent config'e signal enabled/disabled flag eklenecek mi?
- [ ] Nginx config degisikligi (opsiyonel ozel location) yapilacak mi?
- [ ] File descriptor limiti arttirilacak mi?
