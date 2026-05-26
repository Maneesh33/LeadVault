# Lead Email Extractor

A local Streamlit app for extracting email addresses from uploaded files and saving new unique contacts into `recipients.csv`.

The app only extracts and cleans email addresses. It does not send emails.

## Supported files

- `.csv`
- `.xlsx`
- `.txt`
- `.pdf`
- `.png`
- `.jpg`
- `.jpeg`
- `.webp`

## Setup

1. Open a terminal in this folder:

   ```powershell
   cd lead-email-extractor
   ```

2. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install Python packages:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Install the Tesseract OCR engine for image extraction.

   On Windows, one common option is:

   ```powershell
   winget install UB-Mannheim.TesseractOCR
   ```

   Restart your terminal after installing Tesseract so `pytesseract` can find it on your PATH.

## Run

```powershell
streamlit run app.py
```

Streamlit will open a local browser page where you can upload files, extract emails, preview results, download the updated CSV, and save `recipients.csv` locally.

## Output

The master file is saved as:

```text
recipients.csv
```

It contains:

- `email`
- `name_guess`
- `source_files`
- `status`
- `created_at`

If `recipients.csv` already exists, the app loads it first and adds only new email addresses. Existing rows are kept.

## Logs

Import and export activity is written to:

```text
logs/import.log
```
