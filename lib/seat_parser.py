from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string


# =========================
# 共用工具
# =========================

def get_fill_color(cell):
    fill = cell.fill
    if not fill:
        return None

    color = fill.fgColor
    if not color:
        return None

    if color.type == "rgb":
        return color.rgb
    elif color.type == "indexed":
        return f"indexed:{color.indexed}"
    elif color.type == "theme":
        return f"theme:{color.theme}"

    return None


def normalize_row_label(value):
    if value is None:
        return ""

    if isinstance(value, (int, float)):
        if int(value) == value:
            return str(int(value))
        return str(value)

    return str(value).strip()


def label_to_zone_price_available(label):
    text = str(label).strip()

    # 特殊席
    if "工作席" in text:
        return "staff", 0, False

    if "攝影" in text:
        return "camera", 0, False

    if "貴賓" in text:
        return "vip", 0, False

    if "輪椅陪同" in text:
        return "companion", 300, False

    if "輪椅" in text:
        return "wheelchair", 300, False

    if "不開放" in text:
        return "notopen", 300, False

    # 團內票區
    if "團內" in text:
        if "800" in text:
            return "group-800", 640, True
        if "500" in text:
            return "group-500", 400, True
        if "300" in text:
            return "group-300", 240, True
        if "200" in text:
            return "group-200", 160, True

    # 一般票區
    if "800" in text:
        return "regular-800", 800, False
    if "500" in text:
        return "regular-500", 500, False
    if "300" in text:
        return "regular-300", 300, False
    if "200" in text:
        return "regular-200", 200, False

    return "unknown", 0, False


# =========================
# 主入口
# =========================

def parse_seat_map(filepath, concert_code="tp", debug=False):
    if concert_code == "tp":
        return parse_tp_seat_map(filepath, debug=debug)

    if concert_code == "kh":
        return parse_kh_seat_map(filepath, debug=debug)

    raise ValueError(f"未知場次：{concert_code}")


# =========================
# 台北場 parser
# =========================

TP_SEAT_START_COL = column_index_from_string("E")
TP_SEAT_END_COL = column_index_from_string("AT")

TP_LEFT_ROW_LABEL_COL = column_index_from_string("B")
TP_RIGHT_ROW_LABEL_COL = column_index_from_string("AW")

TP_LEGEND_COLOR_COL = column_index_from_string("AX")
TP_LEGEND_LABEL_COL = column_index_from_string("AY")


def build_tp_legend_label_map(ws):
    legend_map = {}

    for row in range(1, ws.max_row + 1):
        color_cell = ws.cell(row, TP_LEGEND_COLOR_COL)
        label_cell = ws.cell(row, TP_LEGEND_LABEL_COL)

        color = get_fill_color(color_cell)
        label = label_cell.value

        if not color or label is None:
            continue

        label = str(label).strip()
        if not label:
            continue

        legend_map[color] = label

    return legend_map


def build_tp_color_map(ws):
    legend_label_map = build_tp_legend_label_map(ws)
    color_map = {}

    for color, label in legend_label_map.items():
        zone, price, available = label_to_zone_price_available(label)
        color_map[color] = (zone, price, available)

    return color_map


def parse_tp_seat_map(filepath, debug=False):
    wb = load_workbook(filepath)
    ws = wb.active

    color_map = build_tp_color_map(ws)

    seats = []
    row_labels = {}

    for excel_row in range(1, ws.max_row + 1):
        left_label = normalize_row_label(
            ws.cell(excel_row, TP_LEFT_ROW_LABEL_COL).value
        )
        right_label = normalize_row_label(
            ws.cell(excel_row, TP_RIGHT_ROW_LABEL_COL).value
        )

        row_label = left_label or right_label

        if row_label:
            row_labels[excel_row] = row_label

        for excel_col in range(TP_SEAT_START_COL, TP_SEAT_END_COL + 1):
            cell = ws.cell(excel_row, excel_col)
            value = cell.value

            if isinstance(value, (int, float)):
                color = get_fill_color(cell)
                zone, price, available = color_map.get(
                    color,
                    ("unknown", 0, False)
                )

                if debug and color not in color_map:
                    print(
                        f"⚠️ 台北場未定義顏色: "
                        f"row={excel_row}, col={excel_col}, "
                        f"seat={value}, color={color}"
                    )

                seats.append({
                    "seat_number": int(value),
                    "excel_row": excel_row,
                    "excel_col": excel_col,
                    "row_label": row_labels.get(excel_row, ""),
                    "zone": zone,
                    "price": price,
                    "color": color,
                    "available": available,
                })

    return seats, row_labels, color_map


# =========================
# 高雄場 parser
# 下一步再正式填
# =========================

def parse_kh_seat_map(filepath, debug=False):
    raise NotImplementedError("高雄場座位圖解析尚未完成")
