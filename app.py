from flask import Flask, request, jsonify, render_template
import cv2
import requests
import os
from datetime import datetime
import os
from urllib.parse import urlparse
import pymysql

# 🔥 ถ้ามี MYSQL_URL ให้ใช้ (Railway)
if os.getenv("MYSQL_URL"):
    url = urlparse(os.getenv("MYSQL_URL"))

    db = pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:],
        port=url.port,
        cursorclass=pymysql.cursors.DictCursor
    )
else:
    # fallback (local)
    db = None

cursor = db.cursor() if db else None

app = Flask(__name__)

# 🔑 API
SECRET_KEY = "+ixZdmZFGS7_lFepb5tSUtA4Z++tRyrPsmycEuA7f8s="
API_URL = "https://connect.slip2go.com/api/verify-slip/qr-code/info"

# 🔥 กันสลิปซ้ำ (จำในเครื่อง)
USED_SLIPS = {}


# =========================
# 🔥 STEP 1: ยิง API
# =========================
def verify_slip(payload):
    try:
        headers = {
            "Authorization": f"Bearer {SECRET_KEY}",
            "Content-Type": "application/json"
        }

        data = {"payload": {"qrCode": payload}}

        res = requests.post(API_URL, json=data, headers=headers)

        print("STATUS:", res.status_code)
        print("RAW:", res.text)

        if res.status_code != 200:
            return {"status": "error"}

        result = res.json()

        if result.get("message") != "Slip found.":
            return {"status": "not_found"}

        d = result.get("data", {})

        sender = d.get("sender", {}).get("account", {})
        receiver = d.get("receiver", {}).get("account", {})

        return {
            "status": "ok",
            "amount": str(d.get("amount", "-")),
            "sender_name": sender.get("nameTh") or sender.get("name") or "-",
            "receiver_name": receiver.get("nameTh") or receiver.get("name") or "-",
            "sender_account": sender.get("bank", {}).get("account") or "-",
            "receiver_account": receiver.get("bank", {}).get("account") or "-",
            "date": d.get("dateTime"),
            "transRef": d.get("transRef")
        }

    except Exception as e:
        print("API ERROR:", e)
        return {"status": "error"}


# =========================
# 🔥 ROUTE
# =========================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    try:
        # =========================
        # 📁 รับไฟล์
        # =========================
        if "file" not in request.files:
            return jsonify({"status": "no_file"})

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"status": "no_file"})

        filepath = os.path.join("uploads", file.filename)
        file.save(filepath)

        # =========================
        # 🔍 อ่าน QR
        # =========================
        img = cv2.imread(filepath)

        detector = cv2.QRCodeDetector()
        data, bbox, _ = detector.detectAndDecode(img)

        if not data:
            return jsonify({"status": "no_qr"})

        payload = data
        print("PAYLOAD:", payload)

        # =========================
        # 🌐 เรียก API
        # =========================
        api_result = verify_slip(payload)

        if api_result.get("status") != "ok":
            return jsonify({"status": "invalid"})

        # =========================
        # ⏱️ คำนวณเวลาโอน
        # =========================
        time_text = "-"

        try:
            slip_time_str = api_result.get("date")

            if slip_time_str:
                slip_time = datetime.fromisoformat(slip_time_str)

                if slip_time.tzinfo is None:
                    now = datetime.now()
                else:
                    now = datetime.now(slip_time.tzinfo)

                diff = now - slip_time

                days = diff.days
                hours = diff.seconds // 3600
                minutes = (diff.seconds % 3600) // 60

                # 🔥 ปรับให้สวย
                if days == 0:
                    time_text = f"{hours} ชั่วโมง {minutes} นาที"
                else:
                    time_text = f"{days} วัน {hours} ชั่วโมง {minutes} นาที"

        except Exception as e:
            print("TIME ERROR:", e)

        # 👉 ใส่ค่าเข้า result
        api_result["time_passed"] = time_text

        # =========================
        # 🔁 เช็คสลิปซ้ำ
        # =========================
        trans_ref = api_result.get("transRef")

        if not trans_ref:
            return jsonify({"status": "invalid"})

        if trans_ref in USED_SLIPS:
            return jsonify({
                "status": "duplicate",
                "data": api_result
            })

        # 👉 บันทึกว่าใช้แล้ว
        USED_SLIPS[trans_ref] = True

        # =========================
        # ✅ ผ่าน
        # =========================
        return jsonify({
            "status": "ok",
            "data": api_result
        })

    except Exception as e:
        import traceback
        traceback.print_exc()

        return jsonify({
            "status": "error",
            "message": str(e)
        })


# =========================
# 🔥 RUN
# =========================
if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))