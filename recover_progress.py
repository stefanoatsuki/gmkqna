"""
Recovery Script: Rebuild evaluation progress from Google Sheets

This script reads submitted evaluations from Google Sheets and rebuilds
the local progress tracking file (evaluations.json).

Usage:
1. Open your Google Sheet with submitted evaluations
2. File > Download > Comma-separated values (.csv)
3. Save it as 'submissions_export.csv' in this folder
4. Run: python recover_progress.py
"""

import pandas as pd
from pathlib import Path
from evaluation_storage import rebuild_progress_from_submissions
import sys

# Path to exported CSV from Google Sheets
CSV_PATH = Path("submissions_export.csv")

if not CSV_PATH.exists():
    print(f"❌ Error: {CSV_PATH} not found!")
    print("\n📋 Instructions:")
    print("1. Open your Google Sheet with submitted evaluations")
    print("2. Go to: File > Download > Comma-separated values (.csv)")
    print("3. Save the file as 'submissions_export.csv' in this folder:")
    print(f"   {Path.cwd()}")
    print("4. Run this script again: python recover_progress.py")
    sys.exit(1)

# Read the CSV
print(f"📖 Reading {CSV_PATH}...")
df = pd.read_csv(CSV_PATH)

# Find the columns we need
# Column A: Patient ID
# Column B: Query  
# Column AX (index 50): Evaluator #
patient_col = None
query_col = None
evaluator_col = None

# Try to find columns by name
for col in df.columns:
    col_lower = str(col).lower()
    if 'patient' in col_lower and 'id' in col_lower:
        patient_col = col
    elif col_lower == 'query' or col_lower.startswith('query'):
        query_col = col
    elif 'evaluator' in col_lower:
        evaluator_col = col

# Fallback: use column indices (A=0, B=1, AX=50)
if not patient_col:
    patient_col = df.columns[0] if len(df.columns) > 0 else None
if not query_col:
    query_col = df.columns[1] if len(df.columns) > 1 else None
if not evaluator_col:
    evaluator_col = df.columns[50] if len(df.columns) > 50 else None

print(f"   Patient ID column: {patient_col}")
print(f"   Query column: {query_col}")
print(f"   Evaluator column: {evaluator_col}")

# Extract submissions
submissions = []
for idx, row in df.iterrows():
    try:
        patient_id = str(row[patient_col]).strip() if patient_col else ""
        query_num = str(row[query_col]).strip() if query_col else ""
        evaluator = str(row[evaluator_col]).strip() if evaluator_col else ""
        
        # Skip empty rows or template rows
        if (patient_id and patient_id != 'nan' and 
            query_num and query_num != 'nan' and 
            evaluator and evaluator != 'nan' and 
            evaluator not in ['', 'Evaluator #']):  # Skip header
            
            submissions.append({
                'evaluator': evaluator,
                'patientId': patient_id,
                'queryNum': query_num
            })
    except Exception as e:
        continue  # Skip problematic rows

if submissions:
    print(f"\n✅ Found {len(submissions)} submitted evaluations")
    print(f"   Rebuilding progress tracking...")
    
    count = rebuild_progress_from_submissions(submissions)
    print(f"\n🎉 Successfully recovered progress for {count} submissions!")
    print(f"   Progress tracking rebuilt in evaluations.json")
    print(f"\n💡 Next steps:")
    print(f"   1. Reboot your Streamlit app")
    print(f"   2. Evaluators will see their completed queries marked as done")
else:
    print("\n❌ No valid submissions found in CSV")
    print("\nPossible issues:")
    print("  - CSV might be the template (no submitted data)")
    print("  - Column names don't match expected format")
    print("  - Evaluator column might be empty")
    print("\nPlease check:")
    print("  1. Did you export the Google Sheet with actual submissions?")
    print("  2. Are there rows with 'Model Preference' filled in?")
    print("  3. Is the Evaluator column (column AX) populated?")

