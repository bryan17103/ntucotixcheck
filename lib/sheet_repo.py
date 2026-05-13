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

STATS_CONFIG_SHEETS = {
    "tp": "stats_config_tp",
    "kh": "stats_config_kh",
}

_ws_cache = {}
_sold_cache = {}
_sold_cache_time = {}
_SOLD_CACHE_TTL = 2

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

_ws_cache = None
_sold_cache = None
_sold_cache_time = 0
_SOLD_CACHE_TTL = 2


def get_google_credentials():
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)


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


def get_config_worksheet(name: str):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(name)


def clear_caches(concert_code=None):
    global _sold_cache, _sold_cache_time

    if _sold_cache is None:
        _sold_cache = {}

    if _sold_cache_time is None:
        _sold_cache_time = {}

    if concert_code:
        _sold_cache.pop(concert_code, None)
        _sold_cache_time.pop(concert_code, None)
    else:
        _sold_cache = {}
        _sold_cache_time = {}


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
    return str(value).strip().replace("\n", "").replace("\r", "")


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


def get_all_records(concert_code="tp") -> List[dict]:
    ws = get_worksheet(concert_code)
    return ws.get_all_records()

def get_order_open(concert_code="tp"):
    config_sheet = STATS_CONFIG_SHEETS.get(concert_code, "stats_config_tp")
    ws = get_config_worksheet(config_sheet)

    rows = ws.get_all_records(expected_headers=["類型", "名稱", "條件"])

    for row in rows:
        if (
            str(row.get("類型", "")).strip() == "open"
            and str(row.get("名稱", "")).strip() == "order_open"
        ):
            value = str(row.get("條件", "true")).strip().lower()
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


def get_manual_points(name: str) -> float:
    member_map = load_section_members()
    info = member_map.get(normalize_text(name))
    if not info:
        return 0
    return float(info.get("manual_points", 0))


def get_orders_by_name(name: str):
    target = normalize_text(name)
    if not target:
        return {
            "orders": [],
            "manual_points": 0,
            "total_points": 0,
        }

    rows = [
        row for row in get_all_records()
        if normalize_text(row.get("名字")) == target
    ]

    orders = group_order_rows(rows)
    manual_points = get_manual_points(target)
    base_points = 0

    for order in orders:
        price_counts = order.get("price_counts", {}) or {}
        base_points += float(price_counts.get("500", 0) or 0) * 3.0
        base_points += float(price_counts.get("300", 0) or 0) * 1.5
        base_points += float(price_counts.get("200", 0) or 0) * 1.0

    return {
        "orders": orders,
        "manual_points": manual_points,
        "total_points": base_points + manual_points,
    }


def admin_search_orders(keyword: str) -> List[dict]:
    target = normalize_text(keyword)
    rows = []

    for row in get_all_records():
        row_name = normalize_text(row.get("名字"))
        order_id = normalize_text(row.get("訂單ID"))

        if target and target not in row_name and target not in order_id:
            continue

        rows.append(row)

    return group_order_rows(rows)


def update_order_note(order_id: str, note: str, floor: str = "", row_label: str = "") -> bool:
    ws = get_worksheet()
    records = get_all_records()
    updated_any = False

    for idx, row in enumerate(records, start=2):
        status = normalize_text(row.get("訂單狀態")).lower()

        if status in {"active", "locked"} and row_matches_scope(row, order_id, floor, row_label):
            ws.update_cell(idx, 9, note)
            updated_any = True

    return updated_any


def mark_order_deleted(order_id: str, floor: str = "", row_label: str = "") -> bool:
    ws = get_worksheet()
    records = get_all_records()
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

    clear_caches()
    return True


def update_order_pickup_status(
    order_id: str,
    pickup_open: bool = None,
    picked_up: bool = None,
    floor: str = "",
    row_label: str = "",
) -> bool:
    ws = get_worksheet()
    records = get_all_records()
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
        clear_caches()

    return updated_any


def admin_toggle_lock_status(order_id: str, floor: str = "", row_label: str = ""):
    ws = get_worksheet()
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

    clear_caches()
    return True, f"訂單狀態已改為 {new_status}"


def admin_toggle_payment_status(order_id: str, floor: str = "", row_label: str = ""):
    ws = get_worksheet()
    all_values = ws.get_all_values()

    target_rows = []
    current_payment = False

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        payment_done = normalize_bool(row[11] if len(row) > 11 else "")

        if values_row_matches_scope(row, order_id, floor, row_label):
            target_rows.append(row_idx)
            current_payment = payment_done

    if not target_rows:
        return False, "找不到訂單"

    new_value = not current_payment

    for row_idx in target_rows:
        ws.update_cell(row_idx, 12, bool(new_value))

    return True, "付款狀態已更新"


def admin_toggle_ticket_adjusted_status(order_id: str, floor: str = "", row_label: str = ""):
    ws = get_worksheet()
    all_values = ws.get_all_values()

    target_rows = []
    current_adjusted = False

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        adjusted = normalize_bool(row[12] if len(row) > 12 else "")

        if values_row_matches_scope(row, order_id, floor, row_label):
            target_rows.append(row_idx)
            current_adjusted = adjusted

    if not target_rows:
        return False, "找不到訂單"

    new_value = not current_adjusted

    for row_idx in target_rows:
        ws.update_cell(row_idx, 13, bool(new_value))

    return True, "調票狀態已更新"


