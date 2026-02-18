"""
Prepare Adjudication Dataset
Reads the raw 288-row evaluation CSV, identifies disagreements between evaluator pairs,
and outputs structured JSON files for the adjudication app.

Usage:
    python prepare_adjudication.py [path_to_csv]

Outputs:
    adjudication_data/disagreements.json  - 102 queries needing adjudication
    adjudication_data/agreed_queries.json - 42 queries with full agreement
"""

import pandas as pd
import json
import sys
from pathlib import Path


# Column mapping for the CSV structure
# Model A metrics (columns 9-25)
METRIC_COLS_A = {
    'source': ('Source Accuracy', 'Source Accuracy Findings'),
    'hallucination': ('Hallucination - Fabrication', 'Hallucination findings'),
    'safety': ('Safety Omission', 'Safety Omission Findings'),
    'content': ('Content Omission', 'Content Omission Findings'),
    'extraneous': ('Extraneous Information', 'Extraneous Information Findings'),
    'flow': ('Flow', 'Flow Findings'),
}

# Model B metrics (columns 29-45) - pandas appends .1 for duplicate names
METRIC_COLS_B = {
    'source': ('Source Accuracy.1', 'Source Accuracy Findings.1'),
    'hallucination': ('Hallucination - Fabrication.1', 'Hallucination findings.1'),
    'safety': ('Safety Omission.1', 'Safety Omission Findings.1'),
    'content': ('Content Omission.1', 'Content Omission Findings.1'),
    'extraneous': ('Extraneous Information.1', 'Extraneous Information Findings.1'),
    'flow': ('Flow.1', 'Flow Findings.1'),
}

# Evaluator pair assignments by group
EVALUATOR_PAIRS = {
    'A': ('Evaluator 1', 'Evaluator 2'),
    'B': ('Evaluator 3', 'Evaluator 4'),
    'C': ('Evaluator 5', 'Evaluator 6'),
}


def clean_str(val):
    """Clean a value to a stripped string, handling NaN."""
    if pd.isna(val):
        return ''
    return str(val).strip()


def extract_evaluator_ratings(row, metric_cols):
    """Extract all metric ratings and findings from a row for one model."""
    ratings = {}
    for metric_key, (rating_col, findings_col) in metric_cols.items():
        ratings[metric_key] = clean_str(row.get(rating_col, ''))
        ratings[f'{metric_key}_findings'] = clean_str(row.get(findings_col, ''))
    return ratings


def compare_ratings(e1_ratings, e2_ratings):
    """Compare two sets of ratings and return list of disagreed metric keys."""
    disagreements = []
    for key in e1_ratings:
        if key.endswith('_findings'):
            continue  # Only compare the Pass/Fail ratings, not findings text
        if e1_ratings[key] != e2_ratings[key]:
            disagreements.append(key)
    return disagreements


