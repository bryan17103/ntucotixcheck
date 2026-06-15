let ORDER_OPEN = true;
let seatData = [];
let rowLabels = {};
let selectedSeats = new Set();
let zoomLevel = window.innerWidth <= 900 ? 1.25 : 1.0;

let seatMapBaseWidth = 0;
let seatMapBaseHeight = 0;

const SECOND_FLOOR_START_ROW = 33; 
async function loadSeats(showLoading = true) {
    const loadingOverlay = document.getElementById("loading-overlay");

    try {
        if (showLoading) {
            loadingOverlay?.classList.remove("hidden");
        }

        const res = await fetch("/api/tp/seats");
        const data = await res.json();

        seatData = data.seats || [];

        ORDER_OPEN = data.order_open !== false;

        updateOrderOpenUI();
        renderSeats();
        updateSummary();
        applyZoom();
        enableDragScroll();

    } catch (err) {
        console.error(err);

    } finally {
        if (showLoading) {
            loadingOverlay?.classList.add("hidden");
        }
    }
}

function getSeatId(seat) {
    return seat.seat_id || `${seat.excel_row}-${seat.excel_col}`;
}

function zoneDisplayName(zone) {
    const map = {
        "group-500": "團內購票 500 元區",
        "group-300": "團內購票 300 元區",
        "group-200": "團內購票 200 元區",

        "regular-500": "500 元區",
        "regular-300": "300 元區",
        "regular-200": "200 元區",

        "wheelchair": "輪椅席",
        "companion": "輪椅陪同席",

        "staff": "館方工作席",
        "camera": "攝影席",
        "vip": "貴賓席",

        "unknown": "未分類"
    };

    return map[zone] || `未知(${zone})`;
}

function formatMoney(value) {
    return `$${value}`;
}

function isSecondFloorSeat(seat) {
    return seat.excel_row >= SECOND_FLOOR_START_ROW;
}

function getFloorLabel(seat) {
    return isSecondFloorSeat(seat) ? "2樓" : "1樓";
}

function applyZoom() {
    const seatMap = document.getElementById("seat-map");
    const scaleWrap = document.getElementById("seat-map-scale");
    if (!seatMap || !scaleWrap) return;

    seatMap.style.transform = `scale(${zoomLevel})`;
    seatMap.style.transformOrigin = "top left";

    if (!seatMapBaseWidth || !seatMapBaseHeight) {
        const rect = seatMap.getBoundingClientRect();
        seatMapBaseWidth = rect.width / zoomLevel;
        seatMapBaseHeight = rect.height / zoomLevel;
    }

    scaleWrap.style.width = `${seatMapBaseWidth * zoomLevel}px`;
    scaleWrap.style.height = `${seatMapBaseHeight * zoomLevel}px`;
}

function setupZoomControls() {
    const zoomInBtn = document.getElementById("zoom-in-btn");
    const zoomOutBtn = document.getElementById("zoom-out-btn");

    if (zoomInBtn && !zoomInBtn.dataset.bound) {
        zoomInBtn.dataset.bound = "true";
        zoomInBtn.addEventListener("click", () => {
            zoomLevel = Math.min(2.0, zoomLevel + 0.1);
            applyZoom();
        });
    }

    if (zoomOutBtn && !zoomOutBtn.dataset.bound) {
        zoomOutBtn.dataset.bound = "true";
        zoomOutBtn.addEventListener("click", () => {
            zoomLevel = Math.max(0.45, zoomLevel - 0.1);
            applyZoom();
        });
    }
}

function showSeatTooltip(event, seat, message = null) {
    const tooltip = document.getElementById("seat-tooltip");
    const viewport = document.getElementById("map-viewport");
    if (!tooltip || !viewport) return;

    const floorText = getFloorLabel(seat);
    const rowText = seat.row_label ? `${seat.row_label}排` : "";
    const title = message || `${floorText} ${rowText}${seat.seat_number}號`;
    const sub =
        `${zoneDisplayName(seat.zone)} / ${formatMoney(seat.price)}`;

    tooltip.innerHTML = `
        <div class="tooltip-title">${title}</div>
        <div class="tooltip-sub">${sub}</div>
    `;

    const rect = viewport.getBoundingClientRect();
    const x = event.clientX - rect.left + viewport.scrollLeft;
    const y = event.clientY - rect.top + viewport.scrollTop;

    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
    tooltip.classList.remove("hidden");
}

function moveSeatTooltip(event) {
    const tooltip = document.getElementById("seat-tooltip");
    const viewport = document.getElementById("map-viewport");
    if (!tooltip || !viewport || tooltip.classList.contains("hidden")) return;

    const rect = viewport.getBoundingClientRect();
    const x = event.clientX - rect.left + viewport.scrollLeft;
    const y = event.clientY - rect.top + viewport.scrollTop;

    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
}

