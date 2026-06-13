from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
import time
import os
import json
import random

import gspread
from google.oauth2.service_account import Credentials
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

TAIPEI_TZ = ZoneInfo("Asia/Taipei")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = "1jtPGTV1dCT6QhI9gehKrMu_YwSvNaCrSViKU9S9Rxp8"
WORKSHEET_NAMES = {
    "tp": "2026Summer_Taipei",
    "kh": "2026Summer_Kaohsiung",
}

STATS_CONFIG_SHEET = "stats_config"

_ws_cache = {}
_sold_cache = {}
_sold_cache_time = {}
_orders_cache = {}
_orders_cache_time = {}
_section_members_cache = None
_section_members_cache_time = 0
_query_cache = {}
_query_cache_time = {}
_SOLD_CACHE_TTL = 30
_ORDERS_CACHE_TTL = 20
_SECTION_MEMBERS_CACHE_TTL = 60
_QUERY_CACHE_TTL = 10

HEADERS = [
    "訂單日期與時間",
    "訂單ID",
    "訂單狀態",
    "名字",
    "樓層",
    "排數",
    "座位",
    "票價",
    "訂單備註",
    "是否開放取票",
    "是否已取票",
    "付款狀態",
    "是否已調票",
]


def get_google_credentials():
    # 本機開發：credentials.json
    local_creds_path = os.path.join(PROJECT_ROOT, "credentials.json")

    if os.path.exists(local_creds_path):
        return Credentials.from_service_account_file(
            local_creds_path,
            scopes=SCOPES,
        )

    # Vercel production：environment variable
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])

    return Credentials.from_service_account_info(
        creds_dict,
        scopes=SCOPES,
    )


def get_spreadsheet():
    creds = get_google_credentials()
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)


def get_worksheet(concert_code="tp"):
    if concert_code not in WORKSHEET_NAMES:
        raise ValueError(f"未知場次：{concert_code}")

    if concert_code in _ws_cache:
        return _ws_cache[concert_code]

    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet(WORKSHEET_NAMES[concert_code])
    _ws_cache[concert_code] = ws
    return ws


_config_ws_cache = {}

def get_config_worksheet(name: str):
    if name in _config_ws_cache:
        return _config_ws_cache[name]

    spreadsheet = get_spreadsheet()
    ws = spreadsheet.worksheet(name)

    _config_ws_cache[name] = ws

    return ws

def get_section_members_worksheet():
    return get_config_worksheet("section_members")

def clear_caches(concert_code=None):
    global _sold_cache
    global _sold_cache_time
    global _orders_cache
    global _orders_cache_time
    global _section_members_cache
    global _section_members_cache_time

    _section_members_cache = None
    _section_members_cache_time = 0

    if concert_code:
        _sold_cache.pop(concert_code, None)
        _sold_cache_time.pop(concert_code, None)

        _orders_cache.pop(concert_code, None)
        _orders_cache_time.pop(concert_code, None)

    else:
        _sold_cache = {}
        _sold_cache_time = {}

        _orders_cache = {}
        _orders_cache_time = {}


def ensure_headers() -> None:
    ws = get_worksheet()
    current = ws.row_values(1)
    if current != HEADERS:
        ws.update("A1:M1", [HEADERS])


def now_str() -> str:
    return datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %H:%M")


def today_mmdd() -> str:
    return datetime.now(TAIPEI_TZ).strftime("%m%d")


def normalize_text(value) -> str:
    if value is None:
        return ""

    return (
        str(value)
        .replace("\u3000", " ")
        .replace("\n", "")
        .replace("\r", "")
        .strip()
    )

def normalize_name(value) -> str:
    return (
        normalize_text(value)
        .replace(" ", "")
        .replace("\u3000", "")
    )

def normalize_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def normalize_bool(value) -> bool:
    text = normalize_text(value).lower()
    return text in {"true", "1", "yes", "y", "是"}


def get_all_records(concert_code):
    now = time.time()

    if (
        concert_code in _orders_cache
        and now - _orders_cache_time.get(concert_code, 0) < _ORDERS_CACHE_TTL
    ):
        return _orders_cache[concert_code]

    ws = get_worksheet(concert_code)

    rows = ws.get_all_records()

    _orders_cache[concert_code] = rows
    _orders_cache_time[concert_code] = now

    return rows

