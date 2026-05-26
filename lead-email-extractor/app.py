from __future__ import annotations

import io
import logging
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st
import numpy as np
from PIL import Image
from PIL import ImageFilter
from PIL import ImageOps
from pypdf import PdfReader
import pytesseract


APP_DIR = Path(__file__).resolve().parent
RECIPIENTS_PATH = APP_DIR / "recipients.csv"
LISTS_DIR = APP_DIR / "recipient_lists"
LOG_DIR = APP_DIR / "logs"
LOG_PATH = LOG_DIR / "import.log"

REQUIRED_COLUMNS = ["email", "name_guess", "source_files", "status", "created_at"]
ALLOWED_EXTENSIONS = ["csv", "xlsx", "txt", "pdf", "png", "jpg", "jpeg", "webp"]
CREATE_NEW_LIST_OPTION = "Create a new recipient list"

EMAIL_TOKEN_REGEX = re.compile(r"\S+@\S+")
EMAIL_REGEX = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
    r"(?![A-Za-z0-9_%+\-])"
)
VALID_EMAIL_REGEX = re.compile(
    r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)

TESSERACT_COMMON_PATHS = [
    APP_DIR / "tools" / "Tesseract-OCR" / "tesseract.exe",
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]

JOINED_EMAIL_TLD_REGEX = re.compile(
    r"\.(com|net|org|edu|gov|in|co|ai|io|info|biz|me|us|uk|ca|au|de|fr|nl|tech|online)"
    r"(?=[A-Za-z0-9_%+\-][A-Za-z0-9._%+\-]*@)",
    re.IGNORECASE,
)
COMMON_PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "rediffmail.com",
}


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


def configure_tesseract() -> bool:
    """Find Tesseract on Windows when it is installed but not added to PATH."""
    tesseract_from_path = shutil.which("tesseract")
    if tesseract_from_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_from_path
        return True

    for tesseract_path in TESSERACT_COMMON_PATHS:
        if tesseract_path.exists():
            pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)
            return True

    return False


def clean_email(raw_email: str) -> Optional[str]:
    """Normalize an email candidate and return None when it is invalid."""
    email = str(raw_email).strip().lower()
    email = re.sub(r"\s+", "", email)
    email = email.strip("<>()[]{}\"'")
    email = email.rstrip(".,;:!?)]}\"'")

    if VALID_EMAIL_REGEX.match(email):
        return email

    return None


def is_suspicious_ocr_email(email: str) -> bool:
    """Skip OCR fragments that look like only the tail of a longer email."""
    local_part, domain = email.split("@", 1)

    if local_part.isdigit() and domain in COMMON_PUBLIC_EMAIL_DOMAINS:
        return True

    if local_part.isdigit() and len(local_part) <= 4:
        return True

    return False


def remove_probable_ocr_truncations(emails: List[str]) -> List[str]:
    """Remove shorter OCR emails when a longer email clearly contains the same tail."""
    unique_emails = list(dict.fromkeys(emails))
    emails_to_remove = set()

    for email in unique_emails:
        local_part, domain = email.split("@", 1)

        for other_email in unique_emails:
            if email == other_email:
                continue

            other_local_part, other_domain = other_email.split("@", 1)
            if domain != other_domain:
                continue

            is_short_tail = other_local_part.endswith(local_part)
            is_small_missing_prefix = 0 < len(other_local_part) - len(local_part) <= 2

            if is_short_tail and (local_part.isdigit() or is_small_missing_prefix):
                emails_to_remove.add(email)
                break

    return [email for email in emails if email not in emails_to_remove]


def repair_split_email_line(line: str) -> str:
    """Repair OCR lines where Tesseract inserts spaces inside one email address."""
    repaired_line = line
    repaired_line = re.sub(
        r"([A-Za-z0-9._%+\-])\s*@\s*([A-Za-z0-9.\-])",
        r"\1@\2",
        repaired_line,
    )
    repaired_line = re.sub(
        r"(@[A-Za-z0-9.\-]+)\s+\.\s+([A-Za-z]{2,})",
        r"\1.\2",
        repaired_line,
    )

    previous_line = None
    while previous_line != repaired_line:
        previous_line = repaired_line
        repaired_line = re.sub(
            r"(?<![A-Za-z0-9._%+\-])([A-Za-z0-9._%+\-]{2,})\s+([0-9]{1,8}@)",
            r"\1\2",
            repaired_line,
        )

    return repaired_line


