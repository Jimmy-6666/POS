(() => {
    const priceSaveForm = document.querySelector("[data-price-save-form]");
    const exactBarcodePriceInput = document.querySelector("[data-exact-barcode-price-input]");
    if (priceSaveForm && exactBarcodePriceInput) {
        let priceSubmitted = false;

        priceSaveForm.addEventListener("submit", event => {
            if (priceSubmitted) {
                event.preventDefault();
                return;
            }
            priceSubmitted = true;
            const submitButton = priceSaveForm.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = "กำลังบันทึก...";
            }
        });

        exactBarcodePriceInput.addEventListener("keydown", event => {
            if (event.key !== "Enter" || event.isComposing) return;
            event.preventDefault();
            if (priceSubmitted || !priceSaveForm.reportValidity()) return;
            priceSaveForm.requestSubmit();
        });
    }

    const createDialog = document.querySelector("[data-price-create-dialog]");
    const createForm = createDialog?.querySelector("[data-price-create-form]");
    const createPriceInput = createDialog?.querySelector("[data-price-create-input]");
    const createPricePanel = createDialog?.querySelector("[data-price-create-price-entry]");
    const createPriceOutput = createDialog?.querySelector("[data-price-create-output]");
    const createDetails = createDialog?.querySelector("[data-price-create-details]");
    const createPriceConfirm = createDialog?.querySelector("[data-price-create-confirm]");
    const createOpenPriceButton = createDialog?.querySelector("[data-price-create-open-numpad]");
    const createNameInput = createDialog?.querySelector("[data-price-create-name]");
    const createCurrentNames = createDialog?.querySelectorAll("[data-price-create-current-name]");
    const createSaveButton = createDialog?.querySelector("#priceMissingProductSave");
    const createClose = createDialog?.querySelector("[data-price-create-close]");
    if (!createDialog || !createForm || !createPriceInput || !createDetails) return;

    const mobileViewport = window.matchMedia("(max-width: 600px)");
    let createSubmitted = false;
    let createPriceAccepted = false;
    let replaceNextDigit = true;

    const createDialogIsModal = () => {
        try {
            return createDialog.matches(":modal");
        } catch (_error) {
            return false;
        }
    };

    const updateCreatePrice = value => {
        createPriceInput.value = value;
        if (createPriceOutput) {
            createPriceOutput.textContent = `${value || "0"} บาท`;
        }
        createPriceInput.dispatchEvent(new Event("input", {bubbles: true}));
    };

    const setCreatePriceEntryOpen = open => {
        if (!createPricePanel) return;
        createPricePanel.hidden = !open;
        createDetails.inert = open;
        createDialog.classList.toggle("quick-price-entry-open", open);
        if (open) {
            replaceNextDigit = true;
            requestAnimationFrame(() => {
                createPricePanel.querySelector("[data-create-price-key]")?.focus({preventScroll: true});
            });
        }
    };

    const syncCreateDialog = () => {
        document.body.classList.add("price-product-create-modal-open");
        if (typeof createDialog.showModal === "function" && !createDialogIsModal()) {
            createDialog.removeAttribute("open");
            createDialog.showModal();
        } else if (!createDialog.open) {
            createDialog.setAttribute("open", "");
        }

        if (mobileViewport.matches) {
            createPriceInput.readOnly = true;
            if (!createPriceAccepted) setCreatePriceEntryOpen(true);
            return;
        }

        createPriceInput.readOnly = false;
        setCreatePriceEntryOpen(false);
        requestAnimationFrame(() => {
            createPriceInput.focus({preventScroll: true});
            createPriceInput.select();
        });
    };

    createPricePanel?.addEventListener("click", event => {
        const button = event.target.closest("button");
        if (!button) return;

        if (button.dataset.createPriceKey !== undefined) {
            const current = createPriceInput.value.replace(/\D/g, "");
            const next = replaceNextDigit
                ? button.dataset.createPriceKey
                : `${current}${button.dataset.createPriceKey}`;
            updateCreatePrice(next.replace(/^0+(?=\d)/, ""));
            replaceNextDigit = false;
        }
        if (button.dataset.createPriceAction === "backspace") {
            updateCreatePrice(createPriceInput.value.replace(/\D/g, "").slice(0, -1));
            replaceNextDigit = false;
        }
        if (button.dataset.createPriceAction === "clear") {
            updateCreatePrice("");
            replaceNextDigit = false;
        }
    });

    createPriceConfirm?.addEventListener("click", () => {
        if (!createPriceInput.value) updateCreatePrice("0");
        createPriceAccepted = true;
        setCreatePriceEntryOpen(false);
        createNameInput?.focus({preventScroll: true});
    });

    const reopenCreatePriceEntry = () => {
        if (!mobileViewport.matches) return;
        createPriceAccepted = false;
        setCreatePriceEntryOpen(true);
    };
    createOpenPriceButton?.addEventListener("click", reopenCreatePriceEntry);
    createPriceInput.addEventListener("click", reopenCreatePriceEntry);

    createNameInput?.addEventListener("input", () => {
        createCurrentNames?.forEach(element => {
            element.textContent = createNameInput.value.trim() || "ยังไม่ได้ระบุชื่อสินค้า";
        });
    });

    createForm.addEventListener("submit", event => {
        if (createSubmitted) {
            event.preventDefault();
            return;
        }
        createSubmitted = true;
        if (createSaveButton) {
            createSaveButton.disabled = true;
            createSaveButton.textContent = "กำลังบันทึก...";
        }
    });

    createDialog.addEventListener("cancel", event => {
        event.preventDefault();
        if (createClose?.href) window.location.assign(createClose.href);
    });
    createDialog.addEventListener("close", () => {
        document.body.classList.remove("price-product-create-modal-open");
    });
    if (typeof mobileViewport.addEventListener === "function") {
        mobileViewport.addEventListener("change", syncCreateDialog);
    } else {
        mobileViewport.addListener(syncCreateDialog);
    }
    syncCreateDialog();
})();
