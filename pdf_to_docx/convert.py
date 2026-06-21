"""Convert supported exam PDFs to the DOCX format used by the Telegram bot.

Two source layouts are supported:

* legacy PDFs that place ``√`` before the correct option and ``•`` before
  incorrect options;
* UNEC PDFs whose correct option text is red and whose visible lines use the
  ``1. 1) question`` / ``a) A) option`` layout.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import fitz  # PyMuPDF
from docx import Document


LEGACY_MARKERS = {"•", "√", "вЂў", "в€љ"}
CORRECT_MARKERS = {"√", "в€љ"}
QUESTION_RE = re.compile(r"^(\d+)\.\s+(\d+)\)\s*(.+)$")
OPTION_RE = re.compile(r"^([a-e])\)\s+(?:[A-E]\)\s*)?(.+)$", re.IGNORECASE)
REFERENCE_RE = re.compile(r"(?:^|\s)ədəbiyyat\s*:", re.IGNORECASE)


@dataclass(frozen=True)
class StyledLine:
    text: str
    has_red_text: bool
    page: int


def _is_red(color: int) -> bool:
    """Return True for the dark-red answer color used by UNEC PDFs."""

    red = (color >> 16) & 0xFF
    green = (color >> 8) & 0xFF
    blue = color & 0xFF
    return red >= 150 and green < 150 and blue < 150 and red > green * 1.4


def extract_styled_lines(pdf_path: str | Path) -> list[StyledLine]:
    """Extract visually ordered lines while preserving red-answer metadata."""

    result: list[StyledLine] = []
    with fitz.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            payload = page.get_text("dict", sort=True)
            for block in payload.get("blocks", []):
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    text = "".join(span.get("text", "") for span in spans).strip()
                    if not text:
                        continue
                    result.append(
                        StyledLine(
                            text=text,
                            has_red_text=any(
                                span.get("text", "").strip()
                                and _is_red(int(span.get("color", 0)))
                                for span in spans
                            ),
                            page=page_number,
                        )
                    )
    return result


def extract_lines(pdf_path: str | Path) -> list[str]:
    """Extract plain lines for legacy marker-based PDFs."""

    with fitz.open(pdf_path) as pdf:
        return [line for page in pdf for line in page.get_text().splitlines()]


def _clean_fragment(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_colored_questions(lines: Iterable[StyledLine]) -> list[dict]:
    """Parse a colored UNEC question bank into validated question records."""

    questions: list[dict] = []
    current: dict | None = None
    in_reference = False

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        if current["options"]:
            questions.append(current)
        current = None

    for line in lines:
        text = _clean_fragment(line.text)
        question_match = QUESTION_RE.match(text)
        if question_match:
            finish()
            current = {
                # The second visible number belongs to the actual question.
                # One source page contains the typo ``81. 381)``.
                "number": int(question_match.group(2)),
                "question": _clean_fragment(question_match.group(3)),
                "options": [],
                "source_page": line.page,
            }
            in_reference = False
            continue

        if current is None:
            continue

        option_match = OPTION_RE.match(text)
        if option_match and not in_reference:
            current["options"].append(
                {
                    "id": option_match.group(1).lower(),
                    "text": _clean_fragment(option_match.group(2)),
                    "correct": line.has_red_text,
                }
            )
            continue

        if REFERENCE_RE.search(text):
            in_reference = True
            continue

        if in_reference or text in {"-", "Detalizasiya"} or re.fullmatch(r"\(\d+\)", text):
            continue

        if current["options"]:
            option = current["options"][-1]
            option["text"] = _clean_fragment(f"{option['text']} {text}")
            option["correct"] = option["correct"] or line.has_red_text
        else:
            current["question"] = _clean_fragment(f"{current['question']} {text}")

    finish()

    # The source PDF repeats a complete 20-question block. Keep the first
    # occurrence and only remove byte-for-byte semantic duplicates.
    unique: list[dict] = []
    seen: set[tuple] = set()
    for question in questions:
        key = (
            question["number"],
            question["question"].casefold(),
            tuple(
                (option["text"].casefold(), option["correct"])
                for option in question["options"]
            ),
        )
        if key not in seen:
            seen.add(key)
            unique.append(question)

    # The repeated block also leaves a 401-420 numbering gap. Present a
    # contiguous range to quiz users while retaining the source number for
    # diagnostics.
    for sequential_number, question in enumerate(unique, start=1):
        question["source_number"] = question["number"]
        question["number"] = sequential_number
    return unique


def validate_questions(
    questions: Sequence[dict], *, expected_count: int | None = None
) -> None:
    """Fail conversion instead of silently producing an unusable quiz bank."""

    if not questions:
        raise ValueError("No questions were detected in the PDF")
    if expected_count is not None and len(questions) != expected_count:
        raise ValueError(f"Expected {expected_count} questions, found {len(questions)}")

    errors: list[str] = []
    seen_numbers: set[int] = set()
    for question in questions:
        number = question["number"]
        options = question["options"]
        correct = [option for option in options if option["correct"]]
        option_ids = [option["id"] for option in options]

        if number in seen_numbers:
            errors.append(f"question {number}: duplicate number")
        seen_numbers.add(number)
        if not question["question"]:
            errors.append(f"question {number}: empty text")
        if len(options) < 2:
            errors.append(f"question {number}: only {len(options)} options")
        if len(option_ids) != len(set(option_ids)):
            errors.append(f"question {number}: duplicate option labels")
        if len(correct) != 1:
            errors.append(f"question {number}: {len(correct)} correct options")

    if errors:
        preview = "; ".join(errors[:10])
        suffix = f"; and {len(errors) - 10} more" if len(errors) > 10 else ""
        raise ValueError(f"Invalid question bank: {preview}{suffix}")


def questions_to_lines(questions: Sequence[dict]) -> list[str]:
    result: list[str] = []
    for question in questions:
        result.append(f"{question['number']}. {question['question']}")
        for option in question["options"]:
            suffix = " [[CORRECT]]" if option["correct"] else ""
            result.append(f"{option['id']}) {option['text']}{suffix}")
        result.append("")
    return result


def parse_questions(lines: Sequence[str]) -> list[str]:
    """Parse the repository's legacy marker layout (kept for compatibility)."""

    result: list[str] = []
    option_letters = "abcdefghijklmnopqrstuvwxyz"
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not re.match(r"^\d+\.$", line):
            i += 1
            continue

        question_number = line
        i += 1
        question_parts: list[str] = []
        while i < len(lines):
            candidate = lines[i].strip()
            if candidate in LEGACY_MARKERS or re.match(r"^\d+\.$", candidate):
                break
            question_parts.append(candidate)
            i += 1
        result.append(f"{question_number} {' '.join(question_parts)}")

        option_idx = 0
        while i + 1 < len(lines):
            marker = lines[i].strip()
            if re.match(r"^\d+\.$", marker):
                break
            if marker not in LEGACY_MARKERS:
                i += 1
                continue

            answer_parts = [lines[i + 1].strip()]
            is_correct = marker in CORRECT_MARKERS
            i += 2
            while i < len(lines):
                continuation = lines[i].strip()
                if continuation in LEGACY_MARKERS or re.match(r"^\d+\.$", continuation):
                    break
                answer_parts.append(continuation)
                i += 1
            suffix = " (+)" if is_correct else ""
            result.append(
                f"{option_letters[option_idx]}) {' '.join(answer_parts)}{suffix}"
            )
            option_idx += 1
        result.append("")

    return result


def save_docx(lines: Sequence[str], output_path: str | Path = "output.docx") -> None:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(output_path)


def convert_pdf(
    pdf_path: str | Path,
    output_path: str | Path,
    *,
    expected_count: int | None = None,
) -> int:
    styled_lines = extract_styled_lines(pdf_path)
    colored_questions = parse_colored_questions(styled_lines)
    if colored_questions:
        validate_questions(colored_questions, expected_count=expected_count)
        output_lines = questions_to_lines(colored_questions)
        count = len(colored_questions)
    else:
        output_lines = parse_questions([line.text for line in styled_lines])
        count = sum(1 for line in output_lines if re.match(r"^\d+\.\s", line))
        if not count:
            raise ValueError("No supported question format was detected")

    save_docx(output_lines, output_path)
    return count


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("Usage: python convert.py input.pdf [output.docx] [expected_count]")
        return 2

    pdf_path = args[0]
    output_path = args[1] if len(args) > 1 else "output.docx"
    expected_count = int(args[2]) if len(args) > 2 else None
    count = convert_pdf(pdf_path, output_path, expected_count=expected_count)
    print(f"Saved {count} questions to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