function hideSeatTooltip() {
    const tooltip = document.getElementById("seat-tooltip");
    if (!tooltip) return;
    tooltip.classList.add("hidden");
}

function toggleSeat(seatId, btn) {
    if (selectedSeats.has(seatId)) {
        selectedSeats.delete(seatId);
        btn.classList.remove("selected");
    } else {
        selectedSeats.add(seatId);
        btn.classList.add("selected");
    }

    updateSummary();
}

function updateSummary() {
    const selectedList = document.getElementById("selected-list");
    const zoneSummary = document.getElementById("zone-summary");
    const summary = document.getElementById("summary");

    if (!selectedList || !zoneSummary || !summary) return;

    const picked = seatData.filter(seat => selectedSeats.has(getSeatId(seat)));

    if (picked.length === 0) {
        selectedList.innerHTML = "尚未選擇";
        zoneSummary.innerHTML = "尚未選擇";
        summary.innerHTML = "總金額：$0";
        return;
    }

    let total = 0;
    const zoneCounts = {};

    const listHtml = picked.map(seat => {
        total += seat.price;
        zoneCounts[seat.zone] = (zoneCounts[seat.zone] || 0) + 1;

        const floorText = getFloorLabel(seat);
        const rowText = seat.row_label ? `${seat.row_label}排` : "";
        return `<div class="selected-seat-item">${floorText}${rowText}${seat.seat_number}號<span> ${zoneDisplayName(seat.zone)} / $${seat.price}</span></div>`;


    }).join("");

    const zonePriceMap = {
        "group-500": 400,
        "group-300": 240,
        "group-200": 160,
    
        "regular-500": 500,
        "regular-300": 300,
        "regular-200": 200
    };
    
    const zoneHtml = Object.entries(zoneCounts).map(([zone, count]) => {
        const price = zonePriceMap[zone];
    
        return `
            <div class="zone-summary-item">
                <span class="zone-name">
                    ${zoneDisplayName(zone)}
                    ${price ? ` / $${price}` : ""}
                </span>
    
                <span class="zone-count">${count} 張</span>
            </div>
        `;
    }).join("");

    selectedList.innerHTML = listHtml;
    zoneSummary.innerHTML = zoneHtml;
    summary.innerHTML = `已選 ${picked.length} 位，總金額：${formatMoney(total)}`;
}

