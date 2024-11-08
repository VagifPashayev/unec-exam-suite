import re
import sys
import fitz  # PyMuPDF
from docx import Document


def extract_lines(pdf_path):
    doc = fitz.open(pdf_path)
    lines = []
    for page in doc:
        lines.extend(page.get_text().splitlines())
    return lines


def parse_questions(lines):
    result = []
    option_letters = "abcdefghijklmnopqrstuvwxyz"
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if re.match(r"^\d+\.$", line):
            question_number = line
            i += 1

            question_parts = []
            while i < len(lines):
                l = lines[i].strip()
                if l.startswith(("•", "√")) or re.match(r"^\d+\.$", l):
                    break
                question_parts.append(l)
                i += 1

            result.append(f"{question_number} {' '.join(question_parts)}")

            option_idx = 0
            while i + 1 < len(lines):
                marker = lines[i].strip()
                next_line = lines[i + 1].strip()

                if re.match(r"^\d+\.$", marker):
                    break

                if marker in ("•", "√"):
                    is_correct = marker == "√"
                    answer_parts = [next_line]
                    i += 2

                    while i < len(lines):
                        cont = lines[i].strip()
                        if cont.startswith(("•", "√")) or re.match(r"^\d+\.$", cont):
                            break
                        answer_parts.append(cont)
                        i += 1

                    letter = option_letters[option_idx]
                    suffix = " (+)" if is_correct else ""
                    result.append(f"{letter}) {' '.join(answer_parts)}{suffix}")
                    option_idx += 1
                else:
                    i += 1

            result.append("")
        else:
            i += 1

    return result


def save_docx(lines, output_path="output.docx"):
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(output_path)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "file.pdf"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "output.docx"

    lines = extract_lines(pdf_path)
    questions = parse_questions(lines)
    save_docx(questions, output_path)
