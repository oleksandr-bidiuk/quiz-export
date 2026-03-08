# Quizlet Flashcard Exporter

Small CLI tool to export terms/definitions from a Quizlet set page URL.

## Usage

```bash
python quizlet_exporter.py "https://quizlet.com/<set-id>/<title>/"
```

Write to a file and select format:

```bash
python quizlet_exporter.py "https://quizlet.com/<set-id>/<title>/" -f json -o cards.json
python quizlet_exporter.py "https://quizlet.com/<set-id>/<title>/" -f tsv -o cards.tsv
```

Optional cookie (for 403/CAPTCHA cases):

```bash
python quizlet_exporter.py "https://quizlet.com/<set-id>/<title>/" --cookie "qltj=...; qlts=...; qtkn=..."
```

## HTML GUI

Run local web interface:

```bash
python gui_server.py
```

Then open `http://127.0.0.1:8000` in your browser.

## Notes

- Works by reading `__NEXT_DATA__` JSON embedded in the set page.
- If Quizlet blocks automated access (403/CAPTCHA) or the set is private, export may fail.
- Output columns are `term,definition` for CSV/TSV.
