# Email Automation System - Knowledge Transfer (KT)

**Date:** May 25, 2026  
**Project:** EMAILSAUTOMATION  
**Status:** Lead Email Extractor (Operational), Campaign Runner (Framework Ready)

---

## 📋 Executive Summary!!!

Your automation system is a **two-component email marketing platform**:

1. **Lead Email Extractor** - A sophisticated Streamlit-based tool for extracting email addresses from multiple file formats (CSV, Excel, PDF, images with OCR)
2. **Email Campaign Runner** - Infrastructure ready for bulk email campaign distribution (framework in place, awaiting implementation)

The system is designed for **lead generation and email campaign automation** with a focus on data quality and recipient management.

---

## 🏗️ System Architecture

```
EMAILSAUTOMATION/
├── lead-email-extractor/          ← EMAIL EXTRACTION MODULE
│   ├── app.py                     (Main Streamlit UI + Email extraction logic)
│   ├── requirements.txt           (Dependencies)
│   ├── recipients.csv             (Master recipient database)
│   └── recipient_lists/           (Custom segmented lists)
│
├── run_campaign.py                ← CAMPAIGN RUNNER (Framework ready)
├── config.yaml                    ← Configuration (Currently empty)
├── template.html                  ← Email template (Currently empty)
├── subjects.csv                   ← Email subjects (Currently empty)
├── recipients.csv                 ← Master recipients list
└── campaign.db                    ← Campaign database
```

---

## 🔍 COMPONENT 1: LEAD EMAIL EXTRACTOR (app.py)

### Purpose
Intelligently extract email addresses from diverse file sources and maintain a clean recipient database.

### Key Features

#### 1. **Multi-Format File Support**
- ✅ CSV files
- ✅ Excel workbooks (.xlsx) - reads all sheets
- ✅ Plain text (.txt)
- ✅ PDF documents - extracts from all pages
- ✅ Images (.png, .jpg, .jpeg, .webp) - **OCR-enabled with Tesseract**

#### 2. **Advanced Email Extraction Engine**
**Regex-Based Extraction:**
- `EMAIL_REGEX`: Strict RFC-compliant email matching
- `EMAIL_TOKEN_REGEX`: Catches malformed email attempts
- `VALID_EMAIL_REGEX`: Final validation using comprehensive pattern

**Cleaning & Validation:**
```python
clean_email(raw_email):
  - Trim whitespace
  - Convert to lowercase
  - Remove special characters: <>()[]{}
  - Strip trailing punctuation
  - Validate against VALID_EMAIL_REGEX
```

#### 3. **OCR Processing for Images**
**Intelligent Image Pre-processing:**
- `crop_screenshot_header()` - Removes mobile UI toolbars
- `remove_table_lines()` - Eliminates table borders that confuse OCR
- Creates 3 variants:
  - No lines version
  - Cropped + no lines version
  - Grayscale version
- Runs Tesseract on all variants and combines results

**OCR Cleanup Filters:**
- Removes suspicious OCR fragments (short digits + public domains)
- Detects and removes probable OCR truncations using heuristics
- Repairs split emails where OCR inserted spaces: `abc @gmail.com` → `abc@gmail.com`
- Fixes joined domains: `emailcom newemailnet` → `email.com newemailnet`

#### 4. **Duplicate Detection & Deduplication**
```python
get_existing_email_set(dataframe):
  - Loads all emails from selected recipient CSV
  - Creates fast lookup set
  - Prevents duplicate additions
  
remove_probable_ocr_truncations(emails):
  - Compares each email against others
  - If shorter email is suffix of longer email
  - AND local part is all digits OR small prefix difference
  - → Removes shorter email as truncation artifact
```

#### 5. **Recipient List Management**
**Default Master List:** `recipients.csv` (always present)
**Custom Lists:** `recipient_lists/*.csv` (user-created segmentation)

**List Creation Flow:**
1. User enters list name: "College ABC"
2. `slugify_list_name()` converts to safe filename: "college_abc"
3. Created at: `recipient_lists/college_abc.csv`

**CSV Schema:**
```
email              | name_guess      | source_files    | status   | created_at
abc@gmail.com      | John Doe        | leads.csv       | pending  | 2026-05-25T10:00:00
jane@company.com   | Jane Smith      | linkedin.pdf    | sent     | 2026-05-25T10:15:00
```

