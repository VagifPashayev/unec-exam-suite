"""Telegram polling application entry point."""

from __future__ import annotations

import logging
import warnings

from telegram import Update
from telegram.error import TelegramError
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import STORAGE, TOKEN, validate_config
from handlers import (
    QUIZ,
    SELECT_AMOUNT,
    SELECT_END,
    SELECT_LANGUAGE,
    SELECT_RANGE,
    SELECT_TOPIC,
    cancel,
    admin_panel,
    approve_user,
    demote_admin,
    demote_user,
    download_quiz,
    handle_admin_callback,
    handle_approval,
    handle_callback,
    handle_end,
    handle_main_menu,
    handle_question_amount,
    handle_quiz_upload,
    handle_range,
    language_command,
    list_users,
    promote_user,
    select_language,
    select_topic,
    start,
)
from i18n import t


class TokenRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if TOKEN:
            record.msg = record.getMessage().replace(TOKEN, "<redacted>")
            record.args = ()
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for handler in logging.getLogger().handlers:
    handler.addFilter(TokenRedactingFilter())
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.request").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

# The conversation is intentionally tracked per user/chat, not per message.
# Stale answer callbacks are rejected by the embedded question index.
warnings.filterwarnings(
    "ignore",
    message=r"If 'per_message=False'.*",
    category=PTBUserWarning,
)


async def error_handler(update: Update | None, context) -> None:
    LOGGER.error(
        "Unhandled exception while processing an update",
        exc_info=(type(context.error), context.error, context.error.__traceback__),
    )
    try:
        if update and update.effective_chat:
            user_id = update.effective_user.id if update.effective_user else 0
            language = STORAGE.get_language(user_id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=t(language, "generic_error"),
            )
    except TelegramError:
        LOGGER.warning("Could not send the error notification", exc_info=True)


def build_application():
    validate_config()
    application = ApplicationBuilder().token(TOKEN).build()
    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("language", language_command),
            CallbackQueryHandler(handle_main_menu, pattern=r"^main_menu$"),
        ],
        states={
            SELECT_LANGUAGE: [CallbackQueryHandler(select_language, pattern=r"^lang:(ru|en|az)$")],
            SELECT_TOPIC: [
                CallbackQueryHandler(select_topic, pattern=r"^topic:\d+$"),
                CallbackQueryHandler(select_language, pattern=r"^lang:menu$"),
            ],
            SELECT_RANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_range)],
            SELECT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_end)],
            SELECT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question_amount)
            ],
            QUIZ: [
                CallbackQueryHandler(
                    handle_callback, pattern=r"^(?:answer:\d+:[a-z]|main_menu)$"
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    application.add_handler(CallbackQueryHandler(handle_approval, pattern=r"^(?:approve|deny):\d+$"), group=0)
    application.add_handler(CallbackQueryHandler(download_quiz, pattern=r"^download:\d+$"), group=0)
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^admin:"), group=0)
    application.add_handler(MessageHandler(filters.Document.ALL, handle_quiz_upload), group=0)
    application.add_handler(CommandHandler("admin", admin_panel), group=0)
    application.add_handler(CommandHandler("users", list_users), group=0)
    application.add_handler(CommandHandler("approve", approve_user), group=0)
    application.add_handler(CommandHandler("demote", demote_user), group=0)
    application.add_handler(CommandHandler("promote", promote_user), group=0)
    application.add_handler(CommandHandler("demote_admin", demote_admin), group=0)
    application.add_handler(conversation, group=1)
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    build_application().run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