def prepare_text_for_email_extraction(text: str) -> str:
    """Fix common OCR/list formatting issues before regex extraction."""
    repaired_lines = [repair_split_email_line(line) for line in (text or "").splitlines()]
    prepared_text = "\n".join(repaired_lines)

    # OCR and pasted lists may glue two emails together:
    # maneesh33@gmail.commaneeshmaahi@gmail.com
    # becomes:
    # maneesh33@gmail.com maneeshmaahi@gmail.com
    return JOINED_EMAIL_TLD_REGEX.sub(lambda match: f".{match.group(1)} ", prepared_text)


def extract_emails_from_text(text: str, apply_ocr_cleanup: bool = False) -> Tuple[List[str], int]:
    """Find email addresses in text and count email-like values that fail validation."""
    prepared_text = prepare_text_for_email_extraction(text)
    valid_emails: List[str] = []
    invalid_count = 0

    for match in EMAIL_REGEX.finditer(prepared_text):
        cleaned_email = clean_email(match.group(0))
        if cleaned_email and apply_ocr_cleanup and is_suspicious_ocr_email(cleaned_email):
            invalid_count += 1
        elif cleaned_email:
            valid_emails.append(cleaned_email)
        else:
            invalid_count += 1

    for token in EMAIL_TOKEN_REGEX.findall(prepared_text):
        if not EMAIL_REGEX.search(token):
            invalid_count += 1

    if apply_ocr_cleanup:
        filtered_emails = remove_probable_ocr_truncations(valid_emails)
        invalid_count += len(valid_emails) - len(filtered_emails)
        valid_emails = filtered_emails

    return valid_emails, invalid_count


def guess_name_from_email(email: str) -> str:
    """Build a simple name guess from the part before the @ symbol."""
    local_part = email.split("@", 1)[0]
    name = re.sub(r"[._\-]+", " ", local_part).strip()
    return name.title()


def slugify_list_name(list_name: str) -> str:
    """Convert a user-entered list name into a safe CSV file name."""
    cleaned_name = list_name.strip().lower()
    cleaned_name = re.sub(r"\.csv$", "", cleaned_name, flags=re.IGNORECASE)
    cleaned_name = re.sub(r"[^a-z0-9._\- ]+", "", cleaned_name)
    cleaned_name = re.sub(r"\s+", "_", cleaned_name).strip("._-")

    return cleaned_name


def get_custom_list_path(list_name: str) -> Path:
    """Return the CSV path for a custom recipient list."""
    safe_name = slugify_list_name(list_name)
    if not safe_name:
        raise ValueError("Enter a recipient list name before extracting emails.")

    return LISTS_DIR / f"{safe_name}.csv"


def list_recipient_files() -> List[Path]:
    """Return the available recipient CSV files the user can choose from."""
    LISTS_DIR.mkdir(parents=True, exist_ok=True)

    files = [RECIPIENTS_PATH]
    files.extend(sorted(LISTS_DIR.glob("*.csv")))
    return files


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


def crop_screenshot_header(image: Image.Image) -> Image.Image:
    """Crop the dark mobile screenshot toolbar when it is present."""
    grayscale_image = ImageOps.grayscale(image)
    pixels = np.array(grayscale_image)
    image_height = pixels.shape[0]
    scan_limit = min(image_height - 20, 280)

    for y_position in range(80, scan_limit):
        if pixels[y_position : y_position + 10].mean() > 205:
            return image.crop((0, max(0, y_position - 5), image.width, image.height))

    return image


