(() => {
  const dialog = document.querySelector("#policyDialog");
  const link = document.querySelector(".policy-popup-link");
  if (!dialog || !link || typeof dialog.showModal !== "function") return;

  link.addEventListener("click", event => {
    event.preventDefault();
    dialog.showModal();
  });

  dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  });
})();
