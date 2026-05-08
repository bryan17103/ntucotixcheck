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


# ===== timezone =====
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


# ===== Google Sheet settings =====
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = "1jtPGTV1dCT6QhI9gehKrMu_YwSvNaCrSViKU9S9Rxp8"
WORKSHEET_NAME = "2026Summer_Taipei"

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


# ===== basic helpers =====
def get_google_credentials():
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)


def get_spreadsheet():
    creds = get_google_credentials()
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)


def get_worksheet():
    global _ws_cache

    if _ws_cache is not None:
        return _ws_cache

    spreadsheet = get_spreadsheet()
    _ws_cache = spreadsheet.worksheet(WORKSHEET_NAME)
    return _ws_cache


def get_config_worksheet(name: str):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(name)


def clear_caches():
    global _sold_cache, _sold_cache_time
    _sold_cache = None
    _sold_cache_time = 0


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


def get_all_records() -> List[dict]:
    ws = get_worksheet()
    return ws.get_all_records(expected_headers=HEADERS)


def generate_order_id(name: str) -> str:
    now = datetime.now(TAIPEI_TZ)
    return (
        "TP"
        + now.strftime("%m%d-%H%M-")
        + f"{now.second:02d}"
        + str(random.randint(0, 9))
    )


# ===== order write/read =====
def append_order_rows(name: str, seat_rows: List[Dict]) -> str:
    ws = get_worksheet()
    order_id = generate_order_id(name)
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
        clear_caches()

    return order_id


def get_active_records() -> List[dict]:
    rows = get_all_records()
    return [
        row for row in rows
        if normalize_text(row.get("訂單狀態")).lower() in {"active", "locked"}
    ]


def build_active_sold_seat_keys() -> Set[Tuple[str, str, int]]:
    global _sold_cache, _sold_cache_time

    now = time.time()
    if _sold_cache is not None and (now - _sold_cache_time) < _SOLD_CACHE_TTL:
        return _sold_cache

    sold = set()
    for row in get_active_records():
        floor = normalize_text(row.get("樓層"))
        row_label = normalize_text(row.get("排數"))
        seat_number = normalize_int(row.get("座位"))

        if floor and row_label and seat_number is not None:
            sold.add((floor, row_label, seat_number))

    _sold_cache = sold
    _sold_cache_time = now
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


def get_orders_by_name(name: str) -> List[dict]:
    target = normalize_text(name)
    if not target:
        return []

    rows = [
        row for row in get_all_records()
        if normalize_text(row.get("名字")) == target
    ]

    return group_order_rows(rows)


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


# ===== order update =====
def update_order_note(order_id: str, note: str) -> bool:
    ws = get_worksheet()
    records = get_all_records()

    target_order_id = normalize_text(order_id)
    updated_any = False

    for idx, row in enumerate(records, start=2):
        current_order_id = normalize_text(row.get("訂單ID"))
        status = normalize_text(row.get("訂單狀態")).lower()

        if current_order_id == target_order_id and status in {"active", "locked"}:
            ws.update_cell(idx, 9, note)
            updated_any = True

    return updated_any


def mark_order_deleted(order_id: str) -> bool:
    ws = get_worksheet()
    all_values = ws.get_all_values()
    target_order_id = normalize_text(order_id)

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        current_order_id = normalize_text(row[1] if len(row) > 1 else "")
        current_status = normalize_text(row[2] if len(row) > 2 else "").lower()

        if current_order_id == target_order_id and current_status == "locked":
            return False

    updated_any = False
    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        current_order_id = normalize_text(row[1] if len(row) > 1 else "")

        if current_order_id == target_order_id:
            ws.update_cell(row_idx, 3, "deleted")
            updated_any = True

    if updated_any:
        clear_caches()

    return updated_any


def update_order_pickup_status(order_id: str, pickup_open: bool = None, picked_up: bool = None) -> bool:
    ws = get_worksheet()
    records = get_all_records()

    target_order_id = normalize_text(order_id)
    updated_any = False

    for idx, row in enumerate(records, start=2):
        current_order_id = normalize_text(row.get("訂單ID"))
        status = normalize_text(row.get("訂單狀態")).lower()

        if current_order_id == target_order_id and status in {"active", "locked"}:
            if pickup_open is not None:
                ws.update_cell(idx, 10, bool(pickup_open))
            if picked_up is not None:
                ws.update_cell(idx, 11, bool(picked_up))
            updated_any = True

    if updated_any:
        clear_caches()

    return updated_any


