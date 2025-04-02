import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pdf_to_docx"))
from convert import parse_questions


def test_empty_input():
    assert parse_questions([]) == []


def test_single_question_with_correct():
    lines = [
        "1.",
        "What is the capital of France?",
        "•",
        "Berlin",
        "√",
        "Paris",
        "•",
        "Rome",
    ]
    result = parse_questions(lines)
    assert any("Paris" in line and "(+)" in line for line in result)
    assert any("Berlin" in line and "(+)" not in line for line in result)


def test_correct_answer_marked():
    lines = [
        "1.",
        "Simple question",
        "•",
        "Wrong answer",
        "√",
        "Right answer",
    ]
    result = parse_questions(lines)
    assert any("(+)" in line for line in result)
    correct_lines = [l for l in result if "(+)" in l]
    assert len(correct_lines) == 1
    assert "Right answer" in correct_lines[0]


def test_multiple_questions():
    lines = [
        "1.",
        "First question",
        "•",
        "Option A",
        "√",
        "Option B",
        "2.",
        "Second question",
        "√",
        "Correct one",
        "•",
        "Wrong one",
    ]
    result = parse_questions(lines)
    question_lines = [l for l in result if l and l[0].isdigit()]
    assert len(question_lines) == 2


def test_blank_line_between_questions():
    lines = [
        "1.",
        "Q one",
        "√",
        "Answer",
        "2.",
        "Q two",
        "√",
        "Answer two",
    ]
    result = parse_questions(lines)
    blanks = [l for l in result if l == ""]
    assert len(blanks) >= 1


def test_multiline_answer():
    lines = [
        "1.",
        "Question text",
        "√",
        "First part",
        "second part",
        "•",
        "Other answer",
    ]
    result = parse_questions(lines)
    correct_lines = [l for l in result if "(+)" in l]
    assert len(correct_lines) == 1
    assert "First part" in correct_lines[0]
    assert "second part" in correct_lines[0]


def test_no_options_question():
    lines = [
        "1.",
        "Question with no options",
    ]
    result = parse_questions(lines)
    assert any("Question with no options" in l for l in result)