def get_order_open(concert_code="tp"):
    ws = get_config_worksheet(STATS_CONFIG_SHEET)

    target_name = f"order_open_{concert_code}"

    rows = ws.get_all_records(expected_headers=["類型", "名稱", "條件"])

    for row in rows:
        if (
            normalize_text(row.get("類型")) == "open"
            and normalize_text(row.get("名稱")) == target_name
        ):
            value = normalize_text(row.get("條件")).lower()
            return value == "true"

    return True

def row_matches_scope(row: dict, order_id: str, floor: str = "", row_label: str = "") -> bool:
    if normalize_text(row.get("訂單ID")) != normalize_text(order_id):
        return False

    if floor and normalize_text(row.get("樓層")) != normalize_text(floor):
        return False

    if row_label and normalize_text(row.get("排數")) != normalize_text(row_label):
        return False

    return True


def values_row_matches_scope(row: list, order_id: str, floor: str = "", row_label: str = "") -> bool:
    current_order_id = normalize_text(row[1] if len(row) > 1 else "")
    current_floor = normalize_text(row[4] if len(row) > 4 else "")
    current_row_label = normalize_text(row[5] if len(row) > 5 else "")

    if current_order_id != normalize_text(order_id):
        return False

    if floor and current_floor != normalize_text(floor):
        return False

    if row_label and current_row_label != normalize_text(row_label):
        return False

    return True

def get_header_col_map(ws):
    headers = ws.row_values(1)
    return {
        normalize_text(header): index + 1
        for index, header in enumerate(headers)
        if normalize_text(header)
    }


def get_row_value_by_header(row, col_map, header_name):
    col_number = col_map.get(header_name)
    if not col_number:
        return ""

    index = col_number - 1
    return row[index] if len(row) > index else ""

def generate_order_id(name: str, concert_code="tp") -> str:
    now = datetime.now(TAIPEI_TZ)

    prefix = {
        "tp": "TP",
        "kh": "KH",
    }.get(concert_code, "TP")

    return (
        prefix
        + now.strftime("%m%d-%H%M-")
        + f"{now.second:02d}"
        + str(random.randint(0, 9))
    )


def append_order_rows(name: str, seat_rows: List[Dict], concert_code="tp") -> str:
    ws = get_worksheet(concert_code)
    order_id = generate_order_id(name, concert_code)
    dt = now_str()

    values = []

    for seat in seat_rows:
        values.append([
            dt,
            order_id,
            "active",
            name,
            seat["floor"],
            str(seat["row_label"]),
            int(seat["seat_number"]),
            int(seat["price"]),
            "",
            False,
            False,
            False,
            False,
        ])

    if values:
        ws.append_rows(values, value_input_option="USER_ENTERED")
        clear_caches(concert_code)

    return order_id


def get_active_records(concert_code="tp") -> List[dict]:
    rows = get_all_records(concert_code)

    return [
        row for row in rows
        if normalize_text(row.get("訂單狀態")).lower() in {"active", "locked"}
    ]


def build_active_sold_seat_keys(concert_code="tp") -> Set[Tuple[str, str, int]]:
    global _sold_cache, _sold_cache_time

    if _sold_cache is None:
        _sold_cache = {}

    if _sold_cache_time is None:
        _sold_cache_time = {}

    now = time.time()

    if (
        concert_code in _sold_cache
        and (now - _sold_cache_time.get(concert_code, 0)) < _SOLD_CACHE_TTL
    ):
        return _sold_cache[concert_code]

    sold = set()

    for row in get_active_records(concert_code):
        floor = normalize_text(row.get("樓層"))
        row_label = normalize_text(row.get("排數"))
        seat_number = normalize_int(row.get("座位"))

        if floor and row_label and seat_number is not None:
            sold.add((floor, row_label, seat_number))

    _sold_cache[concert_code] = sold
    _sold_cache_time[concert_code] = now

    return sold


