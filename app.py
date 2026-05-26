from __future__ import annotations

import io
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st
from PIL import Image
from pypdf import PdfReader
import pytesseract


APP_DIR = Path(__file__).resolve().parent
RECIPIENTS_PATH = APP_DIR / "recipients.csv"
LOG_DIR = APP_DIR / "logs"
LOG_PATH = LOG_DIR / "import.log"

REQUIRED_COLUMNS = ["email", "name_guess", "source_files", "status", "created_at"]
ALLOWED_EXTENSIONS = ["csv", "xlsx", "txt", "pdf", "png", "jpg", "jpeg", "webp"]

EMAIL_TOKEN_REGEX = re.compile(r"\S+@\S+")
EMAIL_REGEX = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
    r"(?![A-Za-z0-9._%+\-])"
)
VALID_EMAIL_REGEX = re.compile(
    r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)


def setup_logger() -> logging.Logger:
    """Create the import logger that writes to logs/import.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("lead_email_extractor")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        logger.addHandler(handler)

    return logger


LOGGER = setup_logger()


def clean_email(raw_email: str) -> Optional[str]:
    """Normalize an email candidate and return None when it is invalid."""
    email = str(raw_email).strip().lower()
    email = re.sub(r"\s+", "", email)
    email = email.strip("<>()[]{}\"'")
    email = email.rstrip(".,;:!?)]}\"'")

    if VALID_EMAIL_REGEX.match(email):
        return email

    return None


def extract_emails_from_text(text: str) -> Tuple[List[str], int]:
    """Find email addresses in text and count email-like values that fail validation."""
    valid_emails: List[str] = []
    invalid_count = 0

    for token in EMAIL_TOKEN_REGEX.findall(text or ""):
        matches = EMAIL_REGEX.findall(token)

        if not matches:
            invalid_count += 1
            continue

        for match in matches:
            cleaned_email = clean_email(match)
            if cleaned_email:
                valid_emails.append(cleaned_email)
            else:
                invalid_count += 1

    return valid_emails, invalid_count


def guess_name_from_email(email: str) -> str:
    """Build a simple name guess from the part before the @ symbol."""
    local_part = email.split("@", 1)[0]
    name = re.sub(r"[._\-]+", " ", local_part).strip()
    return name.title()


def dataframe_to_searchable_text(dataframe: pd.DataFrame) -> str:
    """Turn every cell in a dataframe into searchable plain text."""
    if dataframe.empty:
        return ""

    text_values = dataframe.fillna("").astype(str).to_numpy().ravel()
    return "\n".join(text_values)


def read_csv_text(file_bytes: bytes) -> str:
    """Read a CSV file and return all cell values as text."""
    last_error: Optional[Exception] = None

    for encoding in ["utf-8", "utf-8-sig", "latin-1"]:
        try:
            dataframe = pd.read_csv(
                io.BytesIO(file_bytes),
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
            )
            return dataframe_to_searchable_text(dataframe)
        except pd.errors.EmptyDataError:
            return ""
        except UnicodeDecodeError as error:
            last_error = error

    if last_error:
        raise last_error

    return ""


def read_excel_text(file_bytes: bytes) -> str:
    """Read every sheet and every cell from an Excel workbook."""
    workbook = pd.read_excel(
        io.BytesIO(file_bytes),
        sheet_name=None,
        dtype=str,
        keep_default_na=False,
        engine="openpyxl",
    )

    sheet_text = []
    for sheet_name, dataframe in workbook.items():
        sheet_text.append(str(sheet_name))
        sheet_text.append(dataframe_to_searchable_text(dataframe))

    return "\n".join(sheet_text)


def read_txt_text(file_bytes: bytes) -> str:
    """Read a plain text file with common encodings."""
    last_error: Optional[Exception] = None

    for encoding in ["utf-8", "utf-8-sig", "latin-1"]:
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError as error:
            last_error = error

    if last_error:
        raise last_error

    return ""


def read_pdf_text(file_bytes: bytes) -> str:
    """Extract text from each page of a PDF file."""
    reader = PdfReader(io.BytesIO(file_bytes))
    page_text = []

    for page in reader.pages:
        page_text.append(page.extract_text() or "")

    return "\n".join(page_text)


def read_image_text(file_bytes: bytes) -> str:
    """Run OCR on an image and return the detected text."""
    image = Image.open(io.BytesIO(file_bytes))

    try:
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as error:
        raise RuntimeError(
            "Tesseract OCR engine was not found. Install Tesseract and make sure it is on PATH."
        ) from error


def extract_text_from_file(file_name: str, file_bytes: bytes) -> str:
    """Choose the right text reader based on the uploaded file extension."""
    extension = Path(file_name).suffix.lower()

    if extension == ".csv":
        return read_csv_text(file_bytes)
    if extension == ".xlsx":
        return read_excel_text(file_bytes)
    if extension == ".txt":
        return read_txt_text(file_bytes)
    if extension == ".pdf":
        return read_pdf_text(file_bytes)
    if extension in [".png", ".jpg", ".jpeg", ".webp"]:
        return read_image_text(file_bytes)

    raise ValueError(f"Unsupported file type: {extension}")


def load_existing_recipients() -> pd.DataFrame:
    """Load recipients.csv if it exists, otherwise return an empty master table."""
    if not RECIPIENTS_PATH.exists() or RECIPIENTS_PATH.stat().st_size == 0:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    try:
        dataframe = pd.read_csv(RECIPIENTS_PATH, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    for column in REQUIRED_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

    return dataframe[REQUIRED_COLUMNS]


def save_recipients(dataframe: pd.DataFrame) -> None:
    """Save the master recipient table to recipients.csv."""
    dataframe.to_csv(RECIPIENTS_PATH, index=False)
    LOGGER.info("Exported recipients.csv with %s rows", len(dataframe))


def get_existing_email_set(dataframe: pd.DataFrame) -> Set[str]:
    """Create a lookup set so existing recipients are not added again."""
    existing_emails = set()

    if "email" not in dataframe.columns:
        return existing_emails

    for email_value in dataframe["email"]:
        cleaned_email = clean_email(str(email_value))
        if cleaned_email:
            existing_emails.add(cleaned_email)

    return existing_emails


def process_uploaded_files(uploaded_files: Iterable) -> Dict[str, object]:
    """Extract emails from every uploaded file while keeping failures isolated."""
    email_counts: Counter[str] = Counter()
    email_sources: Dict[str, Set[str]] = defaultdict(set)
    file_results = []
    failed_files = []
    invalid_emails_skipped = 0

    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name

        try:
            file_bytes = uploaded_file.getvalue()
            text = extract_text_from_file(file_name, file_bytes)
            emails, invalid_count = extract_emails_from_text(text)

            invalid_emails_skipped += invalid_count
            email_counts.update(emails)

            for email in emails:
                email_sources[email].add(file_name)

            file_results.append(
                {
                    "file": file_name,
                    "emails_found": len(emails),
                    "unique_emails": len(set(emails)),
                    "invalid_emails_skipped": invalid_count,
                }
            )
            LOGGER.info(
                "Processed %s | extracted=%s | unique=%s | invalid=%s",
                file_name,
                len(emails),
                len(set(emails)),
                invalid_count,
            )
        except Exception as error:
            failed_files.append({"file": file_name, "error": str(error)})
            LOGGER.exception("Failed to process %s", file_name)

    return {
        "email_counts": email_counts,
        "email_sources": email_sources,
        "file_results": file_results,
        "failed_files": failed_files,
        "invalid_emails_skipped": invalid_emails_skipped,
    }


def merge_with_master(
    existing_dataframe: pd.DataFrame,
    email_counts: Counter[str],
    email_sources: Dict[str, Set[str]],
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, int]]:
    """Add only new unique emails to the master recipients table."""
    existing_emails = get_existing_email_set(existing_dataframe)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_rows = []
    preview_rows = []
    duplicate_emails_skipped = 0

    for email in sorted(email_counts):
        source_files = ", ".join(sorted(email_sources[email]))

        if email in existing_emails:
            duplicate_emails_skipped += email_counts[email]
            preview_status = "duplicate_existing"
        else:
            duplicate_emails_skipped += email_counts[email] - 1
            preview_status = "new"
            new_rows.append(
                {
                    "email": email,
                    "name_guess": guess_name_from_email(email),
                    "source_files": source_files,
                    "status": "new",
                    "created_at": now,
                }
            )

        preview_rows.append(
            {
                "email": email,
                "name_guess": guess_name_from_email(email),
                "source_files": source_files,
                "status": preview_status,
                "times_found": email_counts[email],
            }
        )

    new_dataframe = pd.DataFrame(new_rows, columns=REQUIRED_COLUMNS)
    preview_dataframe = pd.DataFrame(
        preview_rows,
        columns=["email", "name_guess", "source_files", "status", "times_found"],
    )

    updated_dataframe = pd.concat(
        [existing_dataframe, new_dataframe], ignore_index=True
    )

    stats = {
        "total_emails_found": sum(email_counts.values()),
        "new_unique_emails_added": len(new_rows),
        "duplicate_emails_skipped": duplicate_emails_skipped,
    }

    return updated_dataframe, preview_dataframe, stats


def show_metrics(stats: Dict[str, int]) -> None:
    """Display the import summary metrics requested by the app."""
    metric_columns = st.columns(5)
    metric_columns[0].metric("Total files uploaded", stats["total_files_uploaded"])
    metric_columns[1].metric("Total emails found", stats["total_emails_found"])
    metric_columns[2].metric(
        "New unique emails added", stats["new_unique_emails_added"]
    )
    metric_columns[3].metric(
        "Duplicate emails skipped", stats["duplicate_emails_skipped"]
    )
    metric_columns[4].metric(
        "Invalid emails skipped", stats["invalid_emails_skipped"]
    )


def run_app() -> None:
    """Render the Streamlit interface."""
    st.set_page_config(page_title="Lead Email Extractor", layout="wide")
    st.title("Lead Email Extractor")
    st.caption("Extract and clean email addresses locally. This app does not send emails.")

    uploaded_files = st.file_uploader(
        "Upload lead files",
        type=ALLOWED_EXTENSIONS,
        accept_multiple_files=True,
    )

    process_clicked = st.button(
        "Extract emails",
        type="primary",
        disabled=not uploaded_files,
    )

    if process_clicked and uploaded_files:
        LOGGER.info(
            "Import started | files=%s | names=%s",
            len(uploaded_files),
            ", ".join(uploaded_file.name for uploaded_file in uploaded_files),
        )

        with st.spinner("Extracting emails..."):
            existing_dataframe = load_existing_recipients()
            processed = process_uploaded_files(uploaded_files)
            updated_dataframe, preview_dataframe, merge_stats = merge_with_master(
                existing_dataframe,
                processed["email_counts"],
                processed["email_sources"],
            )
            save_recipients(updated_dataframe)

        stats = {
            "total_files_uploaded": len(uploaded_files),
            "invalid_emails_skipped": processed["invalid_emails_skipped"],
            **merge_stats,
        }

        st.session_state["stats"] = stats
        st.session_state["preview_dataframe"] = preview_dataframe
        st.session_state["file_results"] = pd.DataFrame(processed["file_results"])
        st.session_state["failed_files"] = pd.DataFrame(processed["failed_files"])
        st.session_state["updated_dataframe"] = updated_dataframe

        LOGGER.info(
            "Import complete | found=%s | new=%s | duplicates=%s | invalid=%s",
            stats["total_emails_found"],
            stats["new_unique_emails_added"],
            stats["duplicate_emails_skipped"],
            stats["invalid_emails_skipped"],
        )

    if "stats" in st.session_state:
        show_metrics(st.session_state["stats"])

        st.subheader("Extracted emails preview")
        st.dataframe(
            st.session_state["preview_dataframe"],
            use_container_width=True,
            hide_index=True,
        )

        if not st.session_state["file_results"].empty:
            with st.expander("File processing details"):
                st.dataframe(
                    st.session_state["file_results"],
                    use_container_width=True,
                    hide_index=True,
                )

        if not st.session_state["failed_files"].empty:
            st.error("Some files could not be processed.")
            st.dataframe(
                st.session_state["failed_files"],
                use_container_width=True,
                hide_index=True,
            )

        csv_data = st.session_state["updated_dataframe"].to_csv(index=False).encode(
            "utf-8"
        )

        left_button, right_button = st.columns([1, 1])
        with left_button:
            st.download_button(
                "Download updated recipients.csv",
                data=csv_data,
                file_name="recipients.csv",
                mime="text/csv",
            )

        with right_button:
            if st.button("Export recipients.csv locally"):
                save_recipients(st.session_state["updated_dataframe"])
                st.success(f"Saved to {RECIPIENTS_PATH}")

    elif RECIPIENTS_PATH.exists() and RECIPIENTS_PATH.stat().st_size > 0:
        existing_dataframe = load_existing_recipients()
        st.subheader("Current recipients.csv")
        st.dataframe(existing_dataframe, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    run_app()
