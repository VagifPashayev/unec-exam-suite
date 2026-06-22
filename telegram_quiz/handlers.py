"""Telegram conversation, access-control, and administration handlers."""

from __future__ import annotations

import asyncio
import os
import random
import tempfile
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from config import QUIZ_DIR, STORAGE, TRASH_DIR
from file_service import MAX_DOCX_BYTES, delete_quiz_file, install_quiz_file
from i18n import LANGUAGES, t
from loader import QuizFormatError, load_questions_from_docx
from quiz import ask_question, send_result_doc


SELECT_LANGUAGE, SELECT_TOPIC, SELECT_RANGE, SELECT_END, SELECT_AMOUNT, QUIZ = range(6)


def _language(user_id: int) -> str:
    return STORAGE.get_language(user_id)


def _message(update: Update):
    return update.message or (update.callback_query and update.callback_query.message)


def _display_user(row) -> str:
    name = f"@{row['username']}" if row["username"] else row["first_name"] or "unknown"
    return f"{escape(name)} (<code>{row['user_id']}</code>)"


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
    files = STORAGE.list_quizzes()
    if not files:
        await _message(update).reply_text(t(language, "no_tests"))
        return ConversationHandler.END

    keyboard = []
    for item in files:
        keyboard.append(
            [
                InlineKeyboardButton(item.title, callback_data=f"topic:{item.id}"),
                InlineKeyboardButton(
                    t(language, "download"), callback_data=f"download:{item.id}"
                ),
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                t(language, "change_language"), callback_data="lang:menu"
            )
        ]
    )
    await _message(update).reply_text(
        t(language, "choose_test"), reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TOPIC


async def _request_or_show_topics(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user = update.effective_user
    previous_status = STORAGE.status(user.id)
    STORAGE.upsert_identity(user.id, user.username, user.first_name)
    language = _language(user.id)
    context.user_data["language"] = language

    if STORAGE.is_approved(user.id):
        return await _show_topics(update, context)
    if previous_status == "blocked":
        await _message(update).reply_text(t(language, "access_denied"))
        return ConversationHandler.END
    if previous_status == "pending":
        await _message(update).reply_text(t(language, "request_pending"))
        return ConversationHandler.END

    STORAGE.request_access(user.id)

    for admin_id in STORAGE.admin_ids():
        admin_language = _language(admin_id)
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
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=t(
                    admin_language,
                    "access_request",
                    username=user.username or "unknown",
                    user_id=user.id,
                ),
                reply_markup=keyboard,
            )
        except Exception:
            continue
    await _message(update).reply_text(t(language, "request_sent"))
    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    user = update.effective_user
    had_language = STORAGE.has_language(user.id)
    STORAGE.upsert_identity(user.id, user.username, user.first_name)
    if not had_language:
        return await _show_language_picker(update)
    return await _request_or_show_topics(update, context)


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _show_language_picker(update)


async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    language = query.data.split(":", 1)[1]
    if language == "menu" or language not in LANGUAGES:
        return await _show_language_picker(update)
    STORAGE.set_language(update.effective_user.id, language)
    context.user_data["language"] = language
    await query.edit_message_text(f"✅ {LANGUAGES[language]}")
    return await _request_or_show_topics(update, context)


async def select_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    language = _language(update.effective_user.id)
    try:
        quiz_id = int(query.data.split(":", 1)[1])
        item = STORAGE.get_quiz(quiz_id)
        if not item:
            raise QuizFormatError("the test is no longer available")
        selected_file = QUIZ_DIR / item.filename
        questions = load_questions_from_docx(selected_file)
        if not questions:
            raise QuizFormatError("no questions")
    except (ValueError, OSError, QuizFormatError) as error:
        await query.message.reply_text(t(language, "invalid_test", error=str(error)))
        return await _show_topics(update, context)

    context.user_data["selected_file"] = str(selected_file)
    context.user_data["questions_raw"] = questions
    await query.message.reply_text(
        t(language, "selected", name=item.title, total=len(questions))
    )
    return SELECT_RANGE


async def download_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    language = _language(update.effective_user.id)
    if not STORAGE.is_approved(update.effective_user.id):
        await query.answer(t(language, "access_denied"), show_alert=True)
        return
    await query.answer()
    try:
        quiz_id = int(query.data.split(":", 1)[1])
        item = STORAGE.get_quiz(quiz_id)
        if not item:
            raise FileNotFoundError
        path = QUIZ_DIR / item.filename
        with path.open("rb") as stream:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=stream,
                filename=item.filename,
                caption=t(
                    language,
                    "original_caption",
                    name=item.title,
                    total=item.question_count,
                ),
            )
    except (ValueError, OSError, FileNotFoundError):
        await query.message.reply_text(t(language, "file_unavailable"))


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
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=t(
            language,
            "finished",
            score=context.user_data["score"],
            total=len(context.user_data["questions"]),
            streak=context.user_data.get("max_streak", 0),
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        t(language, "main_menu"), callback_data="main_menu"
                    )
                ]
            ]
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
    if (
        user_answer not in option_map
        or context.user_data["correct_letter"] not in option_map
    ):
        return QUIZ
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
    context.user_data.pop("awaiting_quiz_upload", None)
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
    actor_id = update.effective_user.id
    if not STORAGE.is_admin(actor_id):
        await query.answer("Forbidden", show_alert=True)
        return
    await query.answer()
    action, user_id_text = query.data.split(":", 1)
    user_id = int(user_id_text)
    user_language = _language(user_id)
    admin_language = _language(actor_id)
    current = STORAGE.status(user_id)
    if current != "pending":
        await query.edit_message_text(t(admin_language, "already_processed"))
        return
    approved = action == "approve"
    STORAGE.set_access(actor_id, user_id, approved)
    rows = [row for row in STORAGE.list_users() if row["user_id"] == user_id]
    display = _display_user(rows[0]) if rows else str(user_id)
    await query.edit_message_text(
        t(
            admin_language,
            "approved" if approved else "denied",
            display=display,
            user_id=user_id,
        ),
        parse_mode="HTML",
    )
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=t(user_language, "access_granted" if approved else "access_denied"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            t(user_language, "main_menu"), callback_data="main_menu"
                        )
                    ]
                ]
            )
            if approved
            else None,
        )
    except Exception:
        pass


async def _resolve_target(context: ContextTypes.DEFAULT_TYPE) -> int:
    target = context.args[0]
    return (
        (await context.bot.get_chat(target)).id
        if target.startswith("@")
        else int(target)
    )


async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor_id = update.effective_user.id
    if not STORAGE.is_admin(actor_id):
        return
    language = _language(actor_id)
    if not context.args:
        await update.message.reply_text(t(language, "usage_demote"))
        return
    try:
        target_id = await _resolve_target(context)
        if STORAGE.role(target_id) in {"owner", "admin"} or not STORAGE.is_approved(
            target_id
        ):
            await update.message.reply_text(t(language, "not_approved"))
            return
        STORAGE.set_access(actor_id, target_id, False)
        await update.message.reply_text(t(language, "removed", target=context.args[0]))
        await context.bot.send_message(
            chat_id=target_id, text=t(_language(target_id), "access_revoked")
        )
    except Exception as error:
        await update.message.reply_text(t(language, "admin_error", error=str(error)))


async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor_id = update.effective_user.id
    if not STORAGE.is_admin(actor_id):
        return
    language = _language(actor_id)
    if not context.args:
        await update.message.reply_text(t(language, "usage_approve_user"))
        return
    try:
        target_id = await _resolve_target(context)
        chat = await context.bot.get_chat(target_id)
        STORAGE.upsert_identity(target_id, chat.username, chat.first_name)
        if STORAGE.role(target_id) == "owner":
            raise ValueError("owner access cannot be changed")
        STORAGE.set_access(actor_id, target_id, True)
        await update.message.reply_text(t(language, "user_approved", target=target_id))
        try:
            await context.bot.send_message(
                chat_id=target_id, text=t(_language(target_id), "access_granted")
            )
        except Exception:
            pass
    except Exception as error:
        await update.message.reply_text(t(language, "admin_error", error=str(error)))


async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor_id = update.effective_user.id
    language = _language(actor_id)
    if not STORAGE.is_owner(actor_id):
        return
    if not context.args:
        await update.message.reply_text(t(language, "usage_promote"))
        return
    try:
        target_id = await _resolve_target(context)
        chat = await context.bot.get_chat(target_id)
        STORAGE.upsert_identity(target_id, chat.username, chat.first_name)
        if not STORAGE.grant_admin(actor_id, target_id):
            raise ValueError("owner role cannot be changed")
        await update.message.reply_text(t(language, "admin_granted", target=target_id))
    except Exception as error:
        await update.message.reply_text(t(language, "admin_error", error=str(error)))


