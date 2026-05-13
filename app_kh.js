const SHOW_KH_THIRD_FLOOR = false;

let ORDER_OPEN = true;
let seatData = [];
let selectedSeats = new Set();
let zoomLevel = window.innerWidth <= 900 ? 1.15 : 0.9;

let seatMapBaseWidth = 0;
let seatMapBaseHeight = 0;

async function loadSeats() {
    const res = await fetch("/api/kh/seats");
    const data = await res.json();

    seatData = (data.seats || []).filter(seat => {
        if (SHOW_KH_THIRD_FLOOR) return true;
        return seat.floor !== "3樓";
    });

    ORDER_OPEN = data.order_open !== false;

    updateOrderOpenUI();
    renderSeats();
    updateSummary();
    applyZoom();
    enableDragScroll();
}

function getSeatId(seat) {
    return seat.seat_id || `${seat.excel_row}-${seat.excel_col}`;
}

function zoneDisplayName(zone) {
    const map = {
        "group-800": "團內購票 800 元區",
        "group-500": "團內購票 500 元區",
        "group-300": "團內購票 300 元區",
        "group-200": "團內購票 200 元區",

        "regular-800": "800 元區",
        "regular-500": "500 元區",
        "regular-300": "300 元區",
        "regular-200": "200 元區",

        "wheelchair": "輪椅席",
        "companion": "輪椅陪同席",
        "staff": "館方工作席",
        "camera": "攝影席",
        "vip": "貴賓席",
        "notopen": "視線不良/不開放",
        "unknown": "未分類"
    };

    return map[zone] || `未知(${zone})`;
}

function formatMoney(value) {
    return `$${value}`;
}

function getFloorLabel(seat) {
    return seat.floor || "";
}