#### 6. **Streamlit UI Workflow**

**Step 1: Select Recipient List**
```
┌─────────────────────────────────┐
│ Choose Target                   │
├─────────────────────────────────┤
│ ⚪ recipients.csv (Master)      │
│ ⚪ Create a new recipient list  │
│ ⚪ college_abc.csv              │
│ ⚪ hyderabad.csv                │
└─────────────────────────────────┘
```

**Step 2: Upload Files**
- Support for batch uploads (multiple files)
- Drag & drop interface

**Step 3: Extract & Process**
- Processes each file independently
- Combines results
- Deduplicates against existing list
- Shows real-time extraction stats

**Step 4: Preview & Export**
- Interactive preview of extracted emails
- File-by-file processing details
- Error reporting
- Download updated CSV or save locally

### Performance Metrics & Tracking

**Logging System:**
- Location: `logs/import.log`
- Records:
  ```
  2026-05-25 10:00:00 | INFO | Processed leads.pdf | extracted=45 | unique=42 | invalid=3
  2026-05-25 10:01:00 | INFO | Import complete | target=college_abc.csv | found=150 | new=42 | duplicates=8 | invalid=3
  ```

**Session State Tracking:**
```python
st.session_state stores:
  - stats: {total_files, emails_found, new_emails, duplicates, invalid}
  - preview_dataframe: Newly extracted emails
  - file_results: Per-file extraction metrics
  - failed_files: Files with errors
  - updated_dataframe: Final merged dataset
```

---

## 🚀 COMPONENT 2: EMAIL CAMPAIGN RUNNER (run_campaign.py)

### Current Status
**Framework in place but NOT YET IMPLEMENTED** - Waiting for implementation

### Expected Architecture
```python
# Pseudo-structure (to be implemented)
run_campaign.py should:
1. Load configuration from config.yaml
   - SMTP server details
   - Email credentials
   - Rate limiting
   - Retry policy
   
2. Read recipients.csv or targeted list
   
3. Load email template.html with variable substitution
   - {{name}}, {{email}}, {{custom_field}}, etc.
   
4. Read email subjects from subjects.csv
   - Optional A/B testing variants
   
5. Execute campaign:
   - Batch email sending
   - Error handling & retry logic
   - Campaign tracking in campaign.db
   - Status updates (pending → sent → failed)
   
6. Generate campaign reports
```

### Dependency Files
- `config.yaml` - ❌ Empty (needs SMTP config)
- `template.html` - ❌ Empty (needs HTML template with variables)
- `subjects.csv` - ❌ Empty (needs subject lines)
- `campaign.db` - ✅ Created (SQLite for tracking)

---

## 📊 Data Flow Diagram

```
INPUT FILES                 EMAIL EXTRACTION              OUTPUT
│                          │                              │
├─ CSV files ─────┐       │  ┌─────────────────────┐     │
├─ Excel files ───┤       ├─→│ Regex Extraction    │     │
├─ PDF files ─────┼─TEXT─→│  │ + Cleaning          │────→├─ Deduplicated
├─ Images +OCR ───┤       │  │ + Validation        │     │  emails
└─ Text files ────┘       │  └─────────────────────┘     │
                          │          ↓                    │
                          │  Duplicate Check              │
                          │  Against CSV                  │
                          │                              │
                          │  ┌─────────────────────┐     │
                          └─→│ Merge & Save        │────→└─ Updated
                             │ to recipients.csv   │     CSV file
                             └─────────────────────┘
```

---

## 🔧 Technical Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| UI Framework | **Streamlit** | Web interface for file upload & management |
| Data Processing | **Pandas** | CSV/Excel reading & dataframe operations |
| OCR Engine | **Tesseract + pytesseract** | Text extraction from images |
| PDF Parsing | **pypdf** | Extract text from PDF files |
| Image Processing | **Pillow (PIL)** | Image manipulation & preprocessing |
| Numerical Computing | **NumPy** | Array operations for image pixel manipulation |
| Spreadsheets | **openpyxl** | Excel file support in Pandas |
| Logging | **Python logging** | Audit trail to `logs/import.log` |

---

## 💡 How the Automation Works (Step-by-Step)

### Email Extraction Process

