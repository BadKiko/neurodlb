#!/usr/bin/env python3
"""
Simple test bot to verify token works.
"""

import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Simple test bot is working!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"You said: {update.message.text}")

def main():
    if not TOKEN:
        print("No token found")
        return

    print(f"Using token: {TOKEN[:10]}...")
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("Starting simple test bot...")
    try:
        application.run_polling()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