def group_order_rows(rows: List[dict]) -> List[dict]:
    grouped = {}

    for row in rows:
        status = normalize_text(row.get("訂單狀態")).lower()
        if status not in {"active", "locked"}:
            continue

        order_id = normalize_text(row.get("訂單ID"))
        dt = normalize_text(row.get("訂單日期與時間"))
        name = normalize_text(row.get("名字"))
        floor = normalize_text(row.get("樓層"))
        row_label = normalize_text(row.get("排數"))
        seat_number = normalize_int(row.get("座位"))
        price = normalize_int(row.get("票價")) or 0
        note = normalize_text(row.get("訂單備註"))
        pickup_open = normalize_bool(row.get("是否開放取票"))
        picked_up = normalize_bool(row.get("是否已取票"))
        payment_done = normalize_bool(row.get("付款狀態"))
        ticket_adjusted = normalize_bool(row.get("是否已調票"))

        key = (order_id, dt, floor, row_label)

        if key not in grouped:
            grouped[key] = {
                "order_id": order_id,
                "datetime": dt,
                "name": name,
                "floor": floor,
                "row_label": row_label,
                "seats": [],
                "price": 0,
                "price_counts": {
                    "800": 0,
                    "500": 0,
                    "300": 0,
                    "200": 0,
                },
                "note": note,
                "pickup_open": pickup_open,
                "picked_up": picked_up,
                "payment_done": payment_done,
                "ticket_adjusted": ticket_adjusted,
                "order_status": status,
            }

        if seat_number is not None:
            grouped[key]["seats"].append(seat_number)

        grouped[key]["price"] += price
        zone = price_to_reward_zone(price)
        
        if zone in grouped[key]["price_counts"]:
            grouped[key]["price_counts"][zone] += 1

        if note:
            grouped[key]["note"] = note
        if pickup_open:
            grouped[key]["pickup_open"] = True
        if picked_up:
            grouped[key]["picked_up"] = True
        if payment_done:
            grouped[key]["payment_done"] = True
        if ticket_adjusted:
            grouped[key]["ticket_adjusted"] = True
        if status:
            grouped[key]["order_status"] = status

    results = list(grouped.values())

    for item in results:
        item["seats"] = sorted(item["seats"])

    results.sort(
        key=lambda x: (x["datetime"], x["floor"], x["row_label"]),
        reverse=True
    )

    return results


def get_manual_points(name: str, concert_code="tp") -> float:
    member_map = load_section_members(concert_code)
    info = member_map.get(normalize_name(name))

    if not info:
        return 0

    return float(info.get("manual_points", 0) or 0)

def calc_points_from_orders(orders) -> float:
    points = 0

    for order in orders:
        price_counts = order.get("price_counts", {}) or {}

        points += float(price_counts.get("800", 0) or 0) * 4.5
        points += float(price_counts.get("500", 0) or 0) * 2.5
        points += float(price_counts.get("300", 0) or 0) * 1.5
        points += float(price_counts.get("200", 0) or 0) * 1.0

    return points


def get_orders_points_pack(name: str, concert_code="tp"):
    target = normalize_name(name)

    rows = [
        row for row in get_all_records(concert_code)
        if normalize_name(row.get("名字")) == target
    ]

    orders = group_order_rows(rows)

    for order in orders:
        order["concert_code"] = concert_code

    manual_points = get_manual_points(target, concert_code)
    base_points = calc_points_from_orders(orders)
    total_points = base_points + manual_points

    return orders, manual_points, total_points

def get_orders_by_name(name: str, concert_code="tp"):
    target = normalize_name(name)

    if not target:
        return {
            "orders": [],
            "manual_points": 0,
            "total_points": 0,
            "identity_code": "5",
            "identity": "請先查詢姓名",
            "discount_amount": 0,
            "all_total_points": 0,
        }

    tp_orders, tp_manual_points, tp_total_points = get_orders_points_pack(target, "tp")
    kh_orders, kh_manual_points, kh_total_points = get_orders_points_pack(target, "kh")

    if concert_code == "tp":
        orders = tp_orders
        manual_points = tp_manual_points
        total_points = tp_total_points

    elif concert_code == "kh":
        orders = kh_orders
        manual_points = kh_manual_points
        total_points = kh_total_points

    else:
        orders = tp_orders + kh_orders
        manual_points = tp_manual_points + kh_manual_points
        total_points = tp_total_points + kh_total_points

    all_total_points = tp_total_points + kh_total_points

    member_map = load_section_members("tp")
    member_info = member_map.get(target, {})

    identity_code = normalize_text(member_info.get("identity_code")) or "5"
    identity = normalize_identity(identity_code)

    discount_amount = calc_discount_amount(
        all_total_points,
        identity_code
    )

    return {
        "orders": orders,
        "manual_points": manual_points,
        "total_points": total_points,
        "identity_code": identity_code,
        "identity": identity,
        "all_total_points": all_total_points,
        "discount_amount": discount_amount,
    }

