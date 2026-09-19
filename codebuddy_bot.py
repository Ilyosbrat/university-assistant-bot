from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from ddgs import DDGS
import sqlite3

import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

conn = sqlite3.connect("applications.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS deadlines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        school_name TEXT,
        deadline_date TEXT
    )
""")
conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I'm your university application assistant.\n\n"
        "Just type a school name (e.g. 'MIT') and I'll look up its deadline, "
        "requirements, and portfolio tips.\n\n"
        "Other commands:\n"
        "/addschool SchoolName YYYY-MM-DD — manually save a deadline\n"
        "/deadlines — see your saved deadlines"
    )

async def add_school(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        deadline_date = args[-1]
        school_name = " ".join(args[:-1])
        user_id = update.effective_user.id
        cursor.execute(
            "INSERT INTO deadlines (user_id, school_name, deadline_date) VALUES (?, ?, ?)",
            (user_id, school_name, deadline_date)
        )
        conn.commit()
        await update.message.reply_text(f"Saved: {school_name} — deadline {deadline_date}")
    except Exception:
        await update.message.reply_text(
            "Format: /addschool SchoolName YYYY-MM-DD\nExample: /addschool MIT 2026-11-01"
        )

async def deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute(
        "SELECT school_name, deadline_date FROM deadlines WHERE user_id = ? ORDER BY deadline_date ASC",
        (user_id,)
    )
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("You haven't added any schools yet.")
        return
    message = "Your deadlines:\n\n"
    for school_name, deadline_date in rows:
        message += f"{school_name} — {deadline_date}\n"
    await update.message.reply_text(message)

async def school_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    school_name = update.message.text.strip()
    await update.message.reply_text(f"Looking up {school_name}... give me a moment.")

    query = f"{school_name} university application deadline admission requirements 2026"
    results = DDGS().text(query, max_results=5)
    search_context = "\n".join([f"{r['title']}: {r['body']}" for r in results])

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        max_tokens=800,
        messages=[
            {"role": "system", "content": "You help students applying to foreign universities. Based on the search results given, provide: 1) Application deadline, 2) Key admission requirements, 3) One practical portfolio/application tip. Format your reply for a Telegram chat message, NOT a document: use short paragraphs and simple bullet points starting with a dash (-), use *single asterisks* for bold (never tables, never pipes |, never HTML tags like <br>). Keep it concise — under 300 words total. If information is unclear or not found, say so honestly rather than guessing."},
            {"role": "user", "content": f"School: {school_name}\n\nSearch results:\n{search_context}"}
        ]
    )
    reply = response.choices[0].message.content
    await update.message.reply_text(reply, parse_mode="Markdown")

app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addschool", add_school))
app.add_handler(CommandHandler("deadlines", deadlines))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, school_lookup))
app.run_polling()