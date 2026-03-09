// AppCenter UI WebSocket Client
// Reconnects automatically with exponential backoff

class AppCenterWS {
    constructor(options = {}) {
        this.onEvent = options.onEvent || function(){};
        this.onConnect = options.onConnect || function(){};
        this.onDisconnect = options.onDisconnect || function(){};
        this.ws = null;
        this._attempts = 0;
        this._timer = null;
        this._stopped = false;
    }

    start() {
        this._stopped = false;
        this._connect();
    }

    stop() {
        this._stopped = true;
        if (this._timer) clearTimeout(this._timer);
        if (this.ws) {
            this.ws.onclose = null;
            this.ws.close();
        }
    }

    _connect() {
        const token = this._getToken();
        if (!token) {
            this._timer = setTimeout(() => this._connect(), 5000);
            return;
        }

        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const url = `${proto}//${location.host}/api/v1/ui/ws?token=${encodeURIComponent(token)}`;

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            this._attempts = 0;
            console.log("AppCenterWS: connected");
            this.onConnect();
        };

        this.ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                this.onEvent(msg);
            } catch (err) {
                console.warn("AppCenterWS: parse error", err);
            }
        };

        this.ws.onclose = (e) => {
            console.log("AppCenterWS: disconnected", e.code);
            this.onDisconnect();
            if (!this._stopped) this._reconnect();
        };

        this.ws.onerror = (e) => {
            console.warn("AppCenterWS: error", e);
        };
    }

    _reconnect() {
        this._attempts++;
        const delay = Math.min(2000 * Math.pow(2, this._attempts - 1), 30000);
        const jitter = delay * (0.75 + 0.5 * Math.random());
        console.log(`AppCenterWS: reconnect in ${Math.round(jitter / 1000)}s`);
        this._timer = setTimeout(() => this._connect(), jitter);
    }

    _getToken() {
        // Keep in sync with app/static/js/api.js:getToken
        const token = localStorage.getItem("appcenter_token") || "";
        if (token) return token;

        // Optional fallback: read from cookie if present in some environments
        const m = document.cookie.match(/(?:^|;\s*)appcenter_token=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : "";
    }

    get connected() {
        return !!(this.ws && this.ws.readyState === WebSocket.OPEN);
    }
}
