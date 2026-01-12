# Medical Evaluation Platform

High-end "Apple-caliber" Medical Evaluation Platform for comparing Model A vs Model B responses.

## Features

- **Three-Column Layout**: Patient Case File (sticky), Model A response, Model B response
- **Apple Midnight Aesthetic**: Beautiful dark theme with #1C1C1E background
- **7-Metric Evaluation Suite**: Comprehensive evaluation form with feedback fields
- **Google Sheets Integration**: Automatic sync of evaluation data
- **Evaluator Management**: 6 evaluators, 12 unique patients each
- **Progress Tracking**: Real-time dashboard showing completion status

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Prepare Data Files**:
   - Place your CSV file: `GMK Q&A Evaluation - All Questions - gmk_qa_eval (1).csv` in the project root
   - Create a folder `docx_responses/` containing DOCX files with Model A and Model B responses
   - DOCX files should follow naming patterns like:
     - `{PatientID}_{QueryNum}_A.docx` and `{PatientID}_{QueryNum}_B.docx`
     - Or `*ModelA*.docx` and `*ModelB*.docx`

3. **Configure Google Sheets URL**:
   - Open `app.py`
   - Replace `[PASTE_YOUR_URL_HERE]` with your Google Apps Script web app URL
   - Ensure your Google Apps Script has a `doPost` function that accepts the JSON payload

4. **Run the Application**:
   ```bash
   streamlit run app.py
   ```

## CSV File Structure

The CSV file should contain the following columns (or similar):
- Patient ID
- Query # (or Query Number)
- Full Query
- Patient Summary (Column F)

## DOCX File Organization

Place DOCX files in the `docx_responses/` folder. The parser supports multiple naming conventions:
- `{PatientID}_{QueryNum}_A.docx` / `{PatientID}_{QueryNum}_B.docx`
- `*ModelA*.docx` / `*ModelB*.docx`
- Files containing patient ID and query number with A/B indicators

## Google Sheets Payload Structure

The app sends the following JSON payload to Google Sheets:
- `patientId`, `queryNum`, `fullQuery`, `patientSummary`, `evaluator`
- `a_source`, `a_source_f`, `a_hallucination`, `a_hall_f`, `a_safety`, `a_safety_f`, `a_completeness`, `a_comp_f`, `a_extraneous`, `a_extra_f`, `a_flow`, `a_flow_f`
- `b_source`, `b_source_f`, `b_hallucination`, `b_hall_f`, `b_safety`, `b_safety_f`, `b_completeness`, `b_comp_f`, `b_extraneous`, `b_extra_f`, `b_flow`, `b_flow_f`
- `preference`, `pref_reasons`

## Usage

1. Select an evaluator from the sidebar
2. Review the Patient Case File (left column)
3. Compare Model A and Model B responses (middle and right columns)
4. Complete the 7-metric evaluation form
5. Provide preference reasons (required)
6. Click "Submit & Next" to save and move to the next evaluation

## File Structure

```
gmk/
├── app.py                          # Main Streamlit application
├── docx_parser.py                  # DOCX parsing utility
├── data_loader.py                  # CSV and assignment management
├── style.css                       # Apple Midnight aesthetic styles
├── assignments.json                # Evaluator assignments (auto-generated)
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── GMK Q&A Evaluation - All Questions - gmk_qa_eval (1).csv  # Metadata CSV
└── docx_responses/                 # Folder containing DOCX files
    ├── PatientID_QueryNum_A.docx
    ├── PatientID_QueryNum_B.docx
    └── ...
```

## Notes

- Evaluator assignments are automatically created on first run (6 evaluators × 12 patients each)
- Progress is tracked per evaluator and saved in session state
- All evaluations are submitted to Google Sheets via POST request
- The app validates that "Preference Reasons" is filled before submission