def admin_search_orders(keyword: str, concert_code="tp") -> List[dict]:
    target = normalize_text(keyword)
    rows = []

    for row in get_all_records(concert_code):
        row_name = normalize_name(row.get("名字"))
        order_id = normalize_text(row.get("訂單ID"))

        if target and target not in row_name and target not in order_id:
            continue

        rows.append(row)

    return group_order_rows(rows)


def update_order_note(order_id: str, note: str, floor: str = "", row_label: str = "", concert_code="tp") -> bool:
    ws = get_worksheet(concert_code)
    records = get_all_records(concert_code)
    updated_any = False

    for idx, row in enumerate(records, start=2):
        status = normalize_text(row.get("訂單狀態")).lower()

        if status in {"active", "locked"} and row_matches_scope(row, order_id, floor, row_label):
            ws.update_cell(idx, 9, note)
            updated_any = True

    if updated_any:
        clear_caches(concert_code)

    return updated_any

def mark_order_deleted(order_id: str, floor: str = "", row_label: str = "", concert_code="tp") -> bool:
    ws = get_worksheet(concert_code)
    records = get_all_records(concert_code)
    matched_rows = []

    for idx, row in enumerate(records, start=2):
        if row_matches_scope(row, order_id, floor, row_label):
            status = normalize_text(row.get("訂單狀態")).lower()

            if status == "locked":
                return False

            matched_rows.append(idx)

    if not matched_rows:
        return False

    for idx in matched_rows:
        ws.update_cell(idx, 3, "deleted")

    clear_caches(concert_code)
    return True

def update_order_pickup_status(
    order_id: str,
    pickup_open: bool = None,
    picked_up: bool = None,
    floor: str = "",
    row_label: str = "",
    concert_code="tp",
) -> bool:
    ws = get_worksheet(concert_code)
    records = get_all_records(concert_code)
    updated_any = False

    for idx, row in enumerate(records, start=2):
        status = normalize_text(row.get("訂單狀態")).lower()

        if status in {"active", "locked"} and row_matches_scope(row, order_id, floor, row_label):
            if pickup_open is not None:
                ws.update_cell(idx, 10, bool(pickup_open))

            if picked_up is not None:
                ws.update_cell(idx, 11, bool(picked_up))

            updated_any = True

    if updated_any:
        clear_caches(concert_code)

    return updated_any

def admin_toggle_lock_status(order_id: str, floor: str = "", row_label: str = "", concert_code="tp"):
    ws = get_worksheet(concert_code)
    all_values = ws.get_all_values()

    target_rows = []
    current_status = None

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        status = normalize_text(row[2] if len(row) > 2 else "").lower()

        if values_row_matches_scope(row, order_id, floor, row_label):
            target_rows.append(row_idx)
            current_status = status

    if not target_rows:
        return False, "找不到訂單"

    new_status = "active" if current_status == "locked" else "locked"

    for row_idx in target_rows:
        ws.update_cell(row_idx, 3, new_status)

    clear_caches(concert_code)
    return True, f"訂單狀態已改為 {new_status}"

def admin_toggle_payment_status(order_id: str, floor: str = "", row_label: str = "", concert_code="tp"):
    ws = get_worksheet(concert_code)
    all_values = ws.get_all_values()
    col_map = get_header_col_map(ws)

    payment_col = col_map.get("付款狀態")
    if not payment_col:
        return False, "找不到欄位：付款狀態"

    target_rows = []
    current_payment = False

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]

        if values_row_matches_scope(row, order_id, floor, row_label):
            target_rows.append(row_idx)
            current_payment = normalize_bool(
                get_row_value_by_header(row, col_map, "付款狀態")
            )

    if not target_rows:
        return False, "找不到訂單"

    new_value = not current_payment

    for row_idx in target_rows:
        ws.update_cell(row_idx, payment_col, bool(new_value))

    clear_caches(concert_code)
    return True, "付款狀態已更新"

