"""
Adjudication Storage - Tracks adjudication progress and stores results.
Mirrors the pattern from evaluation_storage.py but with adjudication-specific fields.
"""

import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime


DATA_DIR = Path(__file__).parent / 'adjudication_data'
PROGRESS_FILE = DATA_DIR / 'adjudication_progress.json'


def load_progress() -> Dict:
    """Load all adjudication progress from JSON file."""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading adjudication progress: {e}")
            return {}
    return {}


def save_progress(progress: Dict):
    """Save all adjudication progress to JSON file."""
    DATA_DIR.mkdir(exist_ok=True)
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress, f, indent=2)
    except Exception as e:
        print(f"Error saving adjudication progress: {e}")


def get_adjudication_status(query_key: str) -> Optional[Dict]:
    """Get adjudication status for a specific query."""
    progress = load_progress()
    return progress.get(query_key, None)


def save_adjudication(query_key: str, adjudication_data: Dict):
    """
    Save adjudication results for a specific query.

    adjudication_data should contain:
    - For each disagreed metric: {metric_key: {rating, findings, root_cause, root_cause_detail}}
    - For preference (if disagreed): {preference, preference_reasons, root_cause, root_cause_detail}
    - timestamp
    """
    progress = load_progress()
    progress[query_key] = {
        'completed': True,
        'timestamp': datetime.now().isoformat(),
        **adjudication_data
    }
    save_progress(progress)


def get_group_progress(group: str, disagreements: list) -> Dict:
    """
    Get adjudication progress for a group.

    Returns:
        {total: int, completed: int, remaining: int, percent: float}
    """
    progress = load_progress()
    group_queries = [d for d in disagreements if d['group'] == group]
    total = len(group_queries)
    completed = sum(1 for d in group_queries if progress.get(d['query_key'], {}).get('completed', False))
    return {
        'total': total,
        'completed': completed,
        'remaining': total - completed,
        'percent': (completed / total * 100) if total > 0 else 0
    }


def get_all_progress(disagreements: list) -> Dict:
    """Get overall adjudication progress across all groups."""
    progress = load_progress()
    total = len(disagreements)
    completed = sum(1 for d in disagreements if progress.get(d['query_key'], {}).get('completed', False))
    return {
        'total': total,
        'completed': completed,
        'remaining': total - completed,
        'percent': (completed / total * 100) if total > 0 else 0
    }


def rebuild_progress_from_sheets(submissions: list) -> int:
    """
    Rebuild local adjudication progress from Google Sheets data.
    Used for auto-recovery after Streamlit Cloud filesystem resets.

    Args:
        submissions: list of dicts from the Google Sheets GET endpoint,
                     each containing query_key and adjudication_data.

    Returns:
        Number of adjudications recovered.
    """
    progress = load_progress()
    count = 0

    for sub in submissions:
        qk = sub.get('query_key', '')
        adj_data = sub.get('adjudication_data', {})
        if not qk or not adj_data:
            continue

        # Only overwrite if not already present locally, or if Sheets has newer data
        if qk not in progress or not progress[qk].get('completed'):
            progress[qk] = {
                'completed': True,
                'timestamp': sub.get('timestamp', datetime.now().isoformat()),
                **adj_data
            }
            count += 1

    if count > 0:
        save_progress(progress)

    return count


def reset_progress():
    """Reset all adjudication progress (admin function)."""
    save_progress({})


def export_calibration_data(disagreements: list) -> list:
    """
    Export calibration data for all adjudicated queries.

    Returns list of dicts, one per disagreed metric-query pair:
    {query_key, metric, model, evaluator_1_rating, evaluator_2_rating,
     adjudicated_rating, root_cause, root_cause_detail}
    """
    progress = load_progress()
    calibration_rows = []

    for d in disagreements:
        qk = d['query_key']
        adj = progress.get(qk)
        if not adj or not adj.get('completed'):
            continue

        for metric_key in d['disagreements']:
            if metric_key == 'preference':
                model = 'comparison'
                e1_val = d['evaluator_1']['preference']
                e2_val = d['evaluator_2']['preference']
                adj_data = adj.get('preference', {})
            elif metric_key.endswith('_a'):
                model = 'A'
                base_metric = metric_key[:-2]
                e1_val = d['evaluator_1']['model_a'].get(base_metric, '')
                e2_val = d['evaluator_2']['model_a'].get(base_metric, '')
                adj_data = adj.get(metric_key, {})
            elif metric_key.endswith('_b'):
                model = 'B'
                base_metric = metric_key[:-2]
                e1_val = d['evaluator_1']['model_b'].get(base_metric, '')
                e2_val = d['evaluator_2']['model_b'].get(base_metric, '')
                adj_data = adj.get(metric_key, {})
            else:
                continue

            calibration_rows.append({
                'query_key': qk,
                'patient_id': d['patient_id'],
                'query_num': d['query_num'],
                'group': d['group'],
                'query_type': d['query_type'],
                'metric': metric_key,
                'model': model,
                'evaluator_1_name': d['evaluator_1']['name'],
                'evaluator_2_name': d['evaluator_2']['name'],
                'evaluator_1_rating': e1_val,
                'evaluator_2_rating': e2_val,
                'adjudicated_rating': adj_data.get('rating', ''),
                'root_cause': adj_data.get('root_cause', ''),
                'root_cause_detail': adj_data.get('root_cause_detail', ''),
            })

    return calibration_rows