```
1. USER UPLOADS FILE (e.g., "leads.pdf")
   ↓
2. DETERMINE FILE TYPE
   - .pdf → read_pdf_text() → pypdf extraction
   - .png/.jpg → read_image_text() → Tesseract OCR
   - .csv → read_csv_text() → Pandas read_csv()
   - .xlsx → read_excel_text() → Pandas read_excel()
   - .txt → read_txt_text() → Simple file decode
   ↓
3. EXTRACT RAW TEXT
   - For PDFs: Extract from all pages
   - For images: Apply pre-processing (crop, denoise), run OCR variants
   - For structured files: Read all cells
   ↓
4. PREPARE TEXT FOR EMAIL EXTRACTION
   repair_split_email_line(line):
     - "abc @gmail.com" → "abc@gmail.com"
     - "abc @.com newabc @.com" → "abc.com newabcabc@.com"
     
   prepare_text_for_email_extraction(text):
     - Apply line repairs
     - Fix joined domains: "...com next email..." → "...com. next email..."
   ↓
5. EXTRACT EMAILS WITH REGEX
   EMAIL_REGEX.finditer(prepared_text):
     - Matches: valid@email.com
     - Non-matches: inv@, @invalid, etc.
   ↓
6. VALIDATE & CLEAN
   clean_email(raw_email):
     - Strip whitespace
     - Lowercase
     - Remove special chars
     - Validate with VALID_EMAIL_REGEX
     - Return cleaned email or None
   ↓
7. APPLY OCR-SPECIFIC FILTERS (if from image)
   is_suspicious_ocr_email(email):
     - Reject "123@gmail.com" (typical OCR artifact)
     - Reject emails with all-digit local parts < 4 chars
     
   remove_probable_ocr_truncations(emails):
     - Remove short emails that are tails of longer ones
     - Heuristic: if "abc@gmail.com" & "longabc@gmail.com" exist
       → Remove "abc@gmail.com" as truncation
   ↓
8. DEDUPLICATION
   existing_set = get_existing_email_set(current_csv)
   new_emails = [e for e in extracted if e not in existing_set]
   ↓
9. ADD METADATA & SAVE
   - email: abc@gmail.com
   - name_guess: guess_name_from_email("abc@gmail.com") → "Abc"
   - source_files: "leads.pdf"
   - status: "pending"
   - created_at: timestamp
   ↓
10. UPDATE recipients.csv
    - Append new rows
    - Keep existing rows
    - Save to disk
```

---

## 🎯 How to Make the System MORE POWERFUL

### ⭐ TIER 1: HIGH-IMPACT FEATURES (Recommended First)

#### 1. **Email Campaign Execution Engine**
**What:** Implement `run_campaign.py` to actually send emails
**Impact:** Turn lead collection into revenue generation
**Effort:** Medium (3-5 hours)
**Implementation:**
```python
# config.yaml needed:
smtp_server: smtp.gmail.com
smtp_port: 587
sender_email: your@email.com
sender_password: app_password
batch_size: 50
delay_between_emails: 2  # seconds
max_retries: 3

# Features:
- Load recipients from CSV
- Substitute variables in template.html
- Send via SMTP with error handling
- Track campaign status in campaign.db
- Generate delivery reports
```

#### 2. **Advanced Recipient Segmentation**
**What:** Filter/segment recipients before campaign
**Impact:** Higher engagement, relevance
**Effort:** Low (2-3 hours)
**Features:**
```python
- Filter by email domain (domain.csv reference)
- Filter by email validity score (domain reputation)
- Segment by source file
- Segment by geography/region (if available)
- Custom rules: exclude keywords in email address
```

#### 3. **Email Validation & Hygiene**
**What:** Verify emails before sending (prevent blacklisting)
**Impact:** Higher deliverability, protect sender reputation
**Effort:** Low (2-3 hours)
**Libraries:**
```python
# Use: py-email-validator or similar
- Verify valid SMTP domain
- Check common typos (gmial.com → gmail.com)
- Exclude disposable email services
- Score email reputation (if possible)
- Automatically flag/remove risky emails
```

---

### ⭐ TIER 2: MEDIUM-IMPACT FEATURES

#### 4. **A/B Testing Framework**
**What:** Test different subject lines and templates
**Impact:** Optimize open rates
**Effort:** Medium (4-6 hours)
**Features:**
```python
- Split recipients 50/50 (A vs B)
- Track open rates, click rates
- Automatically choose winner after N days
- Store results in campaign.db for analysis
- Generate A/B test reports
```