def admin_toggle_ticket_adjusted_status(order_id: str, floor: str = "", row_label: str = "", concert_code="tp"):
    ws = get_worksheet(concert_code)
    all_values = ws.get_all_values()
    col_map = get_header_col_map(ws)

    adjusted_col = col_map.get("是否已調票")
    if not adjusted_col:
        return False, "找不到欄位：是否已調票"

    target_rows = []
    current_adjusted = False

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]

        if values_row_matches_scope(row, order_id, floor, row_label):
            target_rows.append(row_idx)
            current_adjusted = normalize_bool(
                get_row_value_by_header(row, col_map, "是否已調票")
            )

    if not target_rows:
        return False, "找不到訂單"

    new_value = not current_adjusted

    for row_idx in target_rows:
        ws.update_cell(row_idx, adjusted_col, bool(new_value))

    clear_caches(concert_code)
    return True, "調票狀態已更新"

def admin_advance_pickup_status(order_id: str, floor: str = "", row_label: str = "", concert_code="tp"):
    ws = get_worksheet(concert_code)
    all_values = ws.get_all_values()
    col_map = get_header_col_map(ws)

    pickup_open_col = col_map.get("是否開放取票")
    picked_up_col = col_map.get("是否已取票")

    if not pickup_open_col:
        return False, "找不到欄位：是否開放取票"

    if not picked_up_col:
        return False, "找不到欄位：是否已取票"

    target_rows = []
    pickup_open = False
    picked_up = False

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]

        if values_row_matches_scope(row, order_id, floor, row_label):
            target_rows.append(row_idx)
            pickup_open = normalize_bool(
                get_row_value_by_header(row, col_map, "是否開放取票")
            )
            picked_up = normalize_bool(
                get_row_value_by_header(row, col_map, "是否已取票")
            )

    if not target_rows:
        return False, "找不到訂單"

    if not pickup_open and not picked_up:
        new_open, new_picked = True, False
    elif pickup_open and not picked_up:
        new_open, new_picked = True, True
    else:
        new_open, new_picked = True, True

    for row_idx in target_rows:
        ws.update_cell(row_idx, pickup_open_col, bool(new_open))
        ws.update_cell(row_idx, picked_up_col, bool(new_picked))

    clear_caches(concert_code)
    return True, "取票狀態已更新"

def admin_delete_order(order_id: str, floor: str = "", row_label: str = "", concert_code="tp"):
    ws = get_worksheet(concert_code)
    all_values = ws.get_all_values()

    target_rows = []
    current_status = None

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        status = normalize_text(row[2] if len(row) > 2 else "").lower()

        if values_row_matches_scope(row, order_id, floor, row_label):
            target_rows.append(row_idx)
            current_status = status

    if not target_rows:
        return False, "找不到訂單"

    if current_status == "locked":
        return False, "已鎖定，無法刪除"

    for row_idx in target_rows:
        ws.update_cell(row_idx, 3, "deleted")

    clear_caches(concert_code)
    return True, "訂單已刪除"

def get_section_members_rows():
    global _section_members_cache
    global _section_members_cache_time

    now = time.time()

    if (
        _section_members_cache is not None
        and now - _section_members_cache_time < _SECTION_MEMBERS_CACHE_TTL
    ):
        rows = _section_members_cache
    else:
        ws = get_config_worksheet("section_members")

        rows = ws.get_all_records(
            expected_headers=[
                "姓名",
                "聲部",
                "手動加分_TP",
                "手動加分_KH",
                "身份",
            ]
        )

        _section_members_cache = rows
        _section_members_cache_time = now

    result = []

    for row in rows:
        name = normalize_text(row.get("姓名"))
        section = normalize_text(row.get("聲部"))
        identity_code = normalize_text(row.get("身份")) or "5"

        try:
            manual_points = float(row.get("手動加分_TP") or 0)
        except Exception:
            manual_points = 0

        try:
            manual_points_kh = float(row.get("手動加分_KH") or 0)
        except Exception:
            manual_points_kh = 0

        if not name and not section and manual_points == 0 and manual_points_kh == 0 and not identity_code:
            continue

        result.append({
            "name": name,
            "section": section,
            "manual_points": manual_points,
            "manual_points_kh": manual_points_kh,
            "identity_code": identity_code,
        })

    return result

