import sys
import os

# Make sure each subpackage is importable from tests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for subdir in ("telegram_quiz", "pdf_to_docx", "web"):
    path = os.path.join(ROOT, subdir)
    if path not in sys.path:
        sys.path.insert(0, path)
