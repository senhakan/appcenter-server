(function () {
  const API_PREFIX = "/api/v1";

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
    toast,
    protectPage,
  };
})();
