import os
import sqlite3
import logging
from datetime import datetime
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

def get_name(uid):
    return USER_NAMES.get(uid, "Неизвестный")

def check_user(update: Update):
    return update.effective_user.id in ALLOWED_USERS

# ---------- UI ----------
keyboard = ReplyKeyboardMarkup(
    [
        ["➕ Пополнить", "➖ Расход"],
        ["💰 Баланс", "📜 История"],
        ["📊 Отчёт", "📆 Отчёт по месяцам"]
    ],
    resize_keyboard=True
)

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    await update.message.reply_text("💰 Бюджет активирован", reply_markup=keyboard)

# ---------- MONTH SELECT ----------
async def month_report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    months = get_months()

    if not months:
        await update.message.reply_text("Нет данных")
        return ConversationHandler.END

    kb = ReplyKeyboardMarkup([[m] for m in months], resize_keyboard=True)

    await update.message.reply_text("Выбери месяц:", reply_markup=kb)
    return MONTH

# ---------- MONTH REPORT ----------
async def month_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    month = update.message.text
    rows = get_month_data(month)

    income = 0
    expense = 0
    per_cat = {}

    for uid, ttype, amount, cat in rows:
        if cat not in per_cat:
            per_cat[cat] = 0

        if ttype == "income":
            income += amount
        else:
            expense += amount
            per_cat[cat] += amount

    result = income - expense

    text = f"📊 Отчёт за {month}\n\n"
    text += f"💰 Доходы: {income:,.0f} ₽\n"
    text += f"💸 Расходы: {expense:,.0f} ₽\n"
    text += f"📈 Итог: {result:,.0f} ₽\n\n"

    text += "📂 Категории:\n"
    for cat, val in per_cat.items():
        text += f"{cat}: {val:,.0f} ₽\n"

    await update.message.reply_text(text, reply_markup=keyboard)
    return ConversationHandler.END

# ---------- PLACEHOLDERS (упрощено) ----------
async def dummy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Функция уже есть в полном коде")

# ---------- MAIN ----------
def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    month_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("📆 Отчёт по месяцам"), month_report_start)],
        states={
            MONTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, month_report)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))

    app.add_handler(month_conv)

    app.run_polling()

if __name__ == "__main__":
    main()
