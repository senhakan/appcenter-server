(function () {
  const API_PREFIX = "/api/v1";
  const UI_SETTINGS_CACHE_TTL_MS = 5 * 60 * 1000; // refresh occasionally so settings changes apply without reload
  const SESSION_WARNING_SECONDS = 30;

  let _sessionWarnTimer = null;
  let _sessionExpireTimer = null;
  let _sessionCountdownTimer = null;
  let _sessionCountdownValue = SESSION_WARNING_SECONDS;
  let _sessionModalBound = false;
  let _sessionExtending = false;
  let _currentUser = null;
  let _currentUserLoading = null;
  const ROLE_WEIGHTS = { viewer: 10, operator: 20, admin: 30 };

  function getToken() {
    return localStorage.getItem("appcenter_token") || "";
  }

  function setToken(token) {
    localStorage.setItem("appcenter_token", token);
    scheduleSessionTimers();
  }

  function clearToken() {
    localStorage.removeItem("appcenter_token");
    _currentUser = null;
    _currentUserLoading = null;
    clearSessionTimers();
    hideSessionModal();
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
      forceLogout();
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
    if (sec < 60) return `${sec} sn önce`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min} dk önce`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr} saat önce`;
    const day = Math.floor(hr / 24);
    return `${day} gün önce`;
  }

  function toast(message) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 1700);
  }

  function clearSessionTimers() {
    if (_sessionWarnTimer) {
      clearTimeout(_sessionWarnTimer);
      _sessionWarnTimer = null;
    }
    if (_sessionExpireTimer) {
      clearTimeout(_sessionExpireTimer);
      _sessionExpireTimer = null;
    }
    if (_sessionCountdownTimer) {
      clearInterval(_sessionCountdownTimer);
      _sessionCountdownTimer = null;
    }
  }

  function decodeJwtPayload(token) {
    const parts = (token || "").split(".");
    if (parts.length < 2) return null;
    try {
      const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const padded = b64.padEnd(Math.ceil(b64.length / 4) * 4, "=");
      return JSON.parse(atob(padded));
    } catch (_) {
      return null;
    }
  }

  function getTokenExpiryMs(token) {
    const payload = decodeJwtPayload(token);
    if (!payload || !payload.exp) return null;
    const exp = Number(payload.exp);
    if (!Number.isFinite(exp) || exp <= 0) return null;
    return exp * 1000;
  }

  function getSessionModalElements() {
    return {
      modal: document.getElementById("session-timeout-modal"),
      card: document.querySelector("#session-timeout-modal .session-modal-card"),
      countdown: document.getElementById("session-timeout-countdown"),
      continueBtn: document.getElementById("session-continue-btn"),
      logoutBtn: document.getElementById("session-logout-btn"),
    };
  }

  function renderSessionCountdown() {
    const { card, countdown } = getSessionModalElements();
    const isCritical = _sessionCountdownValue <= 10;
    if (card) card.classList.toggle("critical", isCritical);
    if (countdown) countdown.textContent = String(Math.max(0, _sessionCountdownValue));
    if (countdown) countdown.classList.toggle("critical", isCritical);
  }

  function hideSessionModal() {
    const { modal, card, countdown } = getSessionModalElements();
    if (!modal) return;
    modal.classList.add("hidden");
    if (card) card.classList.remove("critical");
    if (countdown) countdown.classList.remove("critical");
  }

  function showSessionModal() {
    const { modal, continueBtn } = getSessionModalElements();
    if (!modal) return;
    _sessionCountdownValue = SESSION_WARNING_SECONDS;
    renderSessionCountdown();
    modal.classList.remove("hidden");
    if (continueBtn) continueBtn.focus();
    if (_sessionCountdownTimer) clearInterval(_sessionCountdownTimer);
    _sessionCountdownTimer = setInterval(() => {
      _sessionCountdownValue -= 1;
      renderSessionCountdown();
      if (_sessionCountdownValue <= 0) {
        clearInterval(_sessionCountdownTimer);
        _sessionCountdownTimer = null;
      }
    }, 1000);
  }

  function forceLogout() {
    clearSessionTimers();
    hideSessionModal();
    localStorage.removeItem("appcenter_token");
    _currentUser = null;
    _currentUserLoading = null;
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }

  function normalizeRole(raw) {
    const role = (raw || "").toString().trim().toLowerCase();
    if (role === "admin" || role === "operator" || role === "viewer") return role;
    return "viewer";
  }

  function getCurrentRole() {
    return normalizeRole(_currentUser && _currentUser.role ? _currentUser.role : "viewer");
  }

  function roleAllowed(role, allowedCsv) {
    const allowed = (allowedCsv || "")
      .toString()
      .split(",")
      .map((x) => x.trim().toLowerCase())
      .filter(Boolean);
    if (!allowed.length) return true;
    return allowed.includes(role);
  }

  function canAny(roles) {
    const normalized = getCurrentRole();
    const allowed = Array.isArray(roles) ? roles : [roles];
    return allowed
      .map((r) => normalizeRole(r))
      .some((r) => r === normalized);
  }

  function canAtLeast(minRole) {
    const currentWeight = ROLE_WEIGHTS[getCurrentRole()] || 0;
    const minWeight = ROLE_WEIGHTS[normalizeRole(minRole)] || 0;
    return currentWeight >= minWeight;
  }

  function applyNavPermissions(role) {
    const resolvedRole = normalizeRole(role);
    document.body.setAttribute("data-user-role", resolvedRole);

    document.querySelectorAll("[data-nav-item]").forEach((el) => {
      const allowedCsv = el.getAttribute("data-roles") || "";
      el.hidden = !roleAllowed(resolvedRole, allowedCsv);
    });

    document.querySelectorAll(".nav-dropdown").forEach((dropdown) => {
      if (dropdown.hidden) return;
      const visibleChildren = dropdown.querySelectorAll(".nav-submenu [data-nav-item]:not([hidden])");
      if (visibleChildren.length === 0) dropdown.hidden = true;
    });
  }

  function applyRoleControls(role) {
    const resolvedRole = normalizeRole(role);
    document.querySelectorAll("[data-required-roles]").forEach((el) => {
      const allowedCsv = el.getAttribute("data-required-roles") || "";
      const visible = roleAllowed(resolvedRole, allowedCsv);
      el.hidden = !visible;
      if (!visible && (el instanceof HTMLInputElement || el instanceof HTMLButtonElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement)) {
        el.disabled = true;
      }
    });
  }

  async function getCurrentUser(force) {
    if (!getToken()) return null;
    if (!force && _currentUser) return _currentUser;
    if (_currentUserLoading) return _currentUserLoading;
    _currentUserLoading = (async () => {
      try {
        const me = await req("/auth/me");
        _currentUser = me || null;
      } catch (_) {
        _currentUser = null;
      } finally {
        _currentUserLoading = null;
      }
      return _currentUser;
    })();
    return _currentUserLoading;
  }

  async function extendSession() {
    if (_sessionExtending) return;
    _sessionExtending = true;
    const { continueBtn } = getSessionModalElements();
    if (continueBtn) continueBtn.disabled = true;
    try {
      const res = await fetch(`${API_PREFIX}/auth/extend`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
      });
      if (!res.ok) throw new Error("Session extend failed");
      const data = await res.json();
      if (!data.access_token) throw new Error("Session extend failed");
      setToken(data.access_token);
      hideSessionModal();
      toast("Oturum suresi uzatildi");
    } catch (_) {
      forceLogout();
    } finally {
      _sessionExtending = false;
      if (continueBtn) continueBtn.disabled = false;
    }
  }

  function bindSessionModalOnce() {
    if (_sessionModalBound) return;
    const { continueBtn, logoutBtn } = getSessionModalElements();
    if (!continueBtn || !logoutBtn) return;
    continueBtn.addEventListener("click", () => {
      extendSession();
    });
    logoutBtn.addEventListener("click", () => {
      forceLogout();
    });
    document.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter") return;
      const { modal } = getSessionModalElements();
      if (!modal || modal.classList.contains("hidden")) return;
      evt.preventDefault();
      extendSession();
    });
    _sessionModalBound = true;
  }

  function scheduleSessionTimers() {
    clearSessionTimers();
    bindSessionModalOnce();
    const token = getToken();
    if (!token) return;

    const expiryMs = getTokenExpiryMs(token);
    if (!expiryMs) return;

    const now = Date.now();
    const remainingMs = expiryMs - now;
    if (remainingMs <= 0) {
      forceLogout();
      return;
    }

    const warningMs = SESSION_WARNING_SECONDS * 1000;
    const warnInMs = remainingMs - warningMs;
    if (warnInMs <= 0) {
      showSessionModal();
    } else {
      _sessionWarnTimer = setTimeout(() => {
        showSessionModal();
      }, warnInMs);
    }

    _sessionExpireTimer = setTimeout(() => {
      forceLogout();
    }, remainingMs);
  }

  async function protectPage() {
    if (!getToken()) {
      window.location.href = "/login";
      return;
    }
    scheduleSessionTimers();
    const me = await getCurrentUser();
    if (me && me.role) {
      applyNavPermissions(me.role);
      applyRoleControls(me.role);
    } else {
      applyNavPermissions("viewer");
      applyRoleControls("viewer");
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
    getCurrentUser,
    applyNavPermissions,
    getCurrentRole,
    canAny,
    canAtLeast,
    protectPage,
  };
})();
