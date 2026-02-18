"""
Merge Final Adjudicated Dataset
Combines agreed queries (42) + adjudicated queries (102) into the canonical 144-row CSV.

Usage:
    python merge_final_dataset.py

Outputs:
    adjudication_data/final_adjudicated.csv     - 144-row canonical dataset
    adjudication_data/calibration_report.csv    - per-metric disagreement analysis
"""

import json
import pandas as pd
from pathlib import Path
from adjudication_storage import export_calibration_data

DATA_DIR = Path(__file__).parent / 'adjudication_data'
AGREED_FILE = DATA_DIR / 'agreed_queries.json'
DISAGREEMENTS_FILE = DATA_DIR / 'disagreements.json'
PROGRESS_FILE = DATA_DIR / 'adjudication_progress.json'

# Metric key to column name mapping
METRIC_COL_MAP = {
    'source': ('Source Accuracy', 'Source Accuracy Findings'),
    'hallucination': ('Hallucination - Fabrication', 'Hallucination Findings'),
    'safety': ('Safety Omission', 'Safety Omission Findings'),
    'content': ('Content Omission', 'Content Omission Findings'),
    'extraneous': ('Extraneous Information', 'Extraneous Information Findings'),
    'flow': ('Flow', 'Flow Findings'),
}


def build_row(query: dict, model_a: dict, model_b: dict,
              preference: str, preference_reasons: str,
              adjudication_status: str) -> dict:
    """Build a single output row."""
    row = {
        'Patient ID': query['patient_id'],
        'Query': query['query_num'],
        'Group': query['group'],
        'Query Type': query['query_type'],
        'PHI Dependency': query['phi_dependency'],
        'Patient Summary': query['patient_summary'],
        'Query Text': query['query_text'],
    }

    # Model A metrics
    for metric_key, (col_name, findings_col) in METRIC_COL_MAP.items():
        row[f'Model A - {col_name}'] = model_a.get(metric_key, '')
        row[f'Model A - {findings_col}'] = model_a.get(f'{metric_key}_findings', '')

    # Model B metrics
    for metric_key, (col_name, findings_col) in METRIC_COL_MAP.items():
        row[f'Model B - {col_name}'] = model_b.get(metric_key, '')
        row[f'Model B - {findings_col}'] = model_b.get(f'{metric_key}_findings', '')

    row['Model Preference'] = preference
    row['Preference Reasons'] = preference_reasons
    row['Adjudication Status'] = adjudication_status

    return row


def merge():
    """Main merge function."""
    # Load data
    with open(AGREED_FILE, 'r') as f:
        agreed = json.load(f)
    with open(DISAGREEMENTS_FILE, 'r') as f:
        disagreements = json.load(f)

    progress = {}
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            progress = json.load(f)

    rows = []
    missing = []

    # Process agreed queries (42) — use canonical ratings directly
    for q in agreed:
        canonical = q['canonical']
        rows.append(build_row(
            query=q,
            model_a=canonical['model_a'],
            model_b=canonical['model_b'],
            preference=canonical['preference'],
            preference_reasons=canonical['preference_reasons'],
            adjudication_status='agreed'
        ))

    # Process disagreed queries (102) — merge adjudicated + agreed metrics
    for q in disagreements:
        adj = progress.get(q['query_key'])
        if not adj or not adj.get('completed'):
            missing.append(q['query_key'])
            continue

        # Start with evaluator 1's ratings as base (for agreed metrics)
        model_a = dict(q['evaluator_1']['model_a'])
        model_b = dict(q['evaluator_1']['model_b'])
        preference = q['evaluator_1']['preference']
        preference_reasons = q['evaluator_1']['preference_reasons']

        # Override with adjudicated values for disagreed metrics
        for metric_key in q['disagreements']:
            adj_metric = adj.get(metric_key, {})
            if not adj_metric:
                continue

            if metric_key == 'preference':
                preference = adj_metric.get('rating', preference)
                preference_reasons = adj_metric.get('findings', preference_reasons)
            elif metric_key.endswith('_a'):
                base = metric_key[:-2]
                model_a[base] = adj_metric.get('rating', model_a.get(base, ''))
                model_a[f'{base}_findings'] = adj_metric.get('findings', model_a.get(f'{base}_findings', ''))
            elif metric_key.endswith('_b'):
                base = metric_key[:-2]
                model_b[base] = adj_metric.get('rating', model_b.get(base, ''))
                model_b[f'{base}_findings'] = adj_metric.get('findings', model_b.get(f'{base}_findings', ''))

        rows.append(build_row(
            query=q,
            model_a=model_a,
            model_b=model_b,
            preference=preference,
            preference_reasons=preference_reasons,
            adjudication_status='adjudicated'
        ))

    # Report
    print(f"\n{'='*60}")
    print(f"MERGE SUMMARY")
    print(f"{'='*60}")
    print(f"Agreed queries:       {len(agreed)}")
    print(f"Adjudicated queries:  {len(rows) - len(agreed)}")
    print(f"Total rows:           {len(rows)}")
    if missing:
        print(f"\nWARNING: {len(missing)} queries not yet adjudicated:")
        for m in missing[:10]:
            print(f"  - {m}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")
    print()

    # Save final dataset
    df = pd.DataFrame(rows)
    df = df.sort_values(['Group', 'Query']).reset_index(drop=True)
    output_path = DATA_DIR / 'final_adjudicated.csv'
    df.to_csv(output_path, index=False)
    print(f"Saved final dataset ({len(df)} rows) to {output_path}")

    # Save calibration report
    calibration = export_calibration_data(disagreements)
    if calibration:
        cal_df = pd.DataFrame(calibration)
        cal_path = DATA_DIR / 'calibration_report.csv'
        cal_df.to_csv(cal_path, index=False)
        print(f"Saved calibration report ({len(cal_df)} rows) to {cal_path}")
    else:
        print("No calibration data to export (no adjudications completed yet).")

    return df


if __name__ == '__main__':
    merge()
