from flask import Flask, request
from linebot import WebhookHandler
from linebot.models import MessageEvent, TextMessage
import sqlite3, datetime

app = Flask(__name__)

CHANNEL_SECRET = "ใส่ของคุณ"
handler = WebhookHandler(CHANNEL_SECRET)

conn = sqlite3.connect("chat.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    text TEXT,
    timestamp TEXT
)
""")

@app.route("/webhook", methods=['POST'])
def webhook():
    body = request.get_data(as_text=True)
    signature = request.headers['X-Line-Signature']
    handler.handle(body, signature)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    cursor.execute(
        "INSERT INTO messages (user_id, text, timestamp) VALUES (?, ?, ?)",
        (
            event.source.user_id,
            event.message.text,
            datetime.datetime.now()
        )
    )
    conn.commit()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)