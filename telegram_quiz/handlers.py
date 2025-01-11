import os
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ConversationHandler, ContextTypes
from loader import list_docx_files, load_questions_from_docx
from quiz import ask_question, send_result_doc
from config import FOLDER_PATH, APPROVED_USERS, ADMIN_ID, save_approved_users

SELECT_TOPIC, SELECT_RANGE, SELECT_COUNT, SELECT_QUESTION_AMOUNT, QUIZ = range(5)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in APPROVED_USERS:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}")],
            [InlineKeyboardButton("❌ Deny", callback_data=f"deny_{user.id}")],
        ])
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❗ Access request from @{user.username or 'unknown'} (ID: {user.id})",
            reply_markup=keyboard,
        )
        await update.message.reply_text("⏳ Your request has been sent to the admin. Please wait.")
        return ConversationHandler.END

    files = list_docx_files(FOLDER_PATH)
    if not files:
        await update.message.reply_text("No test files found in the bot directory.")
        return ConversationHandler.END

    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f[:-5], callback_data=f)] for f in files]
    )
    msg = update.message or (update.callback_query and update.callback_query.message)
    await msg.reply_text("Choose a test:", reply_markup=markup)
    return SELECT_TOPIC


async def select_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    file_name = query.data
    context.user_data["selected_file"] = os.path.join(FOLDER_PATH, file_name)
    context.user_data["questions_raw"] = load_questions_from_docx(context.user_data["selected_file"])
    total = len(context.user_data["questions_raw"])
    await query.message.reply_text(
        f"Selected: {file_name[:-5]} ({total} questions)\nEnter starting question number:"
    )
    return SELECT_RANGE


async def handle_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["q_start"] = int(update.message.text)
        await update.message.reply_text("Enter ending question number:")
        return SELECT_COUNT
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return SELECT_RANGE


async def handle_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        q_end = int(update.message.text)
        q_start = context.user_data["q_start"]
        available = context.user_data["questions_raw"][q_start - 1:q_end]
        context.user_data["available_questions"] = available
        await update.message.reply_text(
            f"How many questions from {q_start} to {q_end}? (max {len(available)})"
        )
        return SELECT_QUESTION_AMOUNT
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return SELECT_COUNT


async def handle_question_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import random
    try:
        n = int(update.message.text.strip())
        available = context.user_data["available_questions"]
        context.user_data["questions"] = random.sample(available, min(len(available), n))
        context.user_data["index"] = 0
        context.user_data["score"] = 0
        context.user_data["streak"] = 0
        await ask_question(update, context)
        return QUIZ
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return SELECT_QUESTION_AMOUNT


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "main_menu":
        return await handle_main_menu(update, context)

    user_answer = query.data.lower()
    correct_letter = context.user_data.get("correct_letter")
    options_dict = context.user_data.get("options_dict", {})
    correct_text = options_dict.get(correct_letter, "Unknown")
    user_text = options_dict.get(user_answer, f"{user_answer}) ?")

    if user_answer == correct_letter:
        context.user_data["score"] += 1
        context.user_data["streak"] = context.user_data.get("streak", 0) + 1
        context.user_data["index"] += 1

        if context.user_data["index"] < len(context.user_data["questions"]):
            await query.message.delete()
            await ask_question(update, context)
        else:
            score = context.user_data["score"]
            total = len(context.user_data["questions"])
            await query.message.edit_text(
                f"🎉 <b>Quiz finished!</b>\nScore: {score}/{total}\n🔥 Streak: {context.user_data.get('streak', 0)}",
                parse_mode="HTML",
            )
            await send_result_doc(update, context)
            return ConversationHandler.END
    else:
        context.user_data["streak"] = 0
        context.user_data.setdefault("incorrect_details", []).append({
            "question": context.user_data["questions"][context.user_data["index"]]["question"],
            "user": user_text,
            "correct": correct_text,
            "options": list(options_dict.values()),
        })

        await query.message.edit_text(
            f"{query.message.text}\n\n❌ <b>Wrong!</b>\n"
            f"Your answer: <code>{user_text}</code>\n"
            f"Correct: <code>{correct_text}</code>",
            parse_mode="HTML",
        )

        context.user_data["index"] += 1
        if context.user_data["index"] < len(context.user_data["questions"]):
            await ask_question(update, context)
        else:
            score = context.user_data["score"]
            total = len(context.user_data["questions"])
            await query.message.reply_text(
                f"🎉 <b>Quiz finished!</b>\nScore: {score}/{total}\n🔥 Streak: {context.user_data.get('streak', 0)}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
                ),
            )
            await send_result_doc(update, context)
            return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await start(update, context)


async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, user_id_str = query.data.split("_", 1)
    user_id = int(user_id_str)

    try:
        user = await context.bot.get_chat(user_id)
        display = f"@{user.username}" if user.username else str(user.first_name)
    except Exception:
        display = str(user_id)

    if action == "approve":
        APPROVED_USERS.add(user_id)
        save_approved_users()
        await query.edit_message_text(f"✅ {display} (ID: {user_id}) approved.")
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Access granted!",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
            ),
        )
    else:
        await query.edit_message_text(f"❌ {display} (ID: {user_id}) denied.")
        await context.bot.send_message(chat_id=user_id, text="❌ Access request denied.")


async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /demote <user_id or @username>")
        return
    target = context.args[0]
    try:
        if target.startswith("@"):
            chat = await context.bot.get_chat(target)
            target_id = chat.id
        else:
            target_id = int(target)

        if target_id in APPROVED_USERS:
            APPROVED_USERS.discard(target_id)
            save_approved_users()
            await update.message.reply_text(f"Removed: {target}")
            await context.bot.send_message(chat_id=target_id, text="Your access has been revoked.")
        else:
            await update.message.reply_text("User not in approved list.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not APPROVED_USERS:
        await update.message.reply_text("No approved users.")
        return
    lines = ["<b>Approved users:</b>\n"]
    for uid in APPROVED_USERS:
        try:
            chat = await context.bot.get_chat(uid)
            name = f"@{chat.username}" if chat.username else chat.first_name
            lines.append(f"• {name} (<code>{uid}</code>)")
        except Exception:
            lines.append(f"• unknown (<code>{uid}</code>)")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
