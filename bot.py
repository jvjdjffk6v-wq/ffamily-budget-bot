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

AMOUNT, COMMENT = range(2)

logging.basicConfig(level=logging.INFO)

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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_transaction(user, user_id, ttype, amount, comment):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions (user, user_id, type, amount, comment)
        VALUES (?, ?, ?, ?, ?)
    """, (user, user_id, ttype, amount, comment))
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
        SELECT user, type, amount, comment, timestamp
        FROM transactions
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

# ---------- ACCESS ----------
def check_user(update: Update):
    return update.effective_user.id in ALLOWED_USERS

def get_name(user_id):
    return USER_NAMES.get(user_id, "Неизвестный")

# ---------- UI ----------
keyboard = ReplyKeyboardMarkup(
    [
        ["➕ Пополнить", "➖ Расход"],
        ["💰 Баланс", "📜 История"],
        ["📊 Отчёт"]
    ],
    resize_keyboard=True
)

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    await update.message.reply_text(
        "💰 Семейный бюджет активирован",
        reply_markup=keyboard
    )

# ---------- BALANCE ----------
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    await update.message.reply_text(f"💰 Баланс: {get_balance():,.0f} ₽")

# ---------- HISTORY ----------
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return

    rows = get_history()

    text = "📜 Последние операции:\n\n"
    for r in rows:
        user, ttype, amount, comment, ts = r
        sign = "+" if ttype == "income" else "-"
        text += f"{sign}{amount:,.0f} ₽ | {comment} | {user}\n"

    await update.message.reply_text(text)

# ---------- REPORT ----------
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT user_id, type, amount
        FROM transactions
        WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')
    """)
    rows = c.fetchall()
    conn.close()

    income = 0
    expense = 0
    per_user = {}

    for uid, ttype, amount in rows:
        name = get_name(uid)

        if name not in per_user:
            per_user[name] = {"income": 0, "expense": 0}

        if ttype == "income":
            income += amount
            per_user[name]["income"] += amount
        else:
            expense += amount
            per_user[name]["expense"] += amount

    result = income - expense

    text = "📊 Отчёт за месяц\n\n"
    text += f"💰 Доходы: {income:,.0f} ₽\n"
    text += f"💸 Расходы: {expense:,.0f} ₽\n"
    text += f"📈 Итог: {result:,.0f} ₽\n\n"

    for name, data in per_user.items():
        text += f"👤 {name}:\n"
        text += f"   +{data['income']:,.0f} ₽ / -{data['expense']:,.0f} ₽\n\n"

    await update.message.reply_text(text)

# ---------- CONVERSATION ----------
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return ConversationHandler.END

    context.user_data["mode"] = "income" if "Пополнить" in update.message.text else "expense"
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
    if not check_user(update):
        return ConversationHandler.END

    amount = context.user_data["amount"]
    comment = update.message.text
    mode = context.user_data["mode"]

    user_id = update.effective_user.id
    user_name = get_name(user_id)

    if mode == "income":
        add_transaction(user_name, user_id, "income", amount, comment)
        sign = "+"
    else:
        add_transaction(user_name, user_id, "expense", amount, comment)
        sign = "-"

    await update.message.reply_text(
        f"{sign} {amount:,.0f} ₽\n{comment}\n{user_name}\n\n💰 Баланс: {get_balance():,.0f} ₽"
    )

    return ConversationHandler.END

# ---------- MAIN ----------
def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("➕ Пополнить|➖ Расход"), add_start)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_step)],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, comment_step)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(filters.Regex("💰 Баланс"), balance))
    app.add_handler(MessageHandler(filters.Regex("📜 История"), history))
    app.add_handler(MessageHandler(filters.Regex("📊 Отчёт"), report))

    app.add_handler(conv)

    app.run_polling()

if __name__ == "__main__":
    main()