async def demote_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor_id = update.effective_user.id
    language = _language(actor_id)
    if not STORAGE.is_owner(actor_id):
        return
    if not context.args:
        await update.message.reply_text(t(language, "usage_demote_admin"))
        return
    try:
        target_id = await _resolve_target(context)
        if not STORAGE.revoke_admin(actor_id, target_id):
            raise ValueError("user is not a delegated administrator")
        await update.message.reply_text(t(language, "admin_revoked", target=target_id))
    except Exception as error:
        await update.message.reply_text(t(language, "admin_error", error=str(error)))


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor_id = update.effective_user.id
    if not STORAGE.is_admin(actor_id):
        return
    language = _language(actor_id)
    rows = STORAGE.list_users()
    if not rows:
        await _message(update).reply_text(t(language, "no_approved"))
        return
    lines = [t(language, "users_title")]
    for row in rows[:80]:
        lines.append(f"• {_display_user(row)} — {row['role']}/{row['status']}")
    if len(rows) > 80:
        lines.append(t(language, "list_truncated", count=len(rows) - 80))
    lines.append(t(language, "users_help"))
    await _message(update).reply_text("\n".join(lines), parse_mode="HTML")


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor_id = update.effective_user.id
    if not STORAGE.is_admin(actor_id):
        return
    language = _language(actor_id)
    keyboard = [
        [
            InlineKeyboardButton(
                t(language, "admin_add_file"), callback_data="admin:add"
            )
        ],
        [InlineKeyboardButton(t(language, "admin_files"), callback_data="admin:files")],
        [InlineKeyboardButton(t(language, "admin_users"), callback_data="admin:users")],
        [
            InlineKeyboardButton(
                t(language, "admin_admins"), callback_data="admin:admins"
            )
        ],
        [InlineKeyboardButton(t(language, "admin_audit"), callback_data="admin:audit")],
    ]
    await _message(update).reply_text(
        t(language, "admin_title"), reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_admin_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    actor_id = update.effective_user.id
    language = _language(actor_id)
    if not STORAGE.is_admin(actor_id):
        await query.answer("Forbidden", show_alert=True)
        return
    await query.answer()
    data = query.data
    if data == "admin:add":
        context.user_data["awaiting_quiz_upload"] = True
        await query.message.reply_text(t(language, "upload_prompt"))
        return
    if data == "admin:users":
        await list_users(update, context)
        return
    if data == "admin:admins":
        rows = [
            row for row in STORAGE.list_users() if row["role"] in {"owner", "admin"}
        ]
        lines = [t(language, "admins_title")]
        lines.extend(f"• {_display_user(row)} — {row['role']}" for row in rows)
        if STORAGE.is_owner(actor_id):
            lines.append(t(language, "admins_help"))
        await query.message.reply_text("\n".join(lines), parse_mode="HTML")
        return
    if data == "admin:audit":
        rows = STORAGE.list_audit()
        lines = [t(language, "audit_title")]
        lines.extend(
            f"• <code>{escape(row['created_at'])}</code> — <code>{row['actor_id']}</code> "
            f"{escape(row['action'])}: {escape(row['target'] or '—')}"
            for row in rows
        )
        await query.message.reply_text("\n".join(lines), parse_mode="HTML")
        return
    if data == "admin:files":
        files = STORAGE.list_quizzes()
        if not files:
            await query.message.reply_text(t(language, "no_tests"))
            return
        keyboard = [
            [
                InlineKeyboardButton(
                    f"🗑 {item.title} ({item.question_count})",
                    callback_data=f"admin:delete:{item.id}",
                )
            ]
            for item in files[:50]
        ]
        await query.message.reply_text(
            t(language, "delete_choose"), reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    if data.startswith("admin:delete:"):
        quiz_id = int(data.rsplit(":", 1)[1])
        item = STORAGE.get_quiz(quiz_id)
        if not item:
            await query.message.reply_text(t(language, "file_unavailable"))
            return
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        t(language, "confirm_delete"),
                        callback_data=f"admin:confirm:{quiz_id}",
                    ),
                    InlineKeyboardButton(
                        t(language, "cancel_delete"), callback_data="admin:files"
                    ),
                ]
            ]
        )
        await query.message.reply_text(
            t(language, "delete_confirm", name=item.title), reply_markup=keyboard
        )
        return
    if data.startswith("admin:confirm:"):
        quiz_id = int(data.rsplit(":", 1)[1])
        item = await asyncio.to_thread(
            delete_quiz_file, quiz_id, actor_id, STORAGE, QUIZ_DIR, TRASH_DIR
        )
        await query.message.reply_text(
            t(language, "file_deleted", name=item.title)
            if item
            else t(language, "file_unavailable")
        )


async def handle_quiz_upload(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    actor_id = update.effective_user.id
    if not STORAGE.is_admin(actor_id) or not context.user_data.get(
        "awaiting_quiz_upload"
    ):
        return
    language = _language(actor_id)
    document = update.message.document
    if not document.file_name or not document.file_name.lower().endswith(".docx"):
        await update.message.reply_text(t(language, "upload_docx_only"))
        return
    if document.file_size and document.file_size > MAX_DOCX_BYTES:
        await update.message.reply_text(
            t(language, "upload_too_large", megabytes=MAX_DOCX_BYTES // 1024 // 1024)
        )
        return
    await update.message.reply_text(t(language, "upload_checking"))
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temporary:
            temporary_path = temporary.name
        telegram_file = await document.get_file()
        await telegram_file.download_to_drive(custom_path=temporary_path)
        item, report = await asyncio.to_thread(
            install_quiz_file,
            temporary_path,
            document.file_name,
            actor_id,
            STORAGE,
            QUIZ_DIR,
        )
        context.user_data.pop("awaiting_quiz_upload", None)
        warning_text = "\n".join(f"⚠️ {value}" for value in report.warnings)
        await update.message.reply_text(
            t(language, "upload_success", name=item.title, total=report.question_count)
            + (f"\n{warning_text}" if warning_text else "")
        )
    except Exception as error:
        await update.message.reply_text(t(language, "upload_failed", error=str(error)))
    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
