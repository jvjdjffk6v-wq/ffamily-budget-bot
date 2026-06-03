import os
import sqlite3
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

TOKEN = os.getenv("TOKEN")

ALLOWED_USERS = [414499892, 8764803039]

USER_NAMES = {
    414499892: "Дмитрий",
    8764803039: "Ксения"
}

DB_NAME = "budget.db"

AMOUNT, COMMENT, CATEGORY, MONTH = range(4)

logging.basicConfig(level=logging.INFO)

CATEGORIES = ["🍔 Еда", "🚕 Транспорт", "🏠 Дом", "🎉 Развлечения", "📦 Другое"]

# ---------- DB ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            comment TEXT,
            category TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_transaction(user, user_id, ttype, amount, comment, category):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions (user, user_id, type, amount, comment, category)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user, user_id, ttype, amount, comment, category))
    conn.commit()
    conn.close()

def get_balance():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT SUM(CASE WHEN type='income' THEN amount ELSE -amount END)
        FROM transactions
    """)
    result = c.fetchone()[0]
    conn.close()
    return result or 0

def get_history(limit=10):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT user, type, amount, comment, category, timestamp
        FROM transactions
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_months():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT strftime('%Y-%m', timestamp)
        FROM transactions
        ORDER BY timestamp DESC
        LIMIT 6
    """)
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

def get_month_data(month):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT user_id, type, amount, category
        FROM transactions
        WHERE strftime('%Y-%m', timestamp) = ?
    """, (month,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_name(uid):
    return USER_NAMES.get(uid, "Неизвестный")

def check_user(update: Update):
    return update.effective_user.id in ALLOWED_USERS

# ---------- UI ----------
keyboard = ReplyKeyboardMarkup(
    [
        ["➕ Пополнить", "➖ Расход"],
        ["💰 Баланс", "📜 История"],
        ["📆 Отчёт по месяцам"]
    ],
    resize_keyboard=True
)

category_keyboard = ReplyKeyboardMarkup([[c] for c in CATEGORIES], resize_keyboard=True)

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    await update.message.reply_text("💰 Семейный бюджет активирован", reply_markup=keyboard)

# ---------- BALANCE ----------
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"💰 Баланс: {get_balance():,.0f} ₽")

# ---------- HISTORY ----------
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_history()

    text = "📜 Последние операции:\n\n"
    for r in rows:
        user, ttype, amount, comment, cat, ts = r
        sign = "+" if ttype == "income
