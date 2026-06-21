"""Telegram conversation handlers."""

from __future__ import annotations

import random
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from config import (
    ADMIN_ID,
    APPROVED_USERS,
    PENDING_USERS,
    QUIZ_DIR,
    USER_LANGUAGES,
    save_approved_users,
    save_pending_users,
    save_user_languages,
)
from i18n import LANGUAGES, t
from loader import QuizFormatError, list_docx_files, load_questions_from_docx
from quiz import ask_question, send_result_doc


SELECT_LANGUAGE, SELECT_TOPIC, SELECT_RANGE, SELECT_END, SELECT_AMOUNT, QUIZ = range(6)


def _language(user_id: int) -> str:
    return USER_LANGUAGES.get(user_id, "en")


def _message(update: Update):
    return update.message or (update.callback_query and update.callback_query.message)


async def _show_language_picker(update: Update) -> int:
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"lang:{code}")]
        for code, label in LANGUAGES.items()
    ]
    await _message(update).reply_text(
        "Выберите язык / Choose a language / Dil seçin:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_LANGUAGE


async def _show_topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language = _language(update.effective_user.id)
    files = list_docx_files(QUIZ_DIR)
    if not files:
        await _message(update).reply_text(t(language, "no_tests"))
        return ConversationHandler.END

    context.user_data["topic_files"] = files
    keyboard = [
        [InlineKeyboardButton(file_name[:-5], callback_data=f"topic:{index}")]
        for index, file_name in enumerate(files)
    ]
    await _message(update).reply_text(
        t(language, "choose_test"), reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TOPIC


async def _request_or_show_topics(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user = update.effective_user
    language = _language(user.id)
    context.user_data["language"] = language

    if user.id in APPROVED_USERS:
        return await _show_topics(update, context)

    if user.id in PENDING_USERS:
        await _message(update).reply_text(t(language, "request_pending"))
        return ConversationHandler.END

    PENDING_USERS.add(user.id)
    save_pending_users()
    admin_language = _language(ADMIN_ID)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(admin_language, "approve"), callback_data=f"approve:{user.id}"
                ),
                InlineKeyboardButton(
                    t(admin_language, "deny"), callback_data=f"deny:{user.id}"
                ),
            ]
        ]
    )
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=t(
            admin_language,
            "access_request",
            username=user.username or "unknown",
            user_id=user.id,
        ),
        reply_markup=keyboard,
    )
    await _message(update).reply_text(t(language, "request_sent"))
    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.effective_user.id not in USER_LANGUAGES:
        return await _show_language_picker(update)
    return await _request_or_show_topics(update, context)


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _show_language_picker(update)


async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    language = query.data.split(":", 1)[1]
    if language not in LANGUAGES:
        return await _show_language_picker(update)
    USER_LANGUAGES[update.effective_user.id] = language
    save_user_languages()
    context.user_data["language"] = language
    await query.edit_message_text(f"✅ {LANGUAGES[language]}")
    return await _request_or_show_topics(update, context)


async def select_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    language = _language(update.effective_user.id)
    try:
        index = int(query.data.split(":", 1)[1])
        file_name = context.user_data["topic_files"][index]
        selected_file = QUIZ_DIR / file_name
        questions = load_questions_from_docx(selected_file)
        if not questions:
            raise QuizFormatError("no questions")
    except (IndexError, KeyError, ValueError, OSError, QuizFormatError) as error:
        await query.message.reply_text(t(language, "invalid_test", error=escape(str(error))))
        return await _show_topics(update, context)

    context.user_data["selected_file"] = str(selected_file)
    context.user_data["questions_raw"] = questions
    await query.message.reply_text(
        t(language, "selected", name=file_name[:-5], total=len(questions))
    )
    return SELECT_RANGE


async def handle_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language = _language(update.effective_user.id)
    try:
        start_number = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(t(language, "number_required"))
        return SELECT_RANGE

    total = len(context.user_data["questions_raw"])
    if not 1 <= start_number <= total:
        await update.message.reply_text(t(language, "start_out_of_range", total=total))
        return SELECT_RANGE
    context.user_data["q_start"] = start_number
    await update.message.reply_text(t(language, "enter_end"))
    return SELECT_END


async def handle_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language = _language(update.effective_user.id)
    try:
        end_number = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(t(language, "number_required"))
        return SELECT_END

    start_number = context.user_data["q_start"]
    total = len(context.user_data["questions_raw"])
    if not start_number <= end_number <= total:
        await update.message.reply_text(
            t(language, "end_out_of_range", start=start_number, total=total)
        )
        return SELECT_END

    available = context.user_data["questions_raw"][start_number - 1 : end_number]
    context.user_data["q_end"] = end_number
    context.user_data["available_questions"] = available
    await update.message.reply_text(
        t(
            language,
            "enter_amount",
            start=start_number,
            end=end_number,
            maximum=len(available),
        )
    )
    return SELECT_AMOUNT


