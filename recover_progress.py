"""
Recovery Script: Rebuild evaluation progress from Google Sheets

This script reads submitted evaluations from Google Sheets and rebuilds
the local progress tracking file (evaluations.json).

Usage:
1. Export your Google Sheet as CSV (File > Download > CSV)
2. Save it as 'submissions_export.csv' in this folder
3. Run: python recover_progress.py
"""

import pandas as pd
from pathlib import Path
from evaluation_storage import rebuild_progress_from_submissions

# Path to exported CSV from Google Sheets
CSV_PATH = Path("submissions_export.csv")

if not CSV_PATH.exists():
    print(f"❌ Error: {CSV_PATH} not found!")
    print("\nPlease:")
    print("1. Export your Google Sheet as CSV")
    print("2. Save it as 'submissions_export.csv' in this folder")
    print("3. Run this script again")
    exit(1)

# Read the CSV
df = pd.read_csv(CSV_PATH)

# Map CSV columns to submission format
# Adjust these column names to match your Google Sheet export
submissions = []
for _, row in df.iterrows():
    # Adjust column names based on your Google Sheet structure
    # Column AX should be "Evaluator #" or similar
    evaluator = str(row.get('Evaluator #', row.get('AX', '')))
    patient_id = str(row.get('Patient ID', row.get('A', '')))
    query_num = str(row.get('Query', row.get('B', '')))
    
    if evaluator and patient_id and query_num and evaluator != 'nan':
        submissions.append({
            'evaluator': evaluator,
            'patientId': patient_id,
            'queryNum': query_num
        })

if submissions:
    count = rebuild_progress_from_submissions(submissions)
    print(f"✅ Recovered progress for {count} submissions!")
    print(f"   Progress tracking rebuilt in evaluations.json")
else:
    print("❌ No valid submissions found in CSV")
    print("   Please check that your CSV has columns: Patient ID, Query, Evaluator #")

