const SHOW_KH_THIRD_FLOOR = false;

let ORDER_OPEN = true;
let seatData = [];
let selectedSeats = new Set();
let zoomLevel = window.innerWidth <= 900 ? 1.15 : 0.9;

let seatMapBaseWidth = 0;
let seatMapBaseHeight = 0;

async function loadSeats() {
    const loadingOverlay = document.getElementById("loading-overlay");

    try {
        loadingOverlay?.classList.remove("hidden");

        const res = await fetch(
            `/api/kh/seats?show_third=${SHOW_KH_THIRD_FLOOR}`
        );
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
        loadingOverlay?.classList.add("hidden");
    }
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
        `${colIndex("AC") - minCol + 2} / ${colIndex("CC") - minCol + 3}`;
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

        ["AI", "AT", "AV", "BI", "BK", "BV"].forEach(col => {
            addSingleMarker(seatMap, minCol, minRow, topOffset, col, r, label, "kh-first-floor-marker");
        });
    }

    // 二樓：直排，只顯示上下，避免壓座位
    const secondFloorVerticalMarkers = [
        ["T", 42, 50, "E3"],
        ["U", 35, 52, "E2"],
        ["V", 25, 57, "E1"],

        ["Y", 33, 55, "D4"],
        ["Z", 31, 55, "D3"],
        ["AB", 34, 54, "D2"],
        ["AC", 37, 53, "D1"],

        ["CB", 37, 53, "D1"],
        ["CC", 34, 54, "D2"],
        ["CE", 31, 55, "D3"],
        ["CF", 33, 55, "D4"],

        ["CI", 25, 57, "E1"],
        ["CJ", 31, 52, "E2"],
        ["CK", 33, 51, "E3"],
    ];

    // 二樓：橫排規則，左右顯示
    const secondFloorHorizontalMarkers = [
        // A 區
        ["AB", 61, "A1"],
        ["AU", 61, "A1"],
        ["BJ", 61, "A1"],
        ["CB", 61, "A1"],
    
        ["AB", 62, "A2"],
        ["AP", 62, "A2"],
        ["AU", 62, "A2"],
        ["BJ", 62, "A2"],
        ["BO", 62, "A2"],
        ["CB", 62, "A2"],
    
        ["AB", 63, "A3"],
        ["AP", 63, "A3"],
        ["AU", 63, "A3"],
        ["BJ", 63, "A3"],
        ["BO", 63, "A3"],
        ["CB", 63, "A3"],
    
        ["AB", 64, "A4"],
        ["AP", 64, "A4"],
        ["AU", 64, "A4"],
        ["BJ", 64, "A4"],
        ["BO", 64, "A4"],
        ["CB", 64, "A4"],
    
        ["AB", 65, "A5"],
        ["AP", 65, "A5"],
        ["AU", 65, "A5"],
        ["BJ", 65, "A5"],
        ["BO", 65, "A5"],
        ["CB", 65, "A5"],
    
        ["AO", 66, "A6"],
        ["BP", 66, "A6"],
    
        // B 區
        ["AV", 66, "B1"],
        ["BH", 66, "B1"],
    
        ["AR", 67, "B2"],
        ["BM", 67, "B2"],
    
        ["AO", 69, "B3"],
        ["AR", 69, "B3"],
        ["BM", 69, "B3"],
        ["BP", 69, "B3"],
    
        ["AO", 70, "B4"],
        ["AR", 70, "B4"],
        ["BM", 70, "B4"],
        ["BP", 70, "B4"],
    
        ["AO", 71, "B5"],
        ["AR", 71, "B5"],
        ["BM", 71, "B5"],
        ["BP", 71, "B5"],
    
        ["AO", 72, "B6"],
        ["AR", 72, "B6"],
        ["BM", 72, "B6"],
        ["BP", 72, "B6"],
    
        ["AO", 73, "B7"],
        ["AR", 73, "B7"],
        ["BM", 73, "B7"],
        ["BP", 73, "B7"],
    
        ["AR", 74, "B8"],
        ["BM", 74, "B8"],
    
        ["AR", 75, "B9"],
        ["BM", 75, "B9"],
    
        // C 區 L-shape
        ["AS", 78, "C1"],
        ["BK", 78, "C1"],
    
        ["AR", 79, "C2"],
        ["BM", 79, "C2"],
    
        ["AQ", 80, "C3"],
        ["Q", 80, "C3"],
        ["BN", 80, "C3"],
        ["CN", 80, "C3"],
    
        ["AP", 81, "C4"],
        ["T", 81, "C4"],
        ["BO", 81, "C4"],
        ["CK", 81, "C4"],
    
        ["AO", 82, "C5"],
        ["W", 82, "C5"],
        ["BP", 82, "C5"],
        ["CH", 82, "C5"],

        // F 區
        ["AS", 17, "F7"],
        ["BK", 17, "F7"],
        
        ["AR", 19, "F6"],
        ["BK", 19, "F6"],
        
        ["AR", 20, "F5"],
        ["BK", 20, "F5"],
        
        ["AR", 21, "F4"],
        ["BK", 21, "F4"],
        
        ["AR", 22, "F3"],
        ["BK", 22, "F3"],
        
        ["AR", 23, "F2"],
        ["BK", 23, "F2"],
        
        ["AK", 26, "F1"],
        ["BS", 26, "F1"],
    ];

    secondFloorVerticalMarkers.forEach(([col, startRow, endRow, text]) => {
        addVerticalRowMarker(
            seatMap,
            minCol,
            minRow,
            topOffset,
            col,
            startRow,
            endRow,
            text
        );
    });
    
    // 二樓 C1 / C2 / E2 特殊顯示位置
    [
        ["V", 60, "C1"],
        ["CH", 60, "C1"],
    
        ["CJ", 73, "C2"],
        ["T", 74, "C2"],

    ].forEach(([col, row, text]) => {
        addSingleMarker(
            seatMap,
            minCol,
            minRow,
            topOffset,
            col,
            row,
            text,
            "kh-special-marker"
        );
    });

    secondFloorHorizontalMarkers.forEach(([col, row, text]) => {
        addSingleMarker(
            seatMap,
            minCol,
            minRow,
            topOffset,
            col,
            row,
            text,
            "kh-horizontal-marker"
        );
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

    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let startScrollLeft = 0;
    let startScrollTop = 0;

    let pinchStartDistance = null;
    let pinchStartZoom = zoomLevel;
    let pinchCenterX = 0;
    let pinchCenterY = 0;
    let pinchStartScrollLeft = 0;
    let pinchStartScrollTop = 0;

    function getTouchDistance(touches) {
        const dx = touches[0].clientX - touches[1].clientX;
        const dy = touches[0].clientY - touches[1].clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }

    function getTouchCenter(touches) {
        return {
            x: (touches[0].clientX + touches[1].clientX) / 2,
            y: (touches[0].clientY + touches[1].clientY) / 2,
        };
    }

    viewport.addEventListener("mousedown", e => {
        if (e.button !== 0) return;

        isDragging = true;
        viewport.classList.add("dragging");

        startX = e.clientX;
        startY = e.clientY;
        startScrollLeft = viewport.scrollLeft;
        startScrollTop = viewport.scrollTop;
        viewport.dataset.justDragged = "false";
    });

    window.addEventListener("mousemove", e => {
        if (!isDragging) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
            viewport.dataset.justDragged = "true";
        }

        viewport.scrollLeft = startScrollLeft - dx;
        viewport.scrollTop = startScrollTop - dy;
    });

    window.addEventListener("mouseup", () => {
        if (!isDragging) return;

        isDragging = false;
        viewport.classList.remove("dragging");

        setTimeout(() => {
            viewport.dataset.justDragged = "false";
        }, 80);
    });

    viewport.addEventListener("touchstart", e => {
        if (e.touches.length === 1) {
            isDragging = true;

            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
            startScrollLeft = viewport.scrollLeft;
            startScrollTop = viewport.scrollTop;
            viewport.dataset.justDragged = "false";
        }

        if (e.touches.length === 2) {
            isDragging = false;

            pinchStartDistance = getTouchDistance(e.touches);
            pinchStartZoom = zoomLevel;

            const center = getTouchCenter(e.touches);
            pinchCenterX = center.x;
            pinchCenterY = center.y;

            pinchStartScrollLeft = viewport.scrollLeft;
            pinchStartScrollTop = viewport.scrollTop;
        }
    }, { passive: false });

    viewport.addEventListener("touchmove", e => {
        if (e.touches.length === 1 && isDragging) {
            e.preventDefault();

            const dx = e.touches[0].clientX - startX;
            const dy = e.touches[0].clientY - startY;

            if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
                viewport.dataset.justDragged = "true";
            }

            viewport.scrollLeft = startScrollLeft - dx;
            viewport.scrollTop = startScrollTop - dy;
        }

        if (e.touches.length === 2 && pinchStartDistance) {
            e.preventDefault();

            const currentDistance = getTouchDistance(e.touches);
            const scale = currentDistance / pinchStartDistance;

            const newZoom = Math.max(0.45, Math.min(2.5, pinchStartZoom * scale));
            const zoomRatio = newZoom / zoomLevel;

            const center = getTouchCenter(e.touches);
            const rect = viewport.getBoundingClientRect();

            const contentX = viewport.scrollLeft + (pinchCenterX - rect.left);
            const contentY = viewport.scrollTop + (pinchCenterY - rect.top);

            zoomLevel = newZoom;
            applyZoom();

            viewport.scrollLeft = contentX * zoomRatio - (center.x - rect.left);
            viewport.scrollTop = contentY * zoomRatio - (center.y - rect.top);
        }
    }, { passive: false });

    viewport.addEventListener("touchend", () => {
        isDragging = false;
        pinchStartDistance = null;

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