#### 5. **Batch Email Scheduling**
**What:** Schedule campaigns instead of send immediately
**Impact:** Control send time, avoid overload
**Effort:** Low-Medium (2-4 hours)
**Features:**
```python
- Schedule campaign for specific date/time
- Use APScheduler library
- Timezone support
- Queue management
- Campaign pause/resume
```

#### 6. **Email Open & Click Tracking**
**What:** Know when recipients open emails and click links
**Impact:** Understand engagement
**Effort:** Medium (4-5 hours)
**Implementation:**
```python
- Add tracking pixel to email (unique ID)
- Add URL parameters to links (utm_source, utm_campaign)
- Log opens/clicks to campaign.db
- Generate engagement reports
- Identify hot leads
```

---

### ⭐ TIER 3: ADVANCED FEATURES

#### 7. **Domain Reputation & Deliverability Dashboard**
**What:** Monitor sender reputation metrics
**Impact:** Prevent emails landing in spam
**Effort:** Medium-High (6-8 hours)
**Features:**
```python
- Check SPF, DKIM, DMARC records
- Monitor bounce rates
- Track complaint rates
- Integration with email service APIs (SendGrid, Mailgun)
- Visual dashboard with Plotly/Streamlit charts
```

#### 8. **Lead Scoring & Qualification**
**What:** Automatically score leads based on engagement
**Impact:** Prioritize high-value prospects
**Effort:** Medium-High (5-7 hours)
**Scoring Factors:**
```python
- Email domain type (business vs consumer)
- Engagement metrics (opens, clicks)
- Response patterns
- Time in list
- Source credibility
```

#### 9. **Intelligent Follow-up Sequences**
**What:** Auto-send follow-ups to non-responders
**Impact:** Higher conversion rates
**Effort:** Medium-High (6-8 hours)
**Features:**
```python
- Create email sequences (Day 1, Day 3, Day 7, etc.)
- Conditional logic: if opened → different email
- Auto-unsubscribe management
- Track sequence performance
- A/B test sequences
```

#### 10. **Data Enrichment Integration**
**What:** Enrich email addresses with additional data
**Impact:** Better personalization, insights
**Effort:** Medium-High (5-7 hours)
**APIs to integrate:**
```python
- Hunter.io - company data, verification
- RocketReach - professional profiles
- ClearBit - company & person enrichment
- EmailListVerify - bulk email verification
- LinkedIn - title, company (if available)
```

---

### ⭐ TIER 4: NICE-TO-HAVE FEATURES

#### 11. **Bulk Email Verification Service**
**What:** Validate all emails in list at once
**Effort:** Low (2-3 hours)
**Services:**
```python
- ZeroBounce API
- NeverBounce API
- Abstract API
```

#### 12. **HTML Email Template Builder**
**What:** Drag-and-drop email template creator
**Effort:** High (8-10 hours)
**Tech:** Use Stripo, MJML, or React-email

#### 13. **Analytics Dashboard**
**What:** Visualize campaign performance
**Effort:** Medium (4-5 hours)
**Tools:** Streamlit + Plotly
```python
- Emails sent/bounced/opened/clicked
- Top performing subjects
- Best send times
- Geographic breakdown
- Industry breakdown
```

#### 14. **Webhook Integration**
**What:** Receive events from email providers
**Effort:** Medium (4-5 hours)
**Features:**
- Track bounces in real-time
- Track complaints
- Update recipient status automatically

#### 15. **Unsubscribe Management**
**What:** Auto-handle unsubscribe requests
**Effort:** Low-Medium (2-4 hours)
**Features:**
```python
- Parse unsubscribe headers
- Maintain unsubscribe list
- Auto-exclude from future campaigns
- GDPR/CAN-SPAM compliance
```

---

## 🚀 IMPLEMENTATION ROADMAP

### Phase 1: MVP (1-2 weeks)
Priority: **Email Campaign Execution** → Single email send feature
```
✅ Lead extraction (DONE)
⬜ Configure config.yaml
⬜ Implement SMTP sending
⬜ Track sends in campaign.db
⬜ Basic error handling
```

