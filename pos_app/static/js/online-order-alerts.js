(() => {
  const alertPages = new Set(["pos.index", "online_staff.index"]);
  if (!alertPages.has(document.body.dataset.endpoint)) return;

  const badges = [...document.querySelectorAll(".online-order-badge")];
  const shortcut = document.querySelector("#onlineOrderShortcut");
  const pageHeading = document.querySelector("#onlineOrdersPageHeading");
  const muteButton = document.querySelector("#muteOnlineAlerts");
  const isOrderList = document.body.dataset.endpoint === "online_staff.index";
  const audio = new Audio("/static/audio/order_sound.mp3");
  let cachedState = {};
  try {
    cachedState = JSON.parse(sessionStorage.getItem("onlineOrderAlertState") || "{}");
  } catch {
    // A malformed browser cache must not disable order alerts.
  }
  const navigationGestureAt = Number(sessionStorage.getItem("onlineOrderAlertNavigationGesture")) || 0;
  const hasRecentNavigationGesture = Date.now() - navigationGestureAt < 10000;
  let muted = localStorage.getItem("onlineOrderMuted") === "1";
  let submittedCount = Date.now() - Number(cachedState.updatedAt) < 60000 ? Number(cachedState.count) || 0 : 0;
  let latestId = null;

  audio.loop = true;
  audio.preload = "auto";

  function updateMuteButton() {
    if (muteButton) {
      muteButton.textContent = muted ? "เปิดเสียงแจ้งเตือน" : "ปิดเสียงแจ้งเตือน";
    }
  }

  function stopAlert() {
    audio.pause();
    audio.currentTime = 0;
  }

  function startAlert() {
    if (muted || !submittedCount || !audio.paused) return;
    audio.play().catch(() => {
      // Browsers require a tap or key press before audible playback.
    });
  }

  function updateBadge() {
    const hasSubmittedOrders = submittedCount > 0;
    badges.forEach((badge) => {
      badge.textContent = submittedCount;
      badge.hidden = !hasSubmittedOrders;
    });
    [shortcut, pageHeading].forEach((target) => target?.classList.toggle("online-order-attention", hasSubmittedOrders));
    shortcut?.setAttribute(
      "aria-label",
      hasSubmittedOrders
        ? `จัดการออเดอร์ออนไลน์ มีออเดอร์ใหม่ ${submittedCount} รายการ`
        : "จัดการออเดอร์ออนไลน์"
    );
  }

  function cacheAlertState() {
    sessionStorage.setItem("onlineOrderAlertState", JSON.stringify({ count: submittedCount, updatedAt: Date.now() }));
  }

  function refreshListForNewOrder(previousLatestId, nextLatestId) {
    if (!isOrderList || previousLatestId === null || nextLatestId <= previousLatestId) return;
    startAlert();
    window.setTimeout(() => window.location.reload(), 250);
  }

  async function poll() {
    try {
      const response = await fetch("/online-orders/api/summary");
      if (!response.ok) return;
      const data = await response.json();
      const nextLatestId = Number(data.latest_id) || 0;
      const previousLatestId = latestId;
      submittedCount = Number(data.new_count) || 0;
      updateBadge();
      cacheAlertState();
      if (submittedCount) startAlert();
      else stopAlert();
      refreshListForNewOrder(previousLatestId, nextLatestId);
      latestId = nextLatestId;
    } catch {
      // Keep the previous local state if the POS is temporarily unavailable.
    }
  }

  function retryAfterUserGesture() {
    if (submittedCount) startAlert();
  }

  muteButton?.addEventListener("click", (event) => {
    muted = !muted;
    localStorage.setItem("onlineOrderMuted", muted ? "1" : "0");
    if (muted) stopAlert();
    else startAlert();
    updateMuteButton();
    event.currentTarget.blur();
  });
  document.addEventListener("pointerdown", retryAfterUserGesture, { passive: true });
  document.addEventListener("keydown", retryAfterUserGesture);

  updateMuteButton();
  updateBadge();
  if (hasRecentNavigationGesture && submittedCount) startAlert();
  poll();
  setInterval(poll, 15000);
})();