async def handle_question_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    language = _language(update.effective_user.id)
    try:
        amount = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(t(language, "number_required"))
        return SELECT_AMOUNT

    available = context.user_data["available_questions"]
    if not 1 <= amount <= len(available):
        await update.message.reply_text(
            t(language, "amount_out_of_range", maximum=len(available))
        )
        return SELECT_AMOUNT

    context.user_data.update(
        {
            "questions": random.sample(available, amount),
            "index": 0,
            "score": 0,
            "streak": 0,
            "max_streak": 0,
            "incorrect_details": [],
            "language": language,
        }
    )
    await ask_question(update, context)
    return QUIZ


async def _finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    language = context.user_data.get("language", "en")
    text = t(
        language,
        "finished",
        score=context.user_data["score"],
        total=len(context.user_data["questions"]),
        streak=context.user_data.get("max_streak", 0),
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(t(language, "main_menu"), callback_data="main_menu")]]
        ),
    )
    await send_result_doc(update, context)
    return ConversationHandler.END


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "main_menu":
        return await handle_main_menu(update, context, answered=True)

    _, callback_index, user_answer = query.data.split(":", 2)
    index = context.user_data.get("index", -1)
    if int(callback_index) != index:
        return QUIZ

    displayed = context.user_data["displayed_options"]
    option_map = {option["letter"]: option for option in displayed}
    selected = option_map[user_answer]
    correct = option_map[context.user_data["correct_letter"]]
    language = context.user_data.get("language", "en")

    if selected["correct"]:
        context.user_data["score"] += 1
        context.user_data["streak"] += 1
        context.user_data["max_streak"] = max(
            context.user_data["max_streak"], context.user_data["streak"]
        )
        await query.message.delete()
    else:
        context.user_data["streak"] = 0
        question = context.user_data["questions"][index]
        context.user_data["incorrect_details"].append(
            {
                "number": question["number"],
                "question": question["question"],
                "options": [dict(option) for option in displayed],
                "selected_letter": selected["letter"],
                "selected_text": selected["text"],
                "correct_letter": correct["letter"],
                "correct_text": correct["text"],
            }
        )
        feedback = (
            f"{query.message.text_html}\n\n<b>{escape(t(language, 'wrong'))}</b>\n"
            f"{escape(t(language, 'your_answer'))}: <code>{escape(selected['letter'].upper() + ') ' + selected['text'])}</code>\n"
            f"{escape(t(language, 'correct_answer'))}: <code>{escape(correct['letter'].upper() + ') ' + correct['text'])}</code>"
        )
        await query.message.edit_text(feedback, parse_mode="HTML")

    context.user_data["index"] += 1
    if context.user_data["index"] >= len(context.user_data["questions"]):
        return await _finish_quiz(update, context)
    await ask_question(update, context)
    return QUIZ


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(t(_language(update.effective_user.id), "cancelled"))
    return ConversationHandler.END


async def handle_main_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, answered: bool = False
) -> int:
    if update.callback_query and not answered:
        await update.callback_query.answer()
    context.user_data.clear()
    return await _request_or_show_topics(update, context)


async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return

    action, user_id_text = query.data.split(":", 1)
    user_id = int(user_id_text)
    language = _language(user_id)
    admin_language = _language(ADMIN_ID)
    try:
        user = await context.bot.get_chat(user_id)
        display = f"@{user.username}" if user.username else user.first_name
    except Exception:
        display = str(user_id)

    PENDING_USERS.discard(user_id)
    save_pending_users()
    if action == "approve":
        APPROVED_USERS.add(user_id)
        save_approved_users()
        await query.edit_message_text(
            t(admin_language, "approved", display=display, user_id=user_id)
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=t(language, "access_granted"),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(t(language, "main_menu"), callback_data="main_menu")]]
            ),
        )
    else:
        await query.edit_message_text(
            t(admin_language, "denied", display=display, user_id=user_id)
        )
        await context.bot.send_message(chat_id=user_id, text=t(language, "access_denied"))


async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    language = _language(ADMIN_ID)
    if not context.args:
        await update.message.reply_text(t(language, "usage_demote"))
        return
    target = context.args[0]
    try:
        if target.startswith("@"):
            target_id = (await context.bot.get_chat(target)).id
        else:
            target_id = int(target)
        if target_id not in APPROVED_USERS or target_id == ADMIN_ID:
            await update.message.reply_text(t(language, "not_approved"))
            return
        APPROVED_USERS.discard(target_id)
        save_approved_users()
        await update.message.reply_text(t(language, "removed", target=target))
        await context.bot.send_message(
            chat_id=target_id, text=t(_language(target_id), "access_revoked")
        )
    except Exception as error:
        await update.message.reply_text(t(language, "admin_error", error=escape(str(error))))


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    language = _language(ADMIN_ID)
    users = sorted(user_id for user_id in APPROVED_USERS if user_id != ADMIN_ID)
    if not users:
        await update.message.reply_text(t(language, "no_approved"))
        return
    lines = [t(language, "approved_users")]
    for user_id in users:
        try:
            chat = await context.bot.get_chat(user_id)
            name = f"@{chat.username}" if chat.username else chat.first_name
        except Exception:
            name = "unknown"
        lines.append(f"• {escape(name)} (<code>{user_id}</code>)")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