def get_stats_config_rows():
    ws = get_config_worksheet(STATS_CONFIG_SHEET)
    rows = ws.get_all_records(expected_headers=["類型", "名稱", "條件"])

    return [
        {
            "type": normalize_text(row.get("類型")),
            "name": normalize_text(row.get("名稱")),
            "condition": normalize_text(row.get("條件")),
        }
        for row in rows
        if normalize_text(row.get("類型")) or normalize_text(row.get("名稱")) or normalize_text(row.get("條件"))
    ]

def save_section_members_rows(rows):
    ws = get_config_worksheet("section_members")

    values = [[
        "姓名",
        "聲部",
        "手動加分_TP",
        "手動加分_KH",
        "身份",
    ]]

    for row in rows:
        name = normalize_name(row.get("name"))
        section = normalize_text(row.get("section"))
        identity_code = normalize_text(row.get("identity_code")) or "5"

        try:
            manual_points_tp = float(row.get("manual_points") or 0)
        except Exception:
            manual_points_tp = 0

        try:
            manual_points_kh = float(row.get("manual_points_kh") or 0)
        except Exception:
            manual_points_kh = 0

        if not name and not section and manual_points_tp == 0 and manual_points_kh == 0 and not identity_code:
            continue

        values.append([
            name,
            section,
            manual_points_tp,
            manual_points_kh,
            identity_code,
        ])

    ws.batch_clear(["A:E"])
    ws.update("A1:E" + str(len(values)), values)

    clear_caches()

def save_stats_config_rows(rows):
    ws = get_config_worksheet(STATS_CONFIG_SHEET)
    values = [["類型", "名稱", "條件"]]

    for row in rows:
        row_type = normalize_text(row.get("type"))
        name = normalize_text(row.get("name"))
        condition = normalize_text(row.get("condition"))

        if not row_type and not name and not condition:
            continue

        values.append([row_type, name, condition])

    ws.clear()
    ws.update("A1", values)

def load_section_members(concert_code="tp"):
    global _section_members_cache
    global _section_members_cache_time

    now = time.time()

    if (
        _section_members_cache is not None
        and now - _section_members_cache_time < _SECTION_MEMBERS_CACHE_TTL
    ):
        rows = _section_members_cache
    else:
        try:
            ws = get_config_worksheet("section_members")
            rows = ws.get_all_records(
                expected_headers=["姓名", "聲部", "手動加分_TP", "手動加分_KH", "身份"]
            )
            _section_members_cache = rows
            _section_members_cache_time = now
        except Exception:
            return {}

    manual_col = "手動加分_KH" if concert_code == "kh" else "手動加分_TP"

    member_to_section = {}

    for row in rows:
        name = normalize_text(row.get("姓名"))
        section = normalize_text(row.get("聲部"))
        identity_code = normalize_text(row.get("身份"))

        try:
            manual_points = float(row.get(manual_col) or 0)
        except Exception:
            manual_points = 0

        if name:
            member_to_section[name] = {
                "section": section or "未分類",
                "manual_points": manual_points,
                "identity_code": identity_code or "5",
                "identity": normalize_identity(identity_code),
            }

    return member_to_section

def price_to_reward_zone(price: int) -> str:
    if price in {800, 640}:
        return "800"
    if price in {500, 400}:
        return "500"
    if price in {300, 240}:
        return "300"
    if price in {200, 160}:
        return "200"
    return str(price)

def price_to_points(price: int) -> float:
    if price in {800, 640}:
        return 4.5
    if price in {500, 400}:
        return 2.5
    if price in {300, 240}:
        return 1.5
    if price in {200, 160}:
        return 1.0
    return 0.0

def format_points(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)

_stats_config_cache = {}
_stats_config_cache_time = {}
_STATS_CONFIG_CACHE_TTL = 60