function renderSeats() {
    const seatMap = document.getElementById("seat-map");
    if (!seatMap) return;

    seatMap.innerHTML = "";

    if (seatData.length === 0) return;

    const minCol = Math.min(...seatData.map(s => s.excel_col));
    const maxCol = Math.max(...seatData.map(s => s.excel_col));
    const minRow = Math.min(...seatData.map(s => s.excel_row));
    const maxRow = Math.max(...seatData.map(s => s.excel_row));

    const totalCols = (maxCol - minCol + 1) + 2;

    const TOP_TITLE_OFFSET = 1;
    const totalRows = (maxRow - minRow + 1) + TOP_TITLE_OFFSET;

    const gridColSize = 28;
    const gridRowSize = 24;

    seatMap.style.gridTemplateColumns =
        `${gridColSize}px repeat(${maxCol - minCol + 1}, ${gridColSize}px) ${gridColSize}px`;

    seatMap.style.gridTemplateRows =
        `repeat(${totalRows}, ${gridRowSize}px)`;

    const firstFloorSeats = seatData.filter(seat => !isSecondFloorSeat(seat));
    const secondFloorSeats = seatData.filter(seat => isSecondFloorSeat(seat));

    // 1樓標題
    if (firstFloorSeats.length > 0) {
        const floor1 = document.createElement("div");
        floor1.className = "floor-label";
        floor1.textContent = "1樓";
        floor1.style.gridColumn = `1 / ${totalCols + 1}`;
        floor1.style.gridRow = 1;
        seatMap.appendChild(floor1);
    }

    // 左右排數
    Object.entries(rowLabels).forEach(([excelRow, label]) => {
        const displayRow = (Number(excelRow) - minRow + 1) + TOP_TITLE_OFFSET;

        const left = document.createElement("div");
        left.className = "row-label";
        left.textContent = label;
        left.style.gridColumn = 1;
        left.style.gridRow = displayRow;
        seatMap.appendChild(left);

        const right = document.createElement("div");
        right.className = "row-label";
        right.textContent = label;
        right.style.gridColumn = totalCols;
        right.style.gridRow = displayRow;
        seatMap.appendChild(right);
    });

    // 2樓標題
    if (secondFloorSeats.length > 0) {
        const secondFloorTopExcelRow = Math.min(...secondFloorSeats.map(seat => seat.excel_row));
        let secondFloorTitleRow = (secondFloorTopExcelRow - minRow) + TOP_TITLE_OFFSET;

        if (secondFloorTitleRow < 2) {
            secondFloorTitleRow = 2;
        }

        const floor2 = document.createElement("div");
        floor2.className = "floor-label";
        floor2.textContent = "2樓";
        floor2.style.gridColumn = `1 / ${totalCols + 1}`;
        floor2.style.gridRow = secondFloorTitleRow;
        seatMap.appendChild(floor2);
    }

    // 座位 
    seatData.forEach(seat => {
        const btn = document.createElement("button");
        const seatId = getSeatId(seat);

        btn.className = `seat ${seat.zone}`;
        btn.textContent = seat.seat_number;
        btn.type = "button";

        btn.style.gridColumn = seat.excel_col - minCol + 2;
        btn.style.gridRow = (seat.excel_row - minRow + 1) + TOP_TITLE_OFFSET;

        // 已售 
        if (seat.sold) {
            btn.classList.add("sold");
            btn.disabled = true;

            btn.addEventListener("mouseenter", (e) => {
                showSeatTooltip(e, seat, "此座位已售出");
            });
            btn.addEventListener("mousemove", moveSeatTooltip);
            btn.addEventListener("mouseleave", hideSeatTooltip);

        //  不可購 
        } else if (!seat.available) {
            btn.disabled = true;

            btn.addEventListener("mouseenter", (e) => {
                showSeatTooltip(e, seat, "此區域不開放團內購票");
            });
            btn.addEventListener("mousemove", moveSeatTooltip);
            btn.addEventListener("mouseleave", hideSeatTooltip);

        // 可選
        } else {
            btn.addEventListener("click", () => {
                const viewport = document.getElementById("map-viewport");
                if (viewport && viewport.dataset.justDragged === "true") return;
                toggleSeat(seatId, btn);
            });

            btn.addEventListener("mouseenter", (e) => {
                showSeatTooltip(e, seat);
            });
            btn.addEventListener("mousemove", moveSeatTooltip);
            btn.addEventListener("mouseleave", hideSeatTooltip);
        }

        if (selectedSeats.has(seatId)) {
            btn.classList.add("selected");
        }

        seatMap.appendChild(btn);
    });

    seatMapBaseWidth = seatMap.offsetWidth;
    seatMapBaseHeight = seatMap.offsetHeight;
}

function enableDragScroll() {
    const viewport = document.getElementById("map-viewport");
    if (!viewport) return;

    if (viewport.dataset.dragBound === "true") return;
    viewport.dataset.dragBound = "true";
    viewport.dataset.justDragged = "false";

    let isDown = false;
    let startX = 0;
    let startY = 0;
    let startScrollLeft = 0;
    let startScrollTop = 0;

    viewport.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;

        isDown = true;
        viewport.classList.add("dragging");

        startX = e.clientX;
        startY = e.clientY;
        startScrollLeft = viewport.scrollLeft;
        startScrollTop = viewport.scrollTop;
        viewport.dataset.justDragged = "false";
    });

    window.addEventListener("mousemove", (e) => {
        if (!isDown) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
            viewport.dataset.justDragged = "true";
        }

        viewport.scrollLeft = startScrollLeft - dx;
        viewport.scrollTop = startScrollTop - dy;
    });

    window.addEventListener("mouseup", () => {
        if (!isDown) return;

        isDown = false;
        viewport.classList.remove("dragging");

        setTimeout(() => {
            viewport.dataset.justDragged = "false";
        }, 80);
    });
}

function setupConfirmButton() {
    const confirmBtn = document.getElementById("confirm-btn");
    if (!confirmBtn || confirmBtn.dataset.bound === "true") return;

    confirmBtn.dataset.bound = "true";

    confirmBtn.addEventListener("click", async () => {
        if (!ORDER_OPEN) {
            alert("團內購票已截止，無法新增訂單！");
            return;
        }
        
        if (selectedSeats.size === 0) {
            alert("請先選擇座位");
            return;
        }

        const name = await askBuyerName();
        if (!name) return;

        const note = await askOrderNote();
        if (note === null) return;

        const res = await fetch("/api/tp/confirm", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                name: name,
                note: note,
                seats: Array.from(selectedSeats)
            })
        });

        const data = await res.json();

        if (data.success) {
            showSuccessModal(
                "購票成功！",
                data.message || "訂單已成立，請記得截圖保存～"
            );
        
            selectedSeats.clear();
            loadSeats(false);
        
        } else {
            showSuccessModal(
                "發生錯誤",
                data.message || "發生錯誤"
            );
        }
    });
}

