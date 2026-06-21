"""Strict DOCX quiz loader used by the Telegram bot."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document


QUESTION_RE = re.compile(r"^(\d+)[.)]\s*(.+)$")
OPTION_RE = re.compile(r"^([a-z])[.)]\s*(.+)$", re.IGNORECASE)


class QuizFormatError(ValueError):
    pass


def list_docx_files(folder_path: str | Path) -> list[str]:
    folder = Path(folder_path)
    if not folder.exists():
        return []
    return sorted(
        path.name
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".docx" and not path.name.startswith("~$")
    )


def _finish_question(current: dict | None, questions: list[dict]) -> None:
    if current is None:
        return
    number = current["number"]
    options = current["options"]
    answers = [option["id"] for option in options if option.pop("correct")]
    if len(options) < 2:
        raise QuizFormatError(f"question {number} has fewer than two options")
    if len({option["id"] for option in options}) != len(options):
        raise QuizFormatError(f"question {number} has duplicate option labels")
    if len(answers) != 1:
        raise QuizFormatError(f"question {number} has {len(answers)} correct answers")
    current["answer"] = answers[0]
    questions.append(current)


def load_questions_from_docx(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    if not path.exists():
        return []

    document = Document(path)
    lines = [
        re.sub(r"\s+", " ", paragraph.text).strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]
    uses_explicit_marker = any("[[CORRECT]]" in line for line in lines)
    questions: list[dict] = []
    current: dict | None = None
    last_target: tuple[str, int | None] | None = None

    for line in lines:

        question_match = QUESTION_RE.match(line)
        if question_match:
            _finish_question(current, questions)
            current = {
                "number": int(question_match.group(1)),
                "question": question_match.group(2).strip(),
                "options": [],
            }
            last_target = ("question", None)
            continue

        option_match = OPTION_RE.match(line)
        if option_match and current is not None:
            text = option_match.group(2).strip()
            marker_pattern = (
                r"\s*\[\[CORRECT\]\]\s*$"
                if uses_explicit_marker
                else r"\s*\(\+\)\s*$"
            )
            marker = re.search(marker_pattern, text)
            correct = marker is not None
            if marker:
                text = text[: marker.start()].rstrip()
            current["options"].append(
                {
                    "id": option_match.group(1).lower(),
                    "text": text,
                    "correct": correct,
                }
            )
            last_target = ("option", len(current["options"]) - 1)
            continue

        if current is not None and last_target is not None:
            target, index = last_target
            if target == "question":
                current["question"] = f"{current['question']} {line}".strip()
            elif index is not None:
                option = current["options"][index]
                option["text"] = f"{option['text']} {line}".strip()

    _finish_question(current, questions)
    return questions