def admin_toggle_lock_status(order_id: str):
    ws = get_worksheet()
    all_values = ws.get_all_values()
    target_order_id = normalize_text(order_id)

    target_rows = []
    current_status = None

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        current_order_id = normalize_text(row[1] if len(row) > 1 else "")
        status = normalize_text(row[2] if len(row) > 2 else "").lower()

        if current_order_id == target_order_id:
            target_rows.append(row_idx)
            current_status = status

    if not target_rows:
        return False, "找不到訂單"

    new_status = "active" if current_status == "locked" else "locked"

    for row_idx in target_rows:
        ws.update_cell(row_idx, 3, new_status)

    clear_caches()
    return True, f"訂單狀態已改為 {new_status}"


def admin_toggle_payment_status(order_id: str):
    ws = get_worksheet()
    all_values = ws.get_all_values()
    target_order_id = normalize_text(order_id)

    target_rows = []
    current_payment = False

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        current_order_id = normalize_text(row[1] if len(row) > 1 else "")
        payment_done = normalize_bool(row[11] if len(row) > 11 else "")

        if current_order_id == target_order_id:
            target_rows.append(row_idx)
            current_payment = payment_done

    if not target_rows:
        return False, "找不到訂單"

    new_value = not current_payment

    for row_idx in target_rows:
        ws.update_cell(row_idx, 12, bool(new_value))

    return True, "付款狀態已更新"


def admin_toggle_ticket_adjusted_status(order_id: str):
    ws = get_worksheet()
    all_values = ws.get_all_values()
    target_order_id = normalize_text(order_id)

    target_rows = []
    current_adjusted = False

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        current_order_id = normalize_text(row[1] if len(row) > 1 else "")
        adjusted = normalize_bool(row[12] if len(row) > 12 else "")

        if current_order_id == target_order_id:
            target_rows.append(row_idx)
            current_adjusted = adjusted

    if not target_rows:
        return False, "找不到訂單"

    new_value = not current_adjusted

    for row_idx in target_rows:
        ws.update_cell(row_idx, 13, bool(new_value))

    return True, "調票狀態已更新"


def admin_advance_pickup_status(order_id: str):
    ws = get_worksheet()
    all_values = ws.get_all_values()
    target_order_id = normalize_text(order_id)

    target_rows = []
    pickup_open = False
    picked_up = False

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        current_order_id = normalize_text(row[1] if len(row) > 1 else "")

        if current_order_id == target_order_id:
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


def admin_delete_order(order_id: str):
    ws = get_worksheet()
    all_values = ws.get_all_values()
    target_order_id = normalize_text(order_id)

    target_rows = []
    current_status = None

    for row_idx in range(2, len(all_values) + 1):
        row = all_values[row_idx - 1]
        current_order_id = normalize_text(row[1] if len(row) > 1 else "")
        status = normalize_text(row[2] if len(row) > 2 else "").lower()

        if current_order_id == target_order_id:
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


# ===== config sheets for edit page =====
def get_section_members_rows():
    ws = get_config_worksheet("section_members")
    rows = ws.get_all_records(expected_headers=["姓名", "聲部", "手動加分"])

    return [
        {
            "name": normalize_text(row.get("姓名")),
            "section": normalize_text(row.get("聲部")),
        }
        for row in rows
        if normalize_text(row.get("姓名")) or normalize_text(row.get("聲部"))
    ]


def get_stats_config_rows():
    ws = get_config_worksheet("stats_config")
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
    values = [["姓名", "聲部"]]

    for row in rows:
        name = normalize_text(row.get("name"))
        section = normalize_text(row.get("section"))

        if not name and not section:
            continue

        values.append([name, section])

    ws.clear()
    ws.update("A1", values)


def save_stats_config_rows(rows):
    ws = get_config_worksheet("stats_config")
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
        rows = ws.get_all_records(expected_headers=["姓名", "聲部", "手動加分"])
    except Exception:
        return member_to_section

    for row in rows:
        name = normalize_text(row.get("姓名"))
        section = normalize_text(row.get("聲部"))

        try:
            manual_points = float(row.get("手動加分") or 0)
        except Exception:
            manual_points = 0

        if name and section:
            member_to_section[name] = {
                "section": section,
                "manual_points": manual_points,
            }

    return member_to_section

# ===== stats / points reward system =====
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
        ws = get_config_worksheet("stats_config")
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

    conductor_count = 0
    fanpage_count = 0
    other_source_count = 0

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
            "manual_bonus": 0
        })
        
        section = member_info["section"]
        section_ticket_count[section] += 1
        section_members[section][name] += 1

        if section == "指揮組":
            conductor_count += 1
        elif name == "粉專購票":
            fanpage_count += 1
        elif section == "未分類":
            other_source_count += 1

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
    for section in ["吹管", "彈撥", "拉弦", "低音", "打擊", "特殊來源"]:
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
        },
        "special": {
            "conductor_count": conductor_count,
            "fanpage_count": fanpage_count,
            "other_source_count": other_source_count,
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