def load_stats_config(concert_code="tp"):
    global _stats_config_cache
    global _stats_config_cache_time
    _stats_config_cache = {}
    _stats_config_cache_time = {}

    now = time.time()

    if (
        concert_code in _stats_config_cache
        and now - _stats_config_cache_time.get(concert_code, 0) < _STATS_CONFIG_CACHE_TTL
    ):
        return _stats_config_cache[concert_code]

    config = {
        "target_tickets": 0,
        "rewards": []
    }

    try:
        ws = get_config_worksheet(STATS_CONFIG_SHEET)
        rows = ws.get_all_records(expected_headers=["類型", "名稱", "條件"])
    except Exception:
        return config

    target_name = f"目標推票數_{concert_code}"

    for row in rows:
        row_type = normalize_text(row.get("類型")).lower()
        name = normalize_text(row.get("名稱"))
        condition_text = normalize_text(row.get("條件"))

        if row_type == "target" and name == target_name:
            try:
                config["target_tickets"] = int(float(condition_text))
            except Exception:
                config["target_tickets"] = 0
            continue

        if row_type == "reward":
            try:
                threshold = float(condition_text)
            except Exception:
                continue

            if name and threshold > 0:
                config["rewards"].append({
                    "reward": name,
                    "threshold": threshold
                })

    config["rewards"].sort(
        key=lambda x: x["threshold"],
        reverse=True
    )

    _stats_config_cache[concert_code] = config
    _stats_config_cache_time[concert_code] = now

    return config

def build_stats_summary(concert_code="tp"):
    rows = get_all_records(concert_code)
    member_to_section = load_section_members(concert_code)
    stats_config = load_stats_config(concert_code)
    EXCLUDED_RANKING_SECTIONS = {"特殊來源"}
    EXCLUDED_REWARD_SECTIONS = {"特殊來源", "未分類"}

    valid_rows = [
        row for row in rows
        if normalize_text(row.get("訂單狀態")).lower() in {"active", "locked"}
    ]

    total_tickets = 0
    paid_tickets = 0
    unpaid_tickets = 0
    paid_amount = 0
    total_amount = 0
    picked_tickets = 0
    unpicked_tickets = 0

    person_ticket_count = defaultdict(int)
    person_points = defaultdict(float)
    section_ticket_count = defaultdict(int)
    section_members = defaultdict(lambda: defaultdict(int))

    zone_ticket_count = {
        "800": 0,
        "500": 0,
        "300": 0,
        "200": 0,
    }

    for row in valid_rows:
        name = normalize_text(row.get("名字"))
        seat = normalize_int(row.get("座位"))
        price = normalize_int(row.get("票價")) or 0
        payment_done = normalize_bool(row.get("付款狀態"))
        picked_up = normalize_bool(row.get("是否已取票"))

        if seat is None:
            continue

        total_tickets += 1
        total_amount += price

        zone_key = price_to_reward_zone(price)

        if zone_key in zone_ticket_count:
            zone_ticket_count[zone_key] += 1

        if payment_done:
            paid_tickets += 1
            paid_amount += price
        else:
            unpaid_tickets += 1

        if picked_up:
            picked_tickets += 1
        else:
            unpicked_tickets += 1

        person_ticket_count[name] += 1
        person_points[name] += price_to_points(price)

        member_info = member_to_section.get(name, {
            "section": "未分類",
            "manual_points": 0,
        })

        section = member_info.get("section", "未分類")

        if section not in EXCLUDED_REWARD_SECTIONS:
            section_ticket_count[section] += 1
            section_members[section][name] += 1

    for name, info in member_to_section.items():
        manual_points = float(info.get("manual_points", 0) or 0)

        if manual_points > 0:
            person_points[name] += manual_points

    ranking = sorted(
        [
            {
                "name": name,
                "section": member_to_section.get(name, {}).get("section", "未分類"),
                "tickets": count,
                "points": person_points[name],
            }
            for name, count in person_ticket_count.items()
            if member_to_section.get(name, {}).get("section", "未分類")
            not in EXCLUDED_RANKING_SECTIONS
        ],
        key=lambda x: (x["points"], x["tickets"]),
        reverse=True
    )

    section_summary = []

    for section in ["吹管", "彈撥", "拉弦", "低音", "打擊", "指揮"]:
        members = section_members.get(section, {})

        member_list = sorted(
            [
                {
                    "name": n,
                    "tickets": c,
                    "points": person_points[n],
                }
                for n, c in members.items()
            ],
            key=lambda x: (x["points"], x["tickets"]),
            reverse=True
        )

        section_summary.append({
            "section": section,
            "subtotal": section_ticket_count.get(section, 0),
            "members": member_list
        })

    reward_summary = []
    assigned_names = set()

    for rule in stats_config.get("rewards", []):
        qualified = []
        threshold = float(rule.get("threshold", 0) or 0)

        for item in ranking:
            name = item["name"]
            section = item.get("section", "未分類")

            if section in EXCLUDED_REWARD_SECTIONS:
                continue

            if name in assigned_names:
                continue

            total_points = person_points[name]

            if total_points >= threshold:
                qualified.append(name)
                assigned_names.add(name)

        reward_summary.append({
            "reward": rule["reward"],
            "requirement": f"{threshold:g} 分",
            "count": len(qualified),
            "names": qualified
        })

    if concert_code == "tp":
        zone_ticket_count.pop("800", None)

    return {
        "overview": {
            "concert_code": concert_code,
            "total_tickets": total_tickets,
            "target_tickets": stats_config.get("target_tickets", 0),
            "paid_tickets": paid_tickets,
            "unpaid_tickets": unpaid_tickets,
            "paid_amount": paid_amount,
            "total_amount": total_amount,
            "picked_tickets": picked_tickets,
            "unpicked_tickets": unpicked_tickets,
            "zone_tickets": zone_ticket_count,
        },
        "ranking": ranking,
        "sections": section_summary,
        "rewards": reward_summary,
        "section_chart": [
            {
                "section": item["section"],
                "tickets": item["subtotal"]
            }
            for item in section_summary
            if item["subtotal"] > 0
        ],
    }