### Phase 2: Stabilization (1 week)
```
⬜ Email validation & hygiene
⬜ Duplicate prevention
⬜ Recipient segmentation
⬜ Campaign scheduling
```

### Phase 3: Intelligence (2 weeks)
```
⬜ Open/click tracking
⬜ A/B testing
⬜ Lead scoring
⬜ Analytics dashboard
```

### Phase 4: Enterprise (Ongoing)
```
⬜ Data enrichment
⬜ Follow-up sequences
⬜ Domain reputation monitoring
⬜ Advanced automations
```

---

## 🐛 Known Issues & Considerations

### Current Limitations

| Issue | Severity | Workaround | Fix Effort |
|-------|----------|-----------|-----------|
| OCR accuracy on low-res images | Medium | Use high-quality screenshots | N/A (OCR library limit) |
| No email validation | High | Manually verify before sending | 2 hours |
| No campaign sending | Critical | Implement run_campaign.py | 4 hours |
| No duplicate prevention across lists | Medium | Implement cross-list dedup | 3 hours |
| No rate limiting | Medium | Add delay config | 1 hour |
| No bounce handling | High | Add bounce list | 3 hours |

---

## 📝 Code Quality Notes

### Strengths
✅ **Modular design** - Separate functions for each task
✅ **Comprehensive regex patterns** - Multiple layers of email validation
✅ **Robust error handling** - Per-file error isolation
✅ **Good logging** - Audit trail for debugging
✅ **Type hints** - Python typing annotations present
✅ **Docstrings** - Well-documented functions

### Areas for Improvement
⚠️ Could add unit tests
⚠️ Could add input validation for large files
⚠️ Could optimize memory for 100k+ emails
⚠️ Could add async file processing for speed

---

## 🔐 Security & Compliance

### Current Best Practices
✅ Email validation to prevent injection
✅ Input sanitization for file names
✅ Logging for audit trail

### Recommended Additions
- Add rate limiting (prevent abuse)
- Add encryption for stored credentials
- Add GDPR consent tracking
- Add email bounce/complaint handling
- Add unsubscribe list management
- Add spam filter score checking

---

## 📚 Key Functions Reference

### Email Extraction Functions
```python
extract_emails_from_text(text, apply_ocr_cleanup=False)
  → Returns: (valid_emails[], invalid_count)

clean_email(raw_email)
  → Returns: cleaned_email or None

guess_name_from_email(email)
  → Returns: "John Doe" from "john.doe@email.com"
```

### File Reading Functions
```python
read_csv_text(file_bytes)
read_excel_text(file_bytes)
read_pdf_text(file_bytes)
read_image_text(file_bytes)  # Requires Tesseract
read_txt_text(file_bytes)
```

### Recipient Management
```python
load_existing_recipients(csv_path)
  → Returns: DataFrame with all existing recipients

save_recipients(dataframe, csv_path)
  → Saves to CSV, logs action

get_custom_list_path(list_name)
  → Returns: Path to list CSV
```

---

## 🎓 Quick Start for Developers

### Setup
```bash
cd lead-email-extractor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
winget install UB-Mannheim.TesseractOCR  # For OCR
streamlit run app.py
```

### Running Campaign (When Implemented)
```bash
python run_campaign.py --config config.yaml --list recipients.csv
```

---

## 📞 Support & Troubleshooting

### Tesseract OCR Not Found
```
Error: Tesseract OCR engine was not found
Solution: 
1. Download from: https://ub-mannheim.github.io/Tesseract_Dokumentation/
2. Or run: winget install UB-Mannheim.TesseractOCR
3. Restart Streamlit app
```

### Email Extraction Too Permissive
→ Reduce scope of EMAIL_REGEX pattern for stricter matching

### Performance Issues with Large Files
→ Consider chunking file reading, async processing

---

## 🎯 Next Steps (Action Items)

1. **Implement run_campaign.py** - Most critical missing piece
2. **Create config.yaml template** - SMTP configuration
3. **Design template.html** - Email template with variable placeholders
4. **Add email validation service** - Prevent bad emails
5. **Create campaign database schema** - Track sends/opens/clicks
6. **Build analytics dashboard** - Visualize campaign performance

---

**Document Version:** 1.0  
**Last Updated:** May 25, 2026  
**Next Review:** Upon completion of Phase 1 implementation