def remove_table_lines(image: Image.Image) -> Image.Image:
    """Remove strong table borders so OCR can read the email text more clearly."""
    grayscale_image = ImageOps.grayscale(image)
    pixels = np.array(grayscale_image)
    black_pixels = pixels < 90
    height, width = black_pixels.shape
    cleaned_pixels = pixels.copy()

    horizontal_lines = np.where(black_pixels.mean(axis=1) > 0.50)[0]
    vertical_lines = np.where(black_pixels.mean(axis=0) > 0.70)[0]

    for y_position in horizontal_lines:
        cleaned_pixels[
            max(0, y_position - 2) : min(height, y_position + 3),
            :,
        ] = 255

    for x_position in vertical_lines:
        cleaned_pixels[
            :,
            max(0, x_position - 2) : min(width, x_position + 3),
        ] = 255

    return Image.fromarray(cleaned_pixels).filter(ImageFilter.SHARPEN)


def build_ocr_image_variants(image: Image.Image) -> List[Image.Image]:
    """Create a few OCR-friendly image versions for screenshots and tables."""
    cropped_image = crop_screenshot_header(image)
    no_lines_image = remove_table_lines(image)
    cropped_no_lines_image = remove_table_lines(cropped_image)

    return [
        no_lines_image,
        cropped_no_lines_image,
        ImageOps.grayscale(image),
    ]