function colIndex(col) {
    let n = 0;
    for (let i = 0; i < col.length; i++) {
        n = n * 26 + (col.charCodeAt(i) - 64);
    }
    return n;
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
    const sub = `${zoneDisplayName(seat.zone)} / ${formatMoney(seat.price)}`;

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

        return `
            <div class="selected-seat-item">
                ${floorText}${rowText}${seat.seat_number}號
                <span> ${zoneDisplayName(seat.zone)} / $${seat.price}</span>
            </div>
        `;
    }).join("");

    const zonePriceMap = {
        "group-800": 640,
        "group-500": 400,
        "group-300": 240,
        "group-200": 160,
        "regular-800": 800,
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

/* ---------- 高雄場地圖元素 ---------- */

function addKhStage(seatMap, minCol, minRow, topOffset) {
    const stage = document.createElement("div");
    stage.className = "stage-box map-stage kh-stage";
    stage.textContent = "舞台";

    stage.style.gridColumn =
        `${colIndex("AJ") - minCol + 2} / ${colIndex("BV") - minCol + 3}`;
    stage.style.gridRow =
        `${35 - minRow + 1 + topOffset} / ${41 - minRow + 2 + topOffset}`;

    seatMap.appendChild(stage);
}

function addFloorFrame(seatMap, minCol, minRow, topOffset, label, startCol, endCol, startRow, endRow, className) {
    const frame = document.createElement("div");
    frame.className = `kh-floor-frame ${className}`;

    frame.style.gridColumn =
        `${colIndex(startCol) - minCol + 2} / ${colIndex(endCol) - minCol + 3}`;
    frame.style.gridRow =
        `${startRow - minRow + 1 + topOffset} / ${endRow - minRow + 2 + topOffset}`;

    const tag = document.createElement("div");
    tag.className = "kh-floor-tag";
    tag.textContent = label;

    frame.appendChild(tag);
    seatMap.appendChild(frame);
}

function addSingleMarker(seatMap, minCol, minRow, topOffset, col, row, text, extraClass = "") {
    const marker = document.createElement("div");
    marker.className = `row-label kh-row-marker ${extraClass}`;
    marker.textContent = text;

    marker.style.gridColumn = colIndex(col) - minCol + 2;
    marker.style.gridRow = row - minRow + 1 + topOffset;

    seatMap.appendChild(marker);
}

function addHorizontalRowMarker(seatMap, minCol, minRow, topOffset, leftCol, rightCol, row, text) {
    addSingleMarker(seatMap, minCol, minRow, topOffset, leftCol, row, text, "kh-horizontal-marker");
    addSingleMarker(seatMap, minCol, minRow, topOffset, rightCol, row, text, "kh-horizontal-marker");
}

function addVerticalRowMarker(seatMap, minCol, minRow, topOffset, col, startRow, endRow, text) {
    addSingleMarker(seatMap, minCol, minRow, topOffset, col, startRow - 1, text, "kh-vertical-marker");
    addSingleMarker(seatMap, minCol, minRow, topOffset, col, endRow + 1, text, "kh-vertical-marker");
}

function addKhRowMarkers(seatMap, minCol, minRow, topOffset) {
    // 一樓：橫排，正常每排顯示
    for (let r = 44; r <= 55; r++) {
        const label = String(r - 43);

        ["AI", "AT", "AV", "BI", "BK"].forEach(col => {
            addSingleMarker(seatMap, minCol, minRow, topOffset, col, r, label, "kh-first-floor-marker");
        });
    }

    // 二樓：直排，只顯示上下，避免壓座位
    const secondFloorVerticalMarkers = [
        ["T", 42, 50, "E3"],
        ["U", 35, 52, "E2"],
        ["V", 25, 57, "E1"],
        ["V", 61, 77, "C1"],
        ["T", 75, 78, "C2"],

        ["Y", 33, 55, "D4"],
        ["Z", 31, 55, "D3"],
        ["AB", 34, 54, "D2"],
        ["AC", 37, 53, "D1"],

        ["CB", 37, 53, "D1"],
        ["CC", 34, 54, "D2"],
        ["CE", 31, 55, "D3"],
        ["CF", 33, 55, "D4"],

        ["CI", 25, 57, "E1"],
        ["CJ", 35, 52, "E2"],
        ["CK", 33, 51, "E3"],
        ["CH", 61, 77, "C1"],
        ["CJ", 74, 78, "C2"],
    ];

    // 二樓：橫排規則，左右顯示
    // 這裡先放常見內圈橫排位置；如果你之後發現哪一排錯，再微調 row/col。
    const secondFloorHorizontalMarkers = [
        ["AD", "CA", 30, "A1"],
        ["AD", "CA", 31, "A2"],
        ["AD", "CA", 32, "A3"],
        ["AD", "CA", 33, "A4"],
        ["AD", "CA", 34, "A5"],

        ["AD", "CA", 54, "A5"],
        ["AD", "CA", 55, "A4"],
        ["AD", "CA", 56, "A3"],
        ["AD", "CA", 57, "A2"],
        ["AD", "CA", 58, "A1"],
    ];

    secondFloorVerticalMarkers.forEach(([col, startRow, endRow, text]) => {
        addVerticalRowMarker(seatMap, minCol, minRow, topOffset, col, startRow, endRow, text);
    });

    secondFloorHorizontalMarkers.forEach(([leftCol, rightCol, row, text]) => {
        addHorizontalRowMarker(seatMap, minCol, minRow, topOffset, leftCol, rightCol, row, text);
    });

    if (!SHOW_KH_THIRD_FLOOR) return;

    const thirdFloorVerticalMarkers = [
        ["J", 43, 49, "B4"],
        ["K", 42, 49, "B3"],
        ["L", 41, 49, "B2"],
        ["K", 53, 72, "B3"],
        ["L", 53, 72, "B2"],
        ["J", 58, 72, "B4"],
        ["M", 57, 67, "B1"],

        ["CR", 31, 51, "B2"],
        ["CS", 31, 51, "B3"],
        ["CT", 31, 51, "B4"],

        ["CQ", 59, 69, "B1"],
        ["CR", 55, 74, "B2"],
        ["CS", 55, 74, "B3"],
        ["CT", 59, 73, "B4"],
    ];

    thirdFloorVerticalMarkers.forEach(([col, startRow, endRow, text]) => {
        addVerticalRowMarker(seatMap, minCol, minRow, topOffset, col, startRow, endRow, text);
    });
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

    const TOP_TITLE_OFFSET = 0;
    const gridColSize = 28;
    const gridRowSize = 24;

    seatMap.style.gridTemplateColumns =
        `repeat(${maxCol - minCol + 3}, ${gridColSize}px)`;

    seatMap.style.gridTemplateRows =
        `repeat(${maxRow - minRow + 2}, ${gridRowSize}px)`;

    if (SHOW_KH_THIRD_FLOOR) {
        addFloorFrame(seatMap, minCol, minRow, TOP_TITLE_OFFSET, "三樓", "B", "CZ", 5, 89, "kh-third-floor");
    }

    addFloorFrame(seatMap, minCol, minRow, TOP_TITLE_OFFSET, "二樓", "P", "CO", 13, 83, "kh-second-floor");
    addFloorFrame(seatMap, minCol, minRow, TOP_TITLE_OFFSET, "一樓", "AF", "BZ", 30, 57, "kh-first-floor");

    addKhStage(seatMap, minCol, minRow, TOP_TITLE_OFFSET);
    addKhRowMarkers(seatMap, minCol, minRow, TOP_TITLE_OFFSET);

    seatData.forEach(seat => {
        const btn = document.createElement("button");
        const seatId = getSeatId(seat);

        btn.className = `seat ${seat.zone}`;
        btn.textContent = seat.seat_number;
        btn.type = "button";

        btn.style.gridColumn = seat.excel_col - minCol + 2;
        btn.style.gridRow = seat.excel_row - minRow + 1 + TOP_TITLE_OFFSET;

        if (seat.sold) {
            btn.classList.add("sold");
            btn.disabled = true;

            btn.addEventListener("mouseenter", e => showSeatTooltip(e, seat, "此座位已售出"));
            btn.addEventListener("mousemove", moveSeatTooltip);
            btn.addEventListener("mouseleave", hideSeatTooltip);
        } else if (!seat.available) {
            btn.disabled = true;

            btn.addEventListener("mouseenter", e => showSeatTooltip(e, seat, "此區域不開放團內購票"));
            btn.addEventListener("mousemove", moveSeatTooltip);
            btn.addEventListener("mouseleave", hideSeatTooltip);
        } else {
            btn.addEventListener("click", () => {
                const viewport = document.getElementById("map-viewport");
                if (viewport && viewport.dataset.justDragged === "true") return;
                toggleSeat(seatId, btn);
            });

            btn.addEventListener("mouseenter", e => showSeatTooltip(e, seat));
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

/* ---------- 拖曳 / 確認訂單 ---------- */

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

    viewport.addEventListener("mousedown", e => {
        if (e.button !== 0) return;

        isDown = true;
        viewport.classList.add("dragging");

        startX = e.clientX;
        startY = e.clientY;
        startScrollLeft = viewport.scrollLeft;
        startScrollTop = viewport.scrollTop;
        viewport.dataset.justDragged = "false";
    });

    window.addEventListener("mousemove", e => {
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

        const res = await fetch("/api/kh/confirm", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                name,
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
            loadSeats();
        } else {
            showSuccessModal(
                "發生錯誤",
                data.message || "發生錯誤"
            );
        }
    });
}

/* ---------- Modal ---------- */

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
    return new Promise(resolve => {
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

successModal?.addEventListener("click", e => {
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

setupZoomControls();
setupConfirmButton();
loadSeats();