const nameModal = document.getElementById("name-modal");
const buyerNameInput = document.getElementById("buyer-name-input");
const nameCancelBtn = document.getElementById("name-cancel-btn");
const nameConfirmBtn = document.getElementById("name-confirm-btn");
const successModal = document.getElementById("success-modal");
const successCloseBtn = document.getElementById("success-close-btn");
const successConfirmBtn = document.getElementById("success-confirm-btn");
const successTitle = document.getElementById("success-title");
const successMessage = document.getElementById("success-message");

function askBuyerName() {
    return new Promise((resolve) => {

        if (!nameModal) {
            resolve(null);
            return;
        }

        buyerNameInput.value = "";

        nameModal.classList.remove("hidden");

        setTimeout(() => {
            buyerNameInput.focus();
        }, 30);

        function cleanup() {
            nameModal.classList.add("hidden");

            nameCancelBtn.removeEventListener("click", handleCancel);
            nameConfirmBtn.removeEventListener("click", handleConfirm);
            buyerNameInput.removeEventListener("keydown", handleKeydown);
        }

        function handleCancel() {
            cleanup();
            resolve(null);
        }

        function handleConfirm() {
            const name = buyerNameInput.value.trim();

            if (!name) {
                buyerNameInput.focus();
                return;
            }

            cleanup();
            resolve(name);
        }

        function handleKeydown(e) {
            if (e.key === "Enter") {
                handleConfirm();
            }
        }

        nameCancelBtn.addEventListener("click", handleCancel);
        nameConfirmBtn.addEventListener("click", handleConfirm);
        buyerNameInput.addEventListener("keydown", handleKeydown);
    });
}

function askOrderNote() {
    return new Promise((resolve) => {
        if (!nameModal) {
            resolve("");
            return;
        }

        const title = nameModal.querySelector("h2");
        const desc = nameModal.querySelector("p");

        const oldTitle = title ? title.textContent : "";
        const oldDesc = desc ? desc.textContent : "";
        const oldPlaceholder = buyerNameInput.getAttribute("placeholder") || "";
        const oldMaxLength = buyerNameInput.getAttribute("maxlength");

        if (title) title.textContent = "訂單備註";
        if (desc) desc.textContent = "例如這張票是誰的";

        buyerNameInput.value = "";
        buyerNameInput.placeholder = "(選填)";
        buyerNameInput.removeAttribute("maxlength");

        nameModal.classList.remove("hidden");

        setTimeout(() => {
            buyerNameInput.focus();
        }, 30);

        function restoreModalText() {
            if (title) title.textContent = oldTitle;
            if (desc) desc.textContent = oldDesc;
            buyerNameInput.placeholder = oldPlaceholder;

            if (oldMaxLength !== null) {
                buyerNameInput.setAttribute("maxlength", oldMaxLength);
            }
        }

        function cleanup() {
            nameModal.classList.add("hidden");
            restoreModalText();

            nameCancelBtn.removeEventListener("click", handleCancel);
            nameConfirmBtn.removeEventListener("click", handleConfirm);
            buyerNameInput.removeEventListener("keydown", handleKeydown);
        }

        function handleCancel() {
            cleanup();
            resolve(null);
        }

        function handleConfirm() {
            const note = buyerNameInput.value.trim();
            cleanup();
            resolve(note);
        }

        function handleKeydown(e) {
            if (e.key === "Enter") {
                handleConfirm();
            }
        }

        nameCancelBtn.addEventListener("click", handleCancel);
        nameConfirmBtn.addEventListener("click", handleConfirm);
        buyerNameInput.addEventListener("keydown", handleKeydown);
    });
}



function showSuccessModal(title, message) {
    if (!successModal) return;

    successTitle.textContent = title || "成功";
    successMessage.textContent = message || "";

    successModal.classList.remove("hidden");
}

function closeSuccessModal() {
    if (!successModal) return;
    successModal.classList.add("hidden");
}

successCloseBtn?.addEventListener("click", closeSuccessModal);
successConfirmBtn?.addEventListener("click", closeSuccessModal);

successModal?.addEventListener("click", (e) => {
    if (e.target === successModal) {
        closeSuccessModal();
    }
});

function updateOrderOpenUI() {
    const confirmBtn = document.getElementById("confirm-btn");
    if (!confirmBtn) return;

    if (!ORDER_OPEN) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = "團內購票已截止";
    } else {
        confirmBtn.disabled = false;
        confirmBtn.textContent = "確認選位";
    }
}

document.getElementById("clear-selection-btn")
?.addEventListener("click", () => {
    selectedSeats.clear();

    renderSeats();
    updateSummary();
});

setupZoomControls();
setupConfirmButton();
loadSeats();