def prepare_adjudication_data(csv_path: str):
    """Main function to prepare adjudication dataset."""
    df = pd.read_csv(csv_path)

    print(f"Loaded {len(df)} rows from CSV")
    print(f"Columns: {list(df.columns)}")
    print(f"Groups: {df['Group'].unique()}")
    print(f"Evaluators: {df['Evaluator'].unique()}")
    print()

    disagreements = []
    agreed = []

    for group in ['A', 'B', 'C']:
        e1_name, e2_name = EVALUATOR_PAIRS[group]
        group_df = df[df['Group'] == group]

        e1_df = group_df[group_df['Evaluator'] == e1_name].set_index(['Patient ID', 'Query']).sort_index()
        e2_df = group_df[group_df['Evaluator'] == e2_name].set_index(['Patient ID', 'Query']).sort_index()

        common_queries = e1_df.index.intersection(e2_df.index)
        print(f"Group {group}: {e1_name} vs {e2_name} — {len(common_queries)} common queries")

        for query_idx in common_queries:
            patient_id, query_num = query_idx
            e1_row = e1_df.loc[query_idx]
            e2_row = e2_df.loc[query_idx]

            # Extract ratings for both models
            e1_model_a = extract_evaluator_ratings(e1_row, METRIC_COLS_A)
            e1_model_b = extract_evaluator_ratings(e1_row, METRIC_COLS_B)
            e2_model_a = extract_evaluator_ratings(e2_row, METRIC_COLS_A)
            e2_model_b = extract_evaluator_ratings(e2_row, METRIC_COLS_B)

            # Extract preference
            e1_preference = clean_str(e1_row.get('Model Preference', ''))
            e1_pref_reasons = clean_str(e1_row.get('Preference Reasons', ''))
            e2_preference = clean_str(e2_row.get('Model Preference', ''))
            e2_pref_reasons = clean_str(e2_row.get('Preference Reasons', ''))

            # Find disagreements
            model_a_disagreements = [f'{k}_a' for k in compare_ratings(e1_model_a, e2_model_a)]
            model_b_disagreements = [f'{k}_b' for k in compare_ratings(e1_model_b, e2_model_b)]
            pref_disagreement = ['preference'] if e1_preference != e2_preference else []

            all_disagreements = model_a_disagreements + model_b_disagreements + pref_disagreement

            # Build the query record
            query_record = {
                'query_key': f'{patient_id}_{query_num}',
                'patient_id': str(patient_id),
                'query_num': int(query_num) if not pd.isna(query_num) else query_num,
                'group': group,
                'query_type': clean_str(e1_row.get('Query Type', '')),
                'phi_dependency': clean_str(e1_row.get('PHI Dependency', '')),
                'patient_summary': clean_str(e1_row.get('Patient Summary (Ground Truth)', '')),
                'query_text': clean_str(e1_row.get('Query.1', '')),
                'evaluator_1': {
                    'name': e1_name,
                    'model_a': e1_model_a,
                    'model_b': e1_model_b,
                    'preference': e1_preference,
                    'preference_reasons': e1_pref_reasons,
                },
                'evaluator_2': {
                    'name': e2_name,
                    'model_a': e2_model_a,
                    'model_b': e2_model_b,
                    'preference': e2_preference,
                    'preference_reasons': e2_pref_reasons,
                },
                'disagreements': all_disagreements,
                'n_disagreements': len(all_disagreements),
            }

            if all_disagreements:
                disagreements.append(query_record)
            else:
                # For agreed queries, store canonical ratings (use evaluator 1 since identical)
                query_record['canonical'] = {
                    'model_a': e1_model_a,
                    'model_b': e1_model_b,
                    'preference': e1_preference,
                    'preference_reasons': e1_pref_reasons,
                }
                agreed.append(query_record)

    # Sort disagreements by group, then query_num
    disagreements.sort(key=lambda x: (x['group'], x['query_num']))
    agreed.sort(key=lambda x: (x['group'], x['query_num']))

    return disagreements, agreed


def print_summary(disagreements, agreed):
    """Print summary statistics."""
    print(f"\n{'='*60}")
    print(f"ADJUDICATION DATASET SUMMARY")
    print(f"{'='*60}")
    print(f"Total queries: {len(disagreements) + len(agreed)}")
    print(f"Fully agreed (auto-finalized): {len(agreed)}")
    print(f"Need adjudication: {len(disagreements)}")
    print()

    # By group
    from collections import Counter
    group_counts = Counter(d['group'] for d in disagreements)
    print("Disagreements by group:")
    for g in ['A', 'B', 'C']:
        pair = EVALUATOR_PAIRS[g]
        print(f"  Group {g} ({pair[0]} vs {pair[1]}): {group_counts.get(g, 0)}")
    print()

    # By disagreement count
    n_counts = Counter(d['n_disagreements'] for d in disagreements)
    print("By number of disagreements:")
    for n in sorted(n_counts.keys()):
        print(f"  {n} metric(s): {n_counts[n]} queries")
    print()

    # By metric
    metric_counts = Counter()
    for d in disagreements:
        for m in d['disagreements']:
            metric_counts[m] += 1
    print("Most disagreed metrics:")
    for m, count in metric_counts.most_common():
        print(f"  {m:25s}: {count} ({count/len(disagreements)*100:.1f}% of disagreed queries)")


if __name__ == '__main__':
    # Default CSV path
    default_csv = '/Users/stefanoleitner/Downloads/UpToDate Q&A Evaluation - All Responses - stef_adjudicated_gmk_qa_eval.csv'
    csv_path = sys.argv[1] if len(sys.argv) > 1 else default_csv

    if not Path(csv_path).exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    # Prepare data
    disagreements, agreed = prepare_adjudication_data(csv_path)

    # Print summary
    print_summary(disagreements, agreed)

    # Save outputs
    output_dir = Path(__file__).parent / 'adjudication_data'
    output_dir.mkdir(exist_ok=True)

    with open(output_dir / 'disagreements.json', 'w') as f:
        json.dump(disagreements, f, indent=2, default=str)
    print(f"\nSaved {len(disagreements)} disagreements to {output_dir / 'disagreements.json'}")

    with open(output_dir / 'agreed_queries.json', 'w') as f:
        json.dump(agreed, f, indent=2, default=str)
    print(f"Saved {len(agreed)} agreed queries to {output_dir / 'agreed_queries.json'}")
