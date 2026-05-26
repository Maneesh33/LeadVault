# Lead Email Extractor

A local Streamlit app for extracting email addresses from uploaded files and saving new unique contacts into a selected CSV list.

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

   On Windows, install the 64-bit UB Mannheim Tesseract OCR build:

   <https://ub-mannheim.github.io/Tesseract_Dokumentation/Tesseract_Doku_Windows.html>

   If `winget` is available, you can also run:

   ```powershell
   winget install UB-Mannheim.TesseractOCR
   ```

   Restart this Streamlit app after installing Tesseract. The app also checks the normal
   `C:\Program Files\Tesseract-OCR\tesseract.exe` location automatically.

## Run

```powershell
streamlit run app.py
```

Streamlit will open a local browser page where you can choose a save destination, upload files, extract emails, preview results, download the updated CSV, and save it locally.

## Output

The default master file is saved as:

```text
recipients.csv
```

You can also create separate recipient lists for colleges, cities, domains, or any other bucket. Custom lists are saved in:

```text
recipient_lists/
```

Examples:

```text
recipient_lists/domain7.csv
recipient_lists/hyderabad.csv
recipient_lists/college_abc.csv
```

It contains:

- `email`
- `name_guess`
- `source_files`
- `status`
- `created_at`

If the selected CSV already exists, the app loads it first and adds only new email addresses to that same selected file. Existing rows are kept. Duplicate checking is exact full-email matching inside the selected file.

Use **Manage recipient lists** in the app to delete custom CSV lists you no longer need. The default `recipients.csv` master file is not deleted from that panel.

## Logs

Import and export activity is written to:

```text
logs/import.log
```
