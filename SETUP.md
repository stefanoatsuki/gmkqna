# Quick Setup Guide

## Prerequisites
- Python 3.8+
- pip

## Installation Steps

1. **Install dependencies**:
   ```bash
   cd /Users/stefanoleitner/CursorProjects/gmk
   pip install -r requirements.txt
   ```

2. **Prepare your data files**:
   - Place your CSV file: `GMK Q&A Evaluation - All Questions - gmk_qa_eval (1).csv` in the `/Users/stefanoleitner/CursorProjects/gmk/` directory
   - Add DOCX files to the `docx_responses/` folder
   - DOCX files should be named with patterns like:
     - `{PatientID}_{QueryNum}_A.docx` (Model A)
     - `{PatientID}_{QueryNum}_B.docx` (Model B)

3. **Configure Google Sheets** (if needed):
   - The app is pre-configured with a Google Sheets URL from `streamlit_text.py`
   - To change it, edit `app.py` and update the `GOOGLE_SHEETS_URL` variable
   - Ensure your Google Apps Script has a `doPost` function that accepts JSON payloads

4. **Run the application**:
   ```bash
   streamlit run app.py
   ```

5. **First-time setup**:
   - The app will automatically create evaluator assignments on first run
   - 6 evaluators × 12 unique patients each
   - Assignments are saved to `assignments.json`

## CSV File Requirements

Your CSV should have columns for:
- Patient ID
- Query Number/Query #
- Full Query text
- Patient Summary (typically Column F)

The app will auto-detect these columns by name patterns.

## Troubleshooting

- **CSV not found**: Ensure the CSV file is named exactly: `GMK Q&A Evaluation - All Questions - gmk_qa_eval (1).csv`
- **DOCX files not loading**: Check that files are in `docx_responses/` folder and follow naming conventions
- **Google Sheets error**: Verify the URL in `app.py` and ensure your Apps Script has a `doPost` function
- **Import errors**: Make sure all dependencies are installed: `pip install -r requirements.txt`

