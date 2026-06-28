import json
import os
import re
import ssl
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv()

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_BASE_URL = os.environ.get("CONSIGNMENT_API_BASE_URL", "").rstrip("/")
TAIPEI_TZ = timezone(timedelta(hours=8))

CHINESE_NAME_RE = re.compile(r"^[\u4e00-\u9fff]{2,8}$")


def normalize_name(value: str) -> str:
    return str(value or "").replace(" ", "").replace("　", "").strip()


def is_valid_chinese_full_name(value: str) -> bool:
    return bool(CHINESE_NAME_RE.match(str(value or "").strip()))


def post_json(url: str, payload: dict, timeout: int = 12) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")

    req = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # 使用 certifi 的憑證，解決本機 SSL certificate verify failed
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    try:
        with urlopen(req, timeout=timeout, context=ssl_context) as response:
            data = json.loads(response.read().decode("utf-8"))
            return response.status, data

    except HTTPError as error:
        try:
            data = json.loads(error.read().decode("utf-8"))
        except Exception:
            data = {"success": False, "message": "主系統回傳格式錯誤"}
        return error.code, data

    except URLError as error:
        return 502, {
            "success": False,
            "message": f"無法連線到主系統：{error.reason}",
        }


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


def lookup_audience_records(concert_code: str, audience_name: str):
    if concert_code not in {"tp", "kh"}:
        return 400, {"success": False, "message": "請選擇正確場次"}

    audience_name = normalize_name(audience_name)

    if not audience_name:
        return 400, {"success": False, "message": "請輸入取票人中文全名"}

    if not is_valid_chinese_full_name(audience_name):
        return 400, {
            "success": False,
            "message": "請輸入完整中文姓名；本系統不接受暱稱、英文、空白或部分姓名查詢。",
        }

    if not API_BASE_URL:
        return 500, {
            "success": False,
            "message": "尚未設定 CONSIGNMENT_API_BASE_URL，無法連接目前寄票系統。",
        }

    status, data = post_json(
        f"{API_BASE_URL}/api/consignment/audience-lookup",
        {
            "concert_code": concert_code,
            "audience_name": audience_name,
        },
    )

    if status >= 400 or not data.get("success"):
        return status, {
            "success": False,
            "message": data.get("message") or "查詢失敗，請稍後再試。",
        }

    target = normalize_name(audience_name)

    records = [
        record for record in data.get("records", [])
        if normalize_name(record.get("audience_name")) == target
    ]

    if not records:
        return 404, {
            "success": False,
            "message": "查無資料，請確認姓名與寄票人填寫的取票人姓名完全一致，或至前台確認。",
        }

    updated_time = datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d %H:%M")

    return 200, {
        "success": True,
        "concert_code": concert_code,
        "audience_name": audience_name,
        "records": records,
        "count": len(records),
        "updated_time": updated_time,
    }


@app.route("/api/consignment/audience-lookup", methods=["POST"])
def api_consignment_audience_lookup_proxy():
    payload = request.get_json(silent=True) or {}

    status, data = lookup_audience_records(
        concert_code=str(payload.get("concert_code", "tp")).strip().lower(),
        audience_name=str(payload.get("audience_name", "")).strip(),
    )

    return jsonify(data), status


@app.route("/api/search")
def api_search():
    concert_code = request.args.get("concert_code", "tp").strip().lower()
    audience_name = request.args.get("q", "").strip()

    status, data = lookup_audience_records(concert_code, audience_name)

    if not data.get("success"):
        data["error"] = data.get("message", "查詢失敗，請稍後再試。")

    return jsonify(data), status

@app.route("/NTUCO.png")
def favicon_png():
    return send_from_directory(BASE_DIR, "NTUCO.png")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)