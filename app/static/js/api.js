(function () {
  const API_PREFIX = "/api/v1";
  const UI_SETTINGS_CACHE_TTL_MS = 5 * 60 * 1000; // refresh occasionally so settings changes apply without reload

  function getToken() {
    return localStorage.getItem("appcenter_token") || "";
  }

  function setToken(token) {
    localStorage.setItem("appcenter_token", token);
  }

  function clearToken() {
    localStorage.removeItem("appcenter_token");
  }

  function authHeaders(extra) {
    const headers = extra ? { ...extra } : {};
    const token = getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  }

  async function req(path, options) {
    const opts = options ? { ...options } : {};
    opts.headers = authHeaders(opts.headers || {});
    const res = await fetch(`${API_PREFIX}${path}`, opts);
    if (res.status === 401) {
      throw new Error("Unauthorized");
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Request failed");
      }
      return data;
    }
    if (!res.ok) {
      throw new Error("Request failed");
    }
    return res;
  }

  let _uiSettings = { timezone: null, loadedAt: 0, loading: null };

  async function initUi(force) {
    const now = Date.now();
    if (_uiSettings.loading) return _uiSettings.loading;
    if (!force && _uiSettings.timezone && (now - _uiSettings.loadedAt) < UI_SETTINGS_CACHE_TTL_MS) return;

    _uiSettings.loading = (async () => {
      try {
        const data = await req("/settings");
        const map = {};
        (data.items || []).forEach((x) => { map[x.key] = x.value; });
        const tz = (map.ui_timezone || "").toString().trim();
        _uiSettings.timezone = tz || null;
        _uiSettings.loadedAt = Date.now();
      } catch (_) {
        // ignore - we can fall back to browser timezone
      } finally {
        _uiSettings.loading = null;
      }
    })();
    return _uiSettings.loading;
  }

  function getUiTimezone() {
    return _uiSettings.timezone || (Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  }

  function parseDate(value) {
    if (!value) return null;
    if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
    if (typeof value === "number") return new Date(value);
    const s0 = value.toString().trim();
    if (!s0) return null;
    // Handle sqlite-style "YYYY-MM-DD HH:MM:SS" (treat as UTC)
    let s = s0;
    if (s.includes(" ") && !s.includes("T")) s = s.replace(" ", "T");
    const hasTz =
      s.endsWith("Z") ||
      /[+-]\d{2}:\d{2}$/.test(s) ||
      /[+-]\d{2}\d{2}$/.test(s);
    if (!hasTz) s = `${s}Z`; // If no explicit offset, treat as UTC
    const d = new Date(s);
    if (!isNaN(d.getTime())) return d;
    // Final fallback: try raw string
    const d2 = new Date(s0);
    return isNaN(d2.getTime()) ? null : d2;
  }

  function formatDate(value) {
    const dt = parseDate(value);
    if (!dt) return "-";
    const tz = getUiTimezone();
    try {
      const fmt = new Intl.DateTimeFormat("tr-TR", {
        timeZone: tz,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      return fmt.format(dt);
    } catch (_) {
      return dt.toLocaleString();
    }
  }

  function relTime(value) {
    const dt = parseDate(value);
    if (!dt) return "-";
    const ms = Date.now() - dt.getTime();
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return `${sec}s önce`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}dk önce`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}sa önce`;
    const day = Math.floor(hr / 24);
    return `${day}g önce`;
  }

  function toast(message) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 1700);
  }

  function protectPage() {
    if (!getToken()) {
      window.location.href = "/login";
    }
  }

  window.AppCenterApi = {
    getToken,
    setToken,
    clearToken,
    req,
    initUi,
    getUiTimezone,
    parseDate,
    formatDate,
    relTime,
    toast,
    protectPage,
  };
})();
