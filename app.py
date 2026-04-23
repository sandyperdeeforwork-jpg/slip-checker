from flask import Flask, request, jsonify, render_template
import cv2
import requests
import os
from datetime import datetime, timedelta
import pymysql

app = Flask(__name__)

print("🔥 PRODUCTION VERSION 🔥")

# =========================
# 🔑 CONFIG (ควรใช้ ENV)
# =========================
SECRET_KEY = os.getenv("API_KEY")  # 🔥 แนะนำใช้ ENV
API_URL = "https://connect.slip2go.com/api/verify-slip/qr-code/info"

# =========================
# 🔥 DB CONNECT
# =========================
def get_db():
    try:
        return pymysql.connect(
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQLDATABASE"),
            port=int(os.getenv("MYSQLPORT")),
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print("DB ERROR:", e)
        return None

# =========================
# 🌐 VERIFY API
# =========================
def verify_slip(payload):
    try:
        headers = {
            "Authorization": f"Bearer {SECRET_KEY}",
            "Content-Type": "application/json"
        }

        res = requests.post(
            API_URL,
            json={"payload": {"qrCode": payload}},
            headers=headers,
            timeout=10
        )

        if res.status_code != 200:
            print("API STATUS:", res.status_code)
            return {"status": "error"}

        result = res.json()

        if result.get("message") != "Slip found.":
            return {"status": "not_found"}

        d = result.get("data", {})

        return {
            "status": "ok",
            "amount": float(d.get("amount", 0)),
            "date": d.get("dateTime"),
            "transRef": d.get("transRef"),
            "receiver": d.get("receiver", "")
        }

    except Exception as e:
        print("API ERROR:", e)
        return {"status": "error"}

# =========================
# ROUTES
# =========================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        if "file" not in request.files:
            return jsonify({"status": "no_file"})

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"status": "no_file"})

        filepath = os.path.join("uploads", file.filename)
        file.save(filepath)

        # =========================
        # 🔍 QR SCAN (3 ชั้น)
        # =========================
        img = cv2.imread(filepath)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        detector = cv2.QRCodeDetector()

        data, _, _ = detector.detectAndDecode(img)

        if not data:
            data, _, _ = detector.detectAndDecode(gray)

        if not data:
            data, _, _ = detector.detectAndDecode(thresh)

        print("QR DATA:", data)

        if not data:
            return jsonify({"status": "no_qr"})

        # =========================
        # 🌐 VERIFY
        # =========================
        api_result = verify_slip(data)
        print("API RESULT:", api_result)

        if api_result.get("status") == "not_found":
            return jsonify({"status": "invalid"})

        if api_result.get("status") == "error":
            return jsonify({"status": "error"})

        # =========================
        # 🔒 ANTI-FRAUD
        # =========================

        # ✅ เช็คยอดเงิน
        if api_result["amount"] != 100.0:
            return jsonify({"status": "amount_mismatch"})

        # ✅ เช็คเวลา (ไม่เกิน 5 นาที)
        try:
            slip_time = datetime.fromisoformat(api_result["date"])
            now = datetime.now(slip_time.tzinfo)

            if now - slip_time > timedelta(minutes=5):
                return jsonify({"status": "expired"})
        except Exception as e:
            print("TIME CHECK ERROR:", e)

        trans_ref = api_result.get("transRef")

        if not trans_ref:
            return jsonify({"status": "error"})

        # =========================
        # 🔥 DB CHECK (กันซ้ำ)
        # =========================
        db = get_db()

        if db:
            try:
                cursor = db.cursor()

                cursor.execute(
                    "SELECT * FROM slips WHERE trans_ref=%s",
                    (trans_ref,)
                )
                existing = cursor.fetchone()

                if existing:
                    return jsonify({
                        "status": "duplicate",
                        "data": api_result
                    })

                cursor.execute(
                    "INSERT INTO slips (trans_ref, amount) VALUES (%s, %s)",
                    (trans_ref, api_result["amount"])
                )
                db.commit()

            except Exception as e:
                print("DB INSERT ERROR:", e)
                return jsonify({"status": "error"})

            finally:
                db.close()

        # =========================
        # ⏱️ TIME DISPLAY
        # =========================
        time_text = "-"
        try:
            slip_time = datetime.fromisoformat(api_result["date"])
            now = datetime.now(slip_time.tzinfo)
            diff = now - slip_time

            minutes = diff.seconds // 60
            time_text = f"{minutes} นาที"

        except Exception as e:
            print("TIME ERROR:", e)

        api_result["time_passed"] = time_text

        return jsonify({
            "status": "ok",
            "data": api_result
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))