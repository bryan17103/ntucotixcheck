function khColIndex(col) {
    let n = 0;
    for (let i = 0; i < col.length; i++) {
        n = n * 26 + (col.charCodeAt(i) - 64);
    }
    return n;
}

function addKhStageToMap(seatMap, minCol, minRow, topOffset = 0, options = {}) {
    const stage = document.createElement("div");
    stage.className = options.className || "stage-box map-stage kh-stage";
    stage.textContent = options.text || "舞台";

    stage.style.gridColumn =
        `${khColIndex("AJ") - minCol + 2} / ${khColIndex("BU") - minCol + 3}`;

    stage.style.gridRow =
        `${35 - minRow + 1 + topOffset} / ${41 - minRow + 2 + topOffset}`;

    seatMap.appendChild(stage);
}

function addKhFloorFrameToMap(
    seatMap,
    minCol,
    minRow,
    topOffset,
    label,
    startCol,
    endCol,
    startRow,
    endRow,
    className = ""
) {
    const frame = document.createElement("div");
    frame.className = `kh-floor-frame ${className}`;

    frame.style.gridColumn =
        `${khColIndex(startCol) - minCol + 2} / ${khColIndex(endCol) - minCol + 3}`;

    frame.style.gridRow =
        `${startRow - minRow + 1 + topOffset} / ${endRow - minRow + 2 + topOffset}`;

    const tag = document.createElement("div");
    tag.className = "kh-floor-tag";
    tag.textContent = label;

    frame.appendChild(tag);
    seatMap.appendChild(frame);
}

function addKhFloorFramesToMap(seatMap, minCol, minRow, topOffset = 0, showThirdFloor = false) {
    if (showThirdFloor) {
        addKhFloorFrameToMap(seatMap, minCol, minRow, topOffset, "三樓", "B", "CZ", 5, 89, "kh-third-floor");
    }

    addKhFloorFrameToMap(seatMap, minCol, minRow, topOffset, "二樓", "P", "CO", 13, 83, "kh-second-floor");
    addKhFloorFrameToMap(seatMap, minCol, minRow, topOffset, "一樓", "AF", "BZ", 30, 57, "kh-first-floor");
}

function addKhSingleMarkerToMap(seatMap, minCol, minRow, topOffset, col, row, text, extraClass = "") {
    const marker = document.createElement("div");
    marker.className = `row-label kh-row-marker ${extraClass}`;
    marker.textContent = text;

    marker.style.gridColumn = khColIndex(col) - minCol + 2;
    marker.style.gridRow = row - minRow + 1 + topOffset;

    seatMap.appendChild(marker);
}

function addKhVerticalRowMarkerToMap(seatMap, minCol, minRow, topOffset, col, startRow, endRow, text) {
    addKhSingleMarkerToMap(seatMap, minCol, minRow, topOffset, col, startRow - 1, text, "kh-vertical-marker");
    addKhSingleMarkerToMap(seatMap, minCol, minRow, topOffset, col, endRow + 1, text, "kh-vertical-marker");
}

function addKhRowMarkersToMap(seatMap, minCol, minRow, topOffset = 0, showThirdFloor = false) {
    for (let r = 44; r <= 55; r++) {
        const label = String(r - 43);

        ["AI", "AT", "AV", "BI", "BK", "BV"].forEach(col => {
            addKhSingleMarkerToMap(seatMap, minCol, minRow, topOffset, col, r, label, "kh-first-floor-marker");
        });
    }

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

    const secondFloorHorizontalMarkers = [
        ["AB", 61, "A1"], ["AU", 61, "A1"], ["BJ", 61, "A1"], ["CB", 61, "A1"],

        ["AB", 62, "A2"], ["AP", 62, "A2"], ["AU", 62, "A2"], ["BJ", 62, "A2"], ["BO", 62, "A2"], ["CB", 62, "A2"],
        ["AB", 63, "A3"], ["AP", 63, "A3"], ["AU", 63, "A3"], ["BJ", 63, "A3"], ["BO", 63, "A3"], ["CB", 63, "A3"],
        ["AB", 64, "A4"], ["AP", 64, "A4"], ["AU", 64, "A4"], ["BJ", 64, "A4"], ["BO", 64, "A4"], ["CB", 64, "A4"],
        ["AB", 65, "A5"], ["AP", 65, "A5"], ["AU", 65, "A5"], ["BJ", 65, "A5"], ["BO", 65, "A5"], ["CB", 65, "A5"],

        ["AO", 66, "A6"], ["BP", 66, "A6"],

        ["AV", 66, "B1"], ["BH", 66, "B1"],
        ["AR", 67, "B2"], ["BM", 67, "B2"],

        ["AO", 69, "B3"], ["AR", 69, "B3"], ["BM", 69, "B3"], ["BP", 69, "B3"],
        ["AO", 70, "B4"], ["AR", 70, "B4"], ["BM", 70, "B4"], ["BP", 70, "B4"],
        ["AO", 71, "B5"], ["AR", 71, "B5"], ["BM", 71, "B5"], ["BP", 71, "B5"],
        ["AO", 72, "B6"], ["AR", 72, "B6"], ["BM", 72, "B6"], ["BP", 72, "B6"],
        ["AO", 73, "B7"], ["AR", 73, "B7"], ["BM", 73, "B7"], ["BP", 73, "B7"],

        ["AR", 74, "B8"], ["BM", 74, "B8"],
        ["AR", 75, "B9"], ["BM", 75, "B9"],

        ["AS", 78, "C1"], ["BK", 78, "C1"],
        ["AR", 79, "C2"], ["BM", 79, "C2"],

        ["AQ", 80, "C3"], ["Q", 80, "C3"], ["BN", 80, "C3"], ["CN", 80, "C3"],
        ["AP", 81, "C4"], ["T", 81, "C4"], ["BO", 81, "C4"], ["CK", 81, "C4"],
        ["AO", 82, "C5"], ["W", 82, "C5"], ["BP", 82, "C5"], ["CH", 82, "C5"],

        ["AS", 17, "F7"], ["BK", 17, "F7"],
        ["AR", 19, "F6"], ["BK", 19, "F6"],
        ["AR", 20, "F5"], ["BK", 20, "F5"],
        ["AR", 21, "F4"], ["BK", 21, "F4"],
        ["AR", 22, "F3"], ["BK", 22, "F3"],
        ["AR", 23, "F2"], ["BK", 23, "F2"],
        ["AK", 26, "F1"], ["BS", 26, "F1"],
    ];

    secondFloorVerticalMarkers.forEach(([col, startRow, endRow, text]) => {
        addKhVerticalRowMarkerToMap(seatMap, minCol, minRow, topOffset, col, startRow, endRow, text);
    });

    [
        ["V", 60, "C1"],
        ["CH", 60, "C1"],
        ["CJ", 73, "C2"],
        ["T", 74, "C2"],
    ].forEach(([col, row, text]) => {
        addKhSingleMarkerToMap(seatMap, minCol, minRow, topOffset, col, row, text, "kh-special-marker");
    });

    secondFloorHorizontalMarkers.forEach(([col, row, text]) => {
        addKhSingleMarkerToMap(seatMap, minCol, minRow, topOffset, col, row, text, "kh-horizontal-marker");
    });

    if (!showThirdFloor) return;

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
        addKhVerticalRowMarkerToMap(seatMap, minCol, minRow, topOffset, col, startRow, endRow, text);
    });
}