def admin_advance_pickup_status(order_id: str, floor: str = "", row_label: str = ""):
    ws = get_worksheet()
    all_values = ws.get_all_values()

    target_rows = []
    pickup_open = False
    picked_up = False

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]

        if values_row_matches_scope(row, order_id, floor, row_label):
            target_rows.append(row_idx)
            pickup_open = normalize_bool(row[9] if len(row) > 9 else "")
            picked_up = normalize_bool(row[10] if len(row) > 10 else "")

    if not target_rows:
        return False, "找不到訂單"

    if not pickup_open and not picked_up:
        new_open, new_picked = True, False
    elif pickup_open and not picked_up:
        new_open, new_picked = True, True
    else:
        new_open, new_picked = True, True

    for row_idx in target_rows:
        ws.update_cell(row_idx, 10, bool(new_open))
        ws.update_cell(row_idx, 11, bool(new_picked))

    return True, "取票狀態已更新"


def admin_delete_order(order_id: str, floor: str = "", row_label: str = ""):
    ws = get_worksheet()
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

    clear_caches()
    return True, "訂單已刪除"

def get_section_members_rows():
    ws = get_config_worksheet("section_members")
    rows = ws.get_all_records(expected_headers=["姓名", "聲部", "手動加分_TP", "手動加分_KH"])

    return [
        {
            "name": normalize_text(row.get("姓名")),
            "section": normalize_text(row.get("聲部")),
            "manual_points": float(row.get("手動加分_TP") or 0),
            "manual_points_kh": float(row.get("手動加分_KH") or 0),
        }
        for row in rows
        if (
            normalize_text(row.get("姓名"))
            or normalize_text(row.get("聲部"))
            or normalize_text(row.get("手動加分_TP"))
            or normalize_text(row.get("手動加分_KH"))
        )
    ]

def get_stats_config_rows():
    ws = get_config_worksheet("stats_config_tp")
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
    values = [["姓名", "聲部", "手動加分_TP", "手動加分_KH"]]

    for row in rows:
        name = normalize_text(row.get("name"))
        section = normalize_text(row.get("section"))

        try:
            manual_points_tp = float(row.get("manual_points") or 0)
        except Exception:
            manual_points_tp = 0

        try:
            manual_points_kh = float(row.get("manual_points_kh") or 0)
        except Exception:
            manual_points_kh = 0

        if not name and not section and manual_points_tp == 0 and manual_points_kh == 0:
            continue

        values.append([name, section, manual_points_tp, manual_points_kh])

    ws.batch_clear(["A:D"])
    ws.update("A1:D" + str(len(values)), values)

def save_stats_config_rows(rows):
    ws = get_config_worksheet("stats_config_tp")
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

def load_section_members():
    member_to_section = {}

    try:
        ws = get_config_worksheet("section_members")
        rows = ws.get_all_records(expected_headers=["姓名", "聲部", "手動加分_TP", "手動加分_KH"])
    except Exception:
        return member_to_section

    for row in rows:
        name = normalize_text(row.get("姓名"))
        section = normalize_text(row.get("聲部"))

        try:
            manual_points = float(row.get("手動加分_TP") or 0)
        except Exception:
            manual_points = 0

        if name and section:
            member_to_section[name] = {
                "section": section,
                "manual_points": manual_points,
            }

    return member_to_section

def price_to_reward_zone(price: int) -> str:
    if price in {500, 400}:
        return "500"
    if price in {300, 240}:
        return "300"
    if price in {200, 160}:
        return "200"
    return str(price)


def price_to_points(price: int) -> float:
    if price in {500, 400}:
        return 3.0
    if price in {300, 240}:
        return 1.5
    if price in {200, 160}:
        return 1.0
    return 0.0


def format_points(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def load_stats_config():
    config = {
        "target_tickets": 0,
        "rewards": []
    }

    try:
        ws = get_config_worksheet("stats_config_tp")
        rows = ws.get_all_records(expected_headers=["類型", "名稱", "條件"])
    except Exception:
        return config

    for row in rows:
        row_type = normalize_text(row.get("類型")).lower()
        name = normalize_text(row.get("名稱"))
        condition_text = normalize_text(row.get("條件"))

        if row_type == "target":
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

    return config


def build_stats_summary():
    rows = get_all_records()
    member_to_section = load_section_members()
    stats_config = load_stats_config()

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

        section = member_info["section"]
        section_ticket_count[section] += 1
        section_members[section][name] += 1

    for name, info in member_to_section.items():
        manual_points = info.get("manual_points", 0)

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
        ],
        key=lambda x: (x["points"], x["tickets"]),
        reverse=True
    )

    section_summary = []
    for section in ["吹管", "彈撥", "拉弦", "低音", "打擊", "指揮", "特殊來源"]:
        members = section_members.get(section, {})
        member_list = sorted(
            [{"name": n, "tickets": c} for n, c in members.items()],
            key=lambda x: x["tickets"],
            reverse=True
        )
        section_summary.append({
            "section": section,
            "subtotal": section_ticket_count.get(section, 0),
            "members": member_list
        })

    reward_summary = []
    assigned_names = set()

    for rule in stats_config["rewards"]:
        qualified = []
        threshold = float(rule.get("threshold", 0))

        for item in ranking:
            name = item["name"]

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

    return {
        "overview": {
            "total_tickets": total_tickets,
            "target_tickets": stats_config["target_tickets"],
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
        ],
    }


def format_reward_conditions(conditions: dict) -> str:
    return ""
