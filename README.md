# unec-exam-suite

A collection of self-study tools built around UNEC/ASOIU exam preparation. Each tool solves a specific part of the workflow — converting PDFs to test files, running quizzes on desktop or in the browser, and checking grades via Telegram.

Built for personal use. Everything actually ran and was used during exam sessions.

---

## What's inside

```
unec-exam-suite/
├── pdf_to_docx/        # Convert exam PDFs to quiz-ready .docx files
├── desktop/            # Tkinter desktop quiz app (image-based questions)
├── telegram_quiz/      # Telegram bot for text-based quizzes from .docx
├── web/                # Flask web quiz with the same image-based format
├── lms_bot/            # Telegram bot that fetches grades from the LMS
└── tests/              # pytest test suite
```

---

## Tools

### 1. `pdf_to_docx` — PDF to quiz converter

Parses exam PDFs (where answers are marked with `√` and wrong options with `•`) and produces a structured `.docx` file that the Telegram quiz bot can read.

**Format expected in the PDF:**
```
1.
Question text here
•
Wrong answer
√
Correct answer
•
Another wrong answer
```

**Usage:**
```bash
cd pdf_to_docx
pip install -r requirements.txt
python convert.py input.pdf output.docx
```

The output `.docx` will have questions numbered like `1. Question text` with options labeled `a)`, `b)`, `c)` and the correct answer marked with `(+)`.

---

### 2. `desktop` — Tkinter quiz app (image questions)

A desktop GUI quiz player for questions where both the question and all answer options are images (screenshots of exam slides). Requires a `quiz_data/` folder with images and a `metadata.json` index.

**`metadata.json` format:**
```json
{
  "q1": {
    "question": "q1_question.png",
    "options": {
      "opt_a.png": "opt_a.png",
      "opt_b.png": "opt_b.png",
      "opt_c.png": "opt_c.png"
    },
    "correct": "opt_b.png"
  }
}
```

**Usage:**
```bash
cd desktop
pip install -r requirements.txt
python quiz_player.py
```

On start it asks for a question range and count. Options are shuffled on each question. Wrong answers are saved to a `.docx` result file. Use `+` / `-` keys to zoom images.

---

### 3. `telegram_quiz` — Telegram bot (text questions from .docx)

A fully async Telegram bot that reads `.docx` files you drop in its folder and runs interactive quizzes via inline buttons. Access is gated — new users send a join request that the admin approves or denies from within Telegram.

**Setup:**
```bash
cd telegram_quiz
pip install -r requirements.txt
cp .env.example .env
# Fill in BOT_TOKEN and ADMIN_ID in .env
```

**Add test files:** drop any `.docx` quiz file (in the format produced by `pdf_to_docx`) into the `telegram_quiz/` folder.

**Run:**
```bash
python main.py
```

**Bot flow:**
1. User sends `/start`
2. If not approved → request goes to admin with Approve / Deny buttons
3. Admin approves → user gets access
4. User picks a test file → selects question range → picks count → quiz begins
5. Each question shows shuffled options as single-letter inline buttons (A, B, C...)
6. Wrong answers show feedback inline; right answers move to next question silently
7. At the end a `.docx` summary with all wrong questions is sent as a file

**Admin commands:**
| Command | Description |
|---|---|
| `/users` | List all approved users |
| `/demote <id or @username>` | Revoke a user's access |

---

### 4. `web` — Flask web quiz (image questions)

Same quiz format as the desktop app but runs in the browser. Useful when sharing with others — just run the server and give them the URL.

**Setup:**
```bash
cd web
pip install -r requirements.txt
```

**Add quiz data:** copy your `quiz_data/` folder (with images and `metadata.json`) into `web/static/quiz_data/`.

**Run:**
```bash
python app.py
# Open http://localhost:5000
```

**Flow:**
- Start page: enter question range or paste specific question numbers (e.g. `12 56 88`)
- Each question shows the question image and option images as clickable buttons
- Wrong answer → review page shows correct vs chosen with colored borders
- Finish page → download `.docx` with all wrong questions

---

### 5. `lms_bot` — LMS grade checker (Telegram)

Fetches grades from the ASOIU LMS (`lms.asoiu.edu.az`) for a list of students and displays them by subject and academic year. Same approve/deny access system as the quiz bot.

**Setup:**
```bash
cd lms_bot
pip install -r requirements.txt
cp .env.example .env
# Fill in BOT_TOKEN, ADMIN_ID, LMS_USERNAME, LMS_PASSWORD
cp data/students.json.example data/students.json
# Edit students.json with real person_id values from the LMS
```

**Run:**
```bash
python bot.py
```

**`data/students.json` format:**
```json
[
  { "name": "John Doe", "person_id": 123456 },
  { "name": "Jane Smith", "person_id": 789012 }
]
```

The bot auto-restarts on crash with a 5-second delay.

---

## Running tests

```bash
pip install pytest python-docx Flask
pytest tests/ -v
```

Tests cover: question loader, PDF parser, progress bar utility, and Flask web routes.

---

## Environment variables

Each bot has its own `.env.example`. Copy it to `.env` and fill in the values. **Never commit `.env` files.**

| Variable | Used in | Description |
|---|---|---|
| `BOT_TOKEN` | telegram_quiz, lms_bot | Telegram bot token from @BotFather |
| `ADMIN_ID` | telegram_quiz, lms_bot | Your Telegram user ID |
| `LMS_USERNAME` | lms_bot | ASOIU LMS login |
| `LMS_PASSWORD` | lms_bot | ASOIU LMS password |

---

## Requirements per tool

| Tool | Key dependencies |
|---|---|
| `pdf_to_docx` | PyMuPDF, python-docx |
| `desktop` | Pillow, python-docx |
| `telegram_quiz` | python-telegram-bot v21, python-docx, python-dotenv |
| `web` | Flask, python-docx |
| `lms_bot` | aiogram v3, requests, python-dotenv |
