# UNEC Exam Suite

Tools for converting UNEC exam PDFs and running quizzes on Telegram, desktop, or the web. The maintained deployment target is the polling-based Telegram bot; it exposes no public port.

## Telegram bot

The bot seeds bundled DOCX banks from `telegram_quiz/quizzes/` into the persistent runtime directory `DATA_DIR/quizzes/`. On a user's first `/start`, it asks for Russian, English, or Azerbaijani and persists the preference. New users then request access from the administrator.

Features:

- strict question-bank validation before a quiz starts;
- safe in-bot DOCX upload, compatibility report, soft deletion, and audit log;
- persistent SQLite-backed access roles (`owner`, `admin`, and `user`);
- original question-bank download for approved users;
- safe answer shuffling without losing the correct-answer mapping;
- validated range and question-count input;
- protection against repeated callback presses;
- score, current streak, and actual best-streak tracking;
- localized Word reports containing every wrong question, all displayed options, the user's answer, and the correct answer;
- `/language`, `/cancel`, `/admin`, `/users`, `/approve`, `/demote`,
  `/promote`, and `/demote_admin` commands.

The `ADMIN_ID` account is the protected owner. Only the owner may grant or
revoke delegated administrator rights. Delegated administrators can approve or
block users and add or remove quiz files. Uploaded banks are accepted only when
every question has 2–26 options, unique numbering, exactly one correct answer,
safe archive contents, and a Telegram-compatible rendered length.

### Local setup

```bash
cd telegram_quiz
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Required secrets:

```dotenv
BOT_TOKEN=replace_with_botfather_token
ADMIN_ID=replace_with_numeric_telegram_user_id
```

Never commit `.env`.

## Converting a PDF

The converter supports both legacy `√`/`•` PDFs and UNEC PDFs where the correct option is red.

```bash
python pdf_to_docx/convert.py input.pdf telegram_quiz/quizzes/output.docx
```

An optional third argument enforces the expected question count:

```bash
python pdf_to_docx/convert.py input.pdf output.docx 1415
```

Conversion fails if a question has fewer than two options, duplicate labels, or anything other than one correct answer. Exact repeated source questions with the same source number are removed, and the final bank is renumbered sequentially.

## Tests

```bash
pip install -r tests/requirements.txt
pip install -r telegram_quiz/requirements.txt -r pdf_to_docx/requirements.txt
pytest tests -q
```

## Docker deployment

The Compose stack uses polling, a dedicated bridge network and state volume, no host ports, a non-root read-only container, automatic restart, Telegram-aware healthcheck, log rotation, and CPU/RAM/PID limits. SQLite state, uploaded quizzes, and the protected trash directory live under `/app/data` in `bot_data`. On the first upgraded start, legacy JSON access lists are migrated and bundled quizzes are copied into this volume.

### First deployment

```bash
sudo install -d -o deploy -g deploy /opt/unec-exam-bot
git clone https://github.com/VagifPashayev/unec-exam-suite.git /opt/unec-exam-bot
cd /opt/unec-exam-bot
cp telegram_quiz/.env.example .env
chmod 600 .env
# Edit BOT_TOKEN and ADMIN_ID without printing them to the terminal.
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

### Update

```bash
cd /opt/unec-exam-bot
git pull --ff-only
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

### Restart and logs

```bash
cd /opt/unec-exam-bot
docker compose restart bot
docker compose logs --follow --tail=200 bot
```

### Back up state and configuration

```bash
cd /opt/unec-exam-bot
mkdir -p backups
chmod 700 backups
VOLUME=$(docker volume ls -q \
  --filter label=com.docker.compose.project=unec-exam-bot \
  --filter label=com.docker.compose.volume=bot_data)
docker run --rm -v "$VOLUME:/data:ro" -v "$PWD/backups:/backup" alpine \
  tar -czf "/backup/bot-data-$(date +%Y%m%d-%H%M%S).tar.gz" -C /data .
cp --preserve=mode .env "backups/env-$(date +%Y%m%d-%H%M%S)"
```

### Roll back application code

```bash
cd /opt/unec-exam-bot
git log --oneline -10
git checkout <known-good-commit>
docker compose config --quiet
docker compose up -d --build
```

Return to the current release later with:

```bash
git switch main
git pull --ff-only
docker compose up -d --build
```

To restore state, stop only this bot stack, extract a selected backup into its `bot_data` volume, and start the stack again. Do not modify another Compose project's networks, volumes, containers, or routes.

## Other tools

- `quiz_creator/`: visual PDF crop tool for image quizzes.
- `desktop/`: Tkinter image-based quiz player.
- `web/`: Flask image-based quiz player.
- `pdf_to_docx/`: PDF-to-DOCX question converter.
