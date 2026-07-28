(() => {
  const status = document.querySelector("#lineAuthStatus");
  const say = text => { if (status) status.textContent = text; };
  const api = async (path, options = {}) => {
    const response = await fetch(path, { credentials: "same-origin", ...options });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || "ไม่สามารถเชื่อมต่อระบบยืนยันตัวตนได้");
      error.code = data.code;
      throw error;
    }
    return data;
  };
  const loadLiff = () => new Promise((resolve, reject) => {
    if (window.liff) return resolve();
    const script = document.createElement("script");
    script.src = "https://static.line-scdn.net/liff/edge/2/sdk.js";
    script.charset = "utf-8";
    script.onload = resolve;
    script.onerror = () => reject(new Error("ไม่สามารถโหลด LINE LIFF ได้"));
    document.head.append(script);
  });
  const redirectAfterAuth = customer => {
    const current = new URL(window.location.href);
    if (!customer.profileComplete && !current.pathname.endsWith("/profile")) {
      const next = current.pathname === "/order" ? current.searchParams.get("next") : current.pathname + current.search;
      window.location.replace(`/order/profile${next ? `?next=${encodeURIComponent(next)}` : ""}`);
      return true;
    }
    if (current.pathname === "/order" && current.searchParams.get("next")) {
      window.location.replace(current.searchParams.get("next"));
      return true;
    }
    return false;
  };
  const initialize = async () => {
    let config;
    try { config = await api("/api/auth/config"); }
    catch (error) { return say(error.message); }
    if (!config.configured) return say("ร้านยังไม่ได้ตั้งค่า LINE สำหรับสั่งออนไลน์");
    try {
      await loadLiff();
      await window.liff.init({ liffId: config.liffId, withLoginOnExternalBrowser: true });
      if (!window.liff.isLoggedIn()) {
        say("กำลังเปิดหน้าเข้าสู่ระบบ LINE…");
        window.liff.login({ redirectUri: window.location.href });
        return;
      }
      const idToken = window.liff.getIDToken();
      if (!idToken) throw new Error("ไม่ได้รับข้อมูลยืนยันตัวตนจาก LINE กรุณาลองเข้าสู่ระบบใหม่");
      const result = await api("/api/auth/line", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": config.csrfToken },
        body: JSON.stringify({ idToken }),
      });
      window.LINE_CUSTOMER_CSRF = result.csrfToken;
      document.querySelectorAll("#customerCsrf,input[name='csrf_token']").forEach(input => { input.value = result.csrfToken; });
      if (redirectAfterAuth(result.customer)) return;
      say(`สวัสดี ${result.customer.displayName || "ลูกค้า"}`);
    } catch (error) {
      if (error.code === "suspended") {
        window.location.replace("/order/suspended");
        return;
      }
      say(error.message || "ไม่สามารถยืนยันตัวตนผ่าน LINE ได้");
    }
  };
  document.querySelector("#lineLogout")?.addEventListener("click", async () => {
    try {
      await api("/api/auth/logout", { method: "POST", headers: { "X-CSRF-Token": window.LINE_CUSTOMER_CSRF } });
      window.location.replace("/order");
    } catch (error) { alert(error.message); }
  });
  initialize();
})();