def read_image_text(file_bytes: bytes) -> str:
    """Run OCR on an image and return the detected text."""
    configure_tesseract()
    image = Image.open(io.BytesIO(file_bytes))

    try:
        ocr_text_blocks = []
        for ocr_image in build_ocr_image_variants(image):
            ocr_text_blocks.append(pytesseract.image_to_string(ocr_image, config="--psm 6"))

        return "\n".join(ocr_text_blocks)
    except pytesseract.TesseractNotFoundError as error:
        raise RuntimeError(
            "Tesseract OCR engine was not found. Install Tesseract OCR, then restart this app. "
            "CSV, Excel, TXT, and PDF files still work without Tesseract."
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


def load_existing_recipients(csv_path: Path) -> pd.DataFrame:
    """Load the selected recipient CSV, otherwise return an empty table."""
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    try:
        dataframe = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    for column in REQUIRED_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

    return dataframe[REQUIRED_COLUMNS]


def save_recipients(dataframe: pd.DataFrame, csv_path: Path) -> None:
    """Save the selected recipient table to its CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(csv_path, index=False)
    LOGGER.info("Exported %s with %s rows", csv_path.name, len(dataframe))


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
            is_image_file = Path(file_name).suffix.lower() in [
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            ]
            emails, invalid_count = extract_emails_from_text(
                text,
                apply_ocr_cleanup=is_image_file,
            )

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


def choose_output_file() -> Tuple[Path, bool]:
    """Render the destination picker and return the chosen CSV path."""
    st.subheader("Save destination")

    available_files = list_recipient_files()
    labels_by_path = {
        RECIPIENTS_PATH: "Master - recipients.csv",
        **{
            csv_path: f"List - {csv_path.stem}"
            for csv_path in available_files
            if csv_path != RECIPIENTS_PATH
        },
    }

    options = available_files + [Path(CREATE_NEW_LIST_OPTION)]
    selected_option = st.selectbox(
        "Choose recipient file",
        options,
        format_func=lambda option: CREATE_NEW_LIST_OPTION
        if str(option) == CREATE_NEW_LIST_OPTION
        else labels_by_path.get(option, option.name),
    )

    if str(selected_option) == CREATE_NEW_LIST_OPTION:
        new_list_name = st.text_input(
            "New list name",
            placeholder="domain7, hyderabad, college_abc",
        )
        safe_name = slugify_list_name(new_list_name)

        if not safe_name:
            st.info("Enter a list name to create a new CSV in recipient_lists.")
            return RECIPIENTS_PATH, False

        target_path = LISTS_DIR / f"{safe_name}.csv"
    else:
        target_path = selected_option

    st.caption(f"Selected output: {target_path.relative_to(APP_DIR)}")
    return target_path, True


def clear_import_session_state() -> None:
    """Clear import preview state after changing or deleting a destination file."""
    for key in [
        "stats",
        "preview_dataframe",
        "file_results",
        "failed_files",
        "updated_dataframe",
        "target_path",
        "selected_target_path",
    ]:
        st.session_state.pop(key, None)


def show_delete_list_controls() -> None:
    """Allow deleting custom recipient CSV files created by the app."""
    custom_files = sorted(LISTS_DIR.glob("*.csv")) if LISTS_DIR.exists() else []

    with st.expander("Manage recipient lists"):
        if not custom_files:
            st.caption("No custom recipient lists created yet.")
            return

        delete_path = st.selectbox(
            "Custom list to delete",
            custom_files,
            format_func=lambda csv_path: csv_path.name,
            key="delete_list_path",
        )
        confirm_delete = st.checkbox(
            f"Yes, delete {delete_path.name}",
            key="confirm_delete_list",
        )

        if st.button(
            "Delete selected list",
            disabled=not confirm_delete,
            type="secondary",
        ):
            try:
                delete_path.unlink()
                LOGGER.info("Deleted recipient list %s", delete_path)
                clear_import_session_state()
                st.success(f"Deleted {delete_path.name}")
                st.rerun()
            except Exception as error:
                LOGGER.exception("Failed to delete recipient list %s", delete_path)
                st.error(f"Could not delete {delete_path.name}: {error}")


def run_app() -> None:
    """Render the Streamlit interface."""
    st.set_page_config(page_title="Lead Email Extractor", layout="wide")
    st.title("Lead Email Extractor")
    st.caption("Extract and clean email addresses locally. This app does not send emails.")

    tesseract_ready = configure_tesseract()
    if not tesseract_ready:
        st.warning(
            "Image OCR is not ready because Tesseract OCR is not installed or is not on PATH. "
            "CSV, Excel, TXT, and PDF uploads will still work. Install Tesseract OCR and restart "
            "the app to process PNG, JPG, JPEG, and WEBP files."
        )

    target_path, target_ready = choose_output_file()
    show_delete_list_controls()
    if target_ready and st.session_state.get("selected_target_path") != str(target_path):
        clear_import_session_state()
        st.session_state["selected_target_path"] = str(target_path)

    uploaded_files = st.file_uploader(
        "Upload lead files",
        type=ALLOWED_EXTENSIONS,
        accept_multiple_files=True,
    )

    process_clicked = st.button(
        "Extract emails",
        type="primary",
        disabled=not uploaded_files or not target_ready,
    )

    if process_clicked and uploaded_files and target_ready:
        LOGGER.info(
            "Import started | target=%s | files=%s | names=%s",
            target_path,
            len(uploaded_files),
            ", ".join(uploaded_file.name for uploaded_file in uploaded_files),
        )

        with st.spinner("Extracting emails..."):
            existing_dataframe = load_existing_recipients(target_path)
            processed = process_uploaded_files(uploaded_files)
            updated_dataframe, preview_dataframe, merge_stats = merge_with_master(
                existing_dataframe,
                processed["email_counts"],
                processed["email_sources"],
            )
            save_recipients(updated_dataframe, target_path)

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
        st.session_state["target_path"] = str(target_path)

        LOGGER.info(
            "Import complete | target=%s | found=%s | new=%s | duplicates=%s | invalid=%s",
            target_path,
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
        current_target_path = Path(st.session_state["target_path"])

        left_button, right_button = st.columns([1, 1])
        with left_button:
            st.download_button(
                f"Download updated {current_target_path.name}",
                data=csv_data,
                file_name=current_target_path.name,
                mime="text/csv",
            )

        with right_button:
            if st.button(f"Export {current_target_path.name} locally"):
                save_recipients(
                    st.session_state["updated_dataframe"],
                    current_target_path,
                )
                st.success(f"Saved to {current_target_path}")

    elif target_ready and target_path.exists() and target_path.stat().st_size > 0:
        existing_dataframe = load_existing_recipients(target_path)
        st.subheader(f"Current {target_path.name}")
        st.dataframe(existing_dataframe, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    run_app()
