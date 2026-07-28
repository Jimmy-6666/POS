(() => {
  const body = document.body;
  window.LINE_CUSTOMER_CSRF = body.dataset.lineCustomerCsrf || "";
  window.ONLINE_ORDERING_OPEN = body.dataset.orderingOpen === "1";
  window.ORDERING_OPEN = window.ONLINE_ORDERING_OPEN;
})();
