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
        sign = "+" if ttype == "income" else "-"
        text += f"{sign}{amount:,.0f} ₽ | {cat} | {comment} | {user}\n"

    await update.message.reply_text(text)

# ---------- MONTH REPORT ----------
async def month_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    months = get_months()

    if not months:
        await update.message.reply_text("Нет данных")
        return

    kb = ReplyKeyboardMarkup([[m] for m in months], resize_keyboard=True)

    await update.message.reply_text("Выбери месяц:", reply_markup=kb)

async def month_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    month = update.message.text

    # защита от случайных сообщений
    if len(month) != 7 or "-" not in month:
        return

    rows = get_month_data(month)

    income = 0
    expense = 0
    per_cat = {}

    for uid, ttype, amount, cat in rows:
        per_cat.setdefault(cat, 0)

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

# ---------- ADD FLOW ----------
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    uid = update.effective_user.id
    name = get_name(uid)

    amount = context.user_data["amount"]
    comment = update.message.text
    mode = context.user_data["mode"]

    if mode == "income":
        add_transaction(name, uid, "income", amount, comment, "💰 Пополнение")

        await update.message.reply_text(
            f"+ {amount:,.0f} ₽\n{comment}\n{name}\n\n💰 Баланс: {get_balance():,.0f} ₽",
            reply_markup=keyboard
        )
        return ConversationHandler.END

    # expense → дальше категория
    context.user_data["comment"] = comment
    await update.message.reply_text("Выберите категорию:", reply_markup=category_keyboard)
    return CATEGORY

async def category_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = get_name(uid)

    amount = context.user_data["amount"]
    comment = context.user_data["comment"]
    category = update.message.text

    add_transaction(name, uid, "expense", amount, comment, category)

    await update.message.reply_text(
        f"- {amount:,.0f} ₽\n{comment}\n{category}\n{name}\n\n💰 Баланс: {get_balance():,.0f} ₽",
        reply_markup=keyboard
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
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_step)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("💰 Баланс"), balance))
    app.add_handler(MessageHandler(filters.Regex("📜 История"), history))
    app.add_handler(MessageHandler(filters.Regex("📆 Отчёт по месяцам"), month_start))

    # важно: второй обработчик после выбора месяца
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, month_report))

    app.add_handler(conv)

    app.run_polling()

if __name__ == "__main__":
    main()
