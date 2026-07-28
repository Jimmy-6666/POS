(() => {
  const badge = document.querySelector("#posOnlineOrderBadge");
  const shortcut = document.querySelector("#onlineOrderShortcut");
  const muteButton = document.querySelector("#muteOnlineAlerts");
  const audio = new Audio("/static/audio/order_sound.mp3");
  let muted = localStorage.getItem("onlineOrderMuted") === "1";
  let submittedCount = 0;

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
    if (!badge) return;
    const hasSubmittedOrders = submittedCount > 0;
    badge.textContent = submittedCount;
    badge.hidden = !hasSubmittedOrders;
    shortcut?.classList.toggle("online-order-attention", hasSubmittedOrders);
    shortcut?.setAttribute(
      "aria-label",
      hasSubmittedOrders
        ? `จัดการออเดอร์ออนไลน์ มีออเดอร์ใหม่ ${submittedCount} รายการ`
        : "จัดการออเดอร์ออนไลน์"
    );
  }

  async function poll() {
    try {
      const response = await fetch("/online-orders/api/summary");
      if (!response.ok) return;
      const data = await response.json();
      submittedCount = Number(data.new_count) || 0;
      updateBadge();
      if (submittedCount) startAlert();
      else stopAlert();
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
  poll();
  setInterval(poll, 15000);
})();
