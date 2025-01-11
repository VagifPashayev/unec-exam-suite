import os
import random
import tempfile
from html import escape
from datetime import datetime
from docx import Document
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils import build_progress_bar


async def ask_question(update, context):
    i = context.user_data["index"]
    q = context.user_data["questions"][i]

    shuffled = q["options"][:]
    random.shuffle(shuffled)

    labels = ["a)", "b)", "c)", "d)", "e)"]
    relabeled = []
    correct_letter = None

    for idx, opt in enumerate(shuffled):
        old_letter = opt[0]
        text = opt[3:].strip()
        new_opt = f"{labels[idx]} {text}"
        relabeled.append(new_opt)
        if old_letter == q["answer"]:
            correct_letter = labels[idx][0]

    context.user_data["correct_letter"] = correct_letter
    context.user_data["options_dict"] = {opt[0]: opt for opt in relabeled}

    total = len(context.user_data["questions"])
    correct = context.user_data["score"]
    wrong = i - correct
    bar = build_progress_bar(i, total)

    text = (
        f"<b>Question {i + 1} of {total}</b>  {bar}\n"
        f"✅ {correct} | ❌ {wrong} | 🔥 {context.user_data.get('streak', 0)}\n\n"
        f"<b>{escape(q['question'])}</b>\n\n"
    )
    for opt in relabeled:
        text += f"{escape(opt)}\n"

    keyboard = [[InlineKeyboardButton(opt[0].upper(), callback_data=opt[0])] for opt in relabeled]
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def send_result_doc(update, context):
    questions = context.user_data.get("questions", [])
    score = context.user_data.get("score", 0)
    total = len(questions)
    streak = context.user_data.get("streak", 0)
    incorrect = context.user_data.get("incorrect_details", [])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    selected_file = context.user_data.get("selected_file", "unknown")
    test_name = os.path.basename(selected_file).replace(".docx", "")
    q_start = context.user_data.get("q_start", 0)
    filename = f"{test_name} ({q_start}-{q_start + len(questions) - 1} of {len(questions)}).docx"

    doc = Document()
    doc.add_paragraph(f"Quiz Results — {timestamp}")
    doc.add_paragraph(f"Correct: {score} / {total}")
    doc.add_paragraph(f"Incorrect: {total - score}")
    doc.add_paragraph(f"Max streak: {streak}")

    if incorrect:
        doc.add_paragraph("Incorrect questions:")
        for idx, item in enumerate(incorrect, 1):
            doc.add_paragraph(f"\n{idx}. {item['question']}")
            for opt in item.get("options", []):
                doc.add_paragraph(f"   {opt}")
            doc.add_paragraph(f"   Your answer: {item['user']}")
            doc.add_paragraph(f"   Correct: {item['correct']}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        doc.save(tmp.name)
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(tmp.name, "rb"),
            filename=filename,
        )
