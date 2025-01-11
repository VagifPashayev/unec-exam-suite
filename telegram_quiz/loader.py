import os
from docx import Document
from utils import assign_labels


def list_docx_files(folder_path):
    return sorted(f for f in os.listdir(folder_path) if f.endswith(".docx"))


def load_questions_from_docx(file_path):
    if not os.path.exists(file_path):
        return []

    document = Document(file_path)
    questions = []
    current_question = None
    current_options = []
    correct_answer = None

    for para in document.paragraphs:
        line = para.text.strip()
        if not line:
            continue

        if line[0].isdigit() and "." in line[:5]:
            if current_question is not None:
                questions.append({
                    "question": current_question,
                    "options": assign_labels(current_options),
                    "answer": correct_answer.lower() if correct_answer else None,
                })
            current_question = line.split(".", 1)[1].strip()
            current_options = []
            correct_answer = None

        elif line[:2] in ("a)", "b)", "c)", "d)", "e)"):
            if "(+)" in line:
                correct_answer = line[0]
                line = line.replace("(+)", "").strip()
            current_options.append(line)

        else:
            if current_question is not None:
                current_question += "\n" + line

    if current_question is not None:
        questions.append({
            "question": current_question,
            "options": assign_labels(current_options),
            "answer": correct_answer.lower() if correct_answer else None,
        })

    return questions