def number_safe(value):
    try:
        return float(value or 0)
    except Exception:
        return 0


def build_stats_summary_all():
    tp = build_stats_summary("tp")
    kh = build_stats_summary("kh")

    person_map = {}

    # 合併排行榜
    for source in [tp, kh]:
        for item in source.get("ranking", []):

            name = item["name"]

            if name not in person_map:
                person_map[name] = {
                    "name": name,
                    "section": item.get("section", "未分類"),
                    "tickets": 0,
                    "points": 0,
                }

            person_map[name]["tickets"] += number_safe(
                item.get("tickets")
            )

            person_map[name]["points"] += number_safe(
                item.get("points")
            )

    ranking = sorted(
        person_map.values(),
        key=lambda x: (x["points"], x["tickets"]),
        reverse=True
    )

    # 各聲部統計
    section_map = {
        section: {
            "section": section,
            "subtotal": 0,
            "members": []
        }
        for section in ["吹管", "彈撥", "拉弦", "低音", "打擊", "指揮"]
    }

    for item in ranking:
        section = item.get("section", "未分類")

        if section not in section_map:
            continue

        section_map[section]["subtotal"] += item["tickets"]

        section_map[section]["members"].append({
            "name": item["name"],
            "tickets": item["tickets"],
            "points": item["points"],
        })

    sections = list(section_map.values())

    # 推票獎勵
    stats_config = load_stats_config("tp")

    reward_summary = []
    assigned_names = set()

    excluded = {"特殊來源", "未分類"}

    for rule in stats_config.get("rewards", []):

        qualified = []
        threshold = float(rule.get("threshold", 0) or 0)

        for item in ranking:

            name = item["name"]
            section = item.get("section", "未分類")

            if section in excluded:
                continue

            if name in assigned_names:
                continue

            if item["points"] >= threshold:
                qualified.append(name)
                assigned_names.add(name)

        reward_summary.append({
            "reward": rule["reward"],
            "requirement": f"{threshold:g} 分",
            "count": len(qualified),
            "names": qualified
        })

    return {
        "ranking": ranking,

        "sections": sections,

        "rewards": reward_summary,

        "section_chart": [
            {
                "section": x["section"],
                "tickets": x["subtotal"]
            }
            for x in sections
            if x["subtotal"] > 0
        ]
    }

def format_reward_conditions(conditions: dict) -> str:
    return ""

def normalize_identity(identity_code):
    mapping = {
        "1": "團員",
        "2": "工人/協演",
        "3": "學生協奏",
        "4": "團長群",
        "5": "暫時未分類，請耐心等待",
    }
    return mapping.get(str(identity_code).strip(), "暫時未分類，請耐心等待")


def calc_discount_amount(total_points, identity_code):
    """
    E欄身份別：
    1 = 團員
    2 = 工人/協演
    3 = 學生協奏
    4 = 團長群
    5 = 暫時未分類
    """

    thresholds = {
        "1": 10,
        "2": 2,
        "3": 55,
        "4": 30,
    }

    code = str(identity_code).strip()
    threshold = thresholds.get(code)

    if threshold is None:
        return 0

    if total_points <= threshold:
        return 0

    discount_points = int(total_points - threshold)
    return discount_points * 100