import sys
import os
import tempfile
import pytest
from docx import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "telegram_quiz"))
from utils import assign_labels, build_progress_bar
from loader import load_questions_from_docx


# --- utils ---

def test_assign_labels_basic():
    options = ["a) First", "b) Second", "c) Third"]
    result = assign_labels(options)
    assert result == ["a) First", "b) Second", "c) Third"]


def test_assign_labels_strips_old_label():
    options = ["a) Alpha", "b) Beta"]
    result = assign_labels(options)
    assert result[0] == "a) Alpha"
    assert result[1] == "b) Beta"


def test_progress_bar_start():
    bar = build_progress_bar(0, 10)
    assert bar.count("█") == 1
    assert len(bar) == 10


def test_progress_bar_end():
    bar = build_progress_bar(9, 10)
    assert "░" not in bar


def test_progress_bar_middle():
    bar = build_progress_bar(4, 10)
    assert len(bar) == 10
    assert "█" in bar and "░" in bar


def test_progress_bar_custom_length():
    bar = build_progress_bar(0, 5, length=20)
    assert len(bar) == 20


# --- loader ---

def _make_docx(paragraphs):
    """Helper: create a temp .docx with given paragraph texts."""
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    doc.save(tmp.name)
    return tmp.name


def test_load_empty_file():
    path = _make_docx([])
    result = load_questions_from_docx(path)
    assert result == []
    os.unlink(path)


def test_load_missing_file():
    result = load_questions_from_docx("/nonexistent/path/file.docx")
    assert result == []


def test_load_single_question():
    path = _make_docx([
        "1. What is 2 + 2?",
        "a) Three",
        "b) Four (+)",
        "c) Five",
    ])
    questions = load_questions_from_docx(path)
    os.unlink(path)

    assert len(questions) == 1
    q = questions[0]
    assert "2 + 2" in q["question"]
    assert q["answer"] == "b"
    assert len(q["options"]) == 3


def test_load_multiple_questions():
    path = _make_docx([
        "1. First question?",
        "a) Wrong",
        "b) Correct (+)",
        "2. Second question?",
        "a) Yes (+)",
        "b) No",
    ])
    questions = load_questions_from_docx(path)
    os.unlink(path)

    assert len(questions) == 2
    assert questions[0]["answer"] == "b"
    assert questions[1]["answer"] == "a"


def test_load_question_no_correct_answer():
    path = _make_docx([
        "1. No correct marked?",
        "a) Option one",
        "b) Option two",
    ])
    questions = load_questions_from_docx(path)
    os.unlink(path)

    assert len(questions) == 1
    assert questions[0]["answer"] is None


def test_load_preserves_question_text():
    path = _make_docx([
        "1. This is a longer question text that spans the line",
        "a) Answer A (+)",
        "b) Answer B",
    ])
    questions = load_questions_from_docx(path)
    os.unlink(path)

    assert "longer question text" in questions[0]["question"]
