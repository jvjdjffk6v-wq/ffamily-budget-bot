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

AMOUNT, COMMENT, CATEGORY = range(3)

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
    res = c.fetchone()[0]
    conn.close()
    return res or 0

def get_history(limit=10):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT user, type, amount, comment, category
        FROM transactions
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_report():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT type, amount, category
        FROM transactions
    """)
    rows = c.fetchall()
    conn.close()

    income = 0
    expense = 0
    per_cat = {}

    for ttype, amount, cat in rows:
        per_cat.setdefault(cat, 0)

        if ttype == "income":
            income += amount
        else:
            expense += amount
            per_cat[cat] += amount

    return income, expense, per_cat

def get_name(uid):
    return USER_NAMES.get(uid, "Неизвестный")

def check_user(update: Update):
    return update.effective_user.id in ALLOWED_USERS

# ---------- UI ----------
keyboard = ReplyKeyboardMarkup(
    [
        ["➕ Пополнить", "➖ Расход"],
        ["💰 Баланс", "📜 История"],
        ["📊 Отчёт"]
    ],
    resize_keyboard=True
)

category_keyboard = ReplyKeyboardMarkup([[c] for c in CATEGORIES], resize_keyboard=True)

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    await update.message.reply_text("💰 Бюджет активирован", reply_markup=keyboard)

# ---------- BALANCE ----------
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"💰 Баланс: {get_balance():,.0f} ₽")

# ---------- HISTORY ----------
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_history()

    text = "📜 Последние операции:\n\n"
    for user, ttype, amount, comment, cat in rows:
        sign = "+" if ttype == "income" else "-"
        text += f"{sign}{amount:,.0f} ₽ | {cat} | {comment} | {user}\n"

    await update.message.reply_text(text)

# ---------- REPORT ----------
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    income, expense, per_cat = get_report()
    result = income - expense

    text = "📊 Общий отчёт\n\n"
    text += f"💰 Доходы: {income:,.0f} ₽\n"
    text += f"💸 Расходы: {expense:,.0f} ₽\n"
    text += f"📈 Итог: {result:,.0f} ₽\n\n"

    text += "📂 По категориям:\n"
    for cat, val in per_cat.items():
        text += f"{cat}: {val:,.0f} ₽\n"

    await update.message.reply_text(text)

# ---------- ADD FLOW ----------
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["mode"] = "income" if "Пополнить" in text else "expense"

    await update.message.reply_text("Введите сумму:")
    return AMOUNT

async def amount_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["amount"] = float(update.message.text.replace(",", "."))
    except:
        await update.message.reply_text("Введите число")
        return AMOUNT

    await update.message.reply_text("Комментарий:")
    return COMMENT

async def comment_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = get_name(uid)

    amount = context.user_data["amount"]
    comment = update.message.text
    mode = context.user
