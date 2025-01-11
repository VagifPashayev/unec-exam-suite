import logging
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from config import TOKEN
from handlers import (
    start, select_topic, handle_range, handle_count, handle_question_amount,
    handle_callback, cancel, handle_main_menu, handle_approval, demote_user, list_users,
    SELECT_TOPIC, SELECT_RANGE, SELECT_COUNT, SELECT_QUESTION_AMOUNT, QUIZ,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def error_handler(update: Update, context):
    logging.exception("Unhandled exception:")
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Something went wrong. Try again.",
            )
    except TelegramError:
        pass


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_TOPIC: [CallbackQueryHandler(select_topic)],
            SELECT_RANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_range)],
            SELECT_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_count)],
            SELECT_QUESTION_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question_amount)],
            QUIZ: [CallbackQueryHandler(handle_callback)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CallbackQueryHandler(handle_approval, pattern=r"^(approve|deny)_\d+$"))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_main_menu, pattern="^main_menu$"))
    app.add_handler(CommandHandler("demote", demote_user))
    app.add_handler(CommandHandler("users", list_users))
    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
