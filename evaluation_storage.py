"""
Evaluation Storage - Tracks evaluation progress and stores results
"""

import json
from pathlib import Path
from typing import Dict, Optional


EVALUATIONS_FILE = Path(__file__).parent / "evaluations.json"


def load_evaluations() -> Dict:
    """Load all evaluations from JSON file."""
    if EVALUATIONS_FILE.exists():
        try:
            with open(EVALUATIONS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading evaluations: {e}")
            return {}
    return {}


def reset_all_evaluations():
    """Reset all evaluation progress (admin function)."""
    try:
        with open(EVALUATIONS_FILE, 'w') as f:
            json.dump({}, f)
        return True
    except Exception as e:
        print(f"Error resetting evaluations: {e}")
        return False


def save_evaluations(evaluations: Dict):
    """Save all evaluations to JSON file."""
    try:
        with open(EVALUATIONS_FILE, 'w') as f:
            json.dump(evaluations, f, indent=2)
    except Exception as e:
        print(f"Error saving evaluations: {e}")


def get_evaluation_status(evaluator: str, patient_id: str, query_num: str) -> Dict:
    """Get evaluation status for a specific query."""
    evaluations = load_evaluations()
    key = f"{evaluator}_{patient_id}_{query_num}"
    return evaluations.get(key, {
        'started': False,
        'model_a_graded': False,
        'model_b_graded': False,
        'comparison_done': False,
        'model_a_data': {},
        'model_b_data': {},
        'comparison_data': {}
    })


def update_evaluation_status(evaluator: str, patient_id: str, query_num: str, 
                            status_updates: Dict):
    """Update evaluation status for a specific query."""
    evaluations = load_evaluations()
    key = f"{evaluator}_{patient_id}_{query_num}"
    
    if key not in evaluations:
        evaluations[key] = {
            'started': False,
            'model_a_graded': False,
            'model_b_graded': False,
            'comparison_done': False,
            'model_a_data': {},
            'model_b_data': {},
            'comparison_data': {}
        }
    
    evaluations[key].update(status_updates)
    save_evaluations(evaluations)


def get_all_evaluator_queries(evaluator: str, assignments: list) -> list:
    """Get all queries for an evaluator with their status."""
    queries_with_status = []
    evaluations = load_evaluations()
    
    for assignment in assignments:
        patient_id = assignment['patient_id']
        query_num = assignment['query_num']
        key = f"{evaluator}_{patient_id}_{query_num}"
        
        status = evaluations.get(key, {
            'started': False,
            'model_a_graded': False,
            'model_b_graded': False,
            'comparison_done': False
        })
        
        queries_with_status.append({
            **assignment,
            'status': status
        })
    
    return queries_with_status


def rebuild_progress_from_submissions(submitted_data: list):
    """
    Rebuild evaluation progress from submitted data (e.g., from Google Sheets export).
    
    Args:
        submitted_data: List of dicts with keys: evaluator, patientId, queryNum
                        (matching what was submitted to Google Sheets)
    
    This marks queries as completed if they were submitted to Google Sheets.
    Useful for recovering progress after Streamlit Cloud file system reset.
    """
    evaluations = load_evaluations()
    created_keys = []
    
    for submission in submitted_data:
        evaluator = submission.get('evaluator', '').strip()
        patient_id = str(submission.get('patientId', '')).strip()
        query_num_raw = submission.get('queryNum', '')
        
        # Normalize query number to match assignment format (e.g., "1" -> "1.0")
        try:
            # Convert to float then back to string with .0 if whole number
            qnum_float = float(query_num_raw)
            if qnum_float == int(qnum_float):
                query_num = f"{int(qnum_float)}.0"
            else:
                query_num = str(qnum_float)
        except (ValueError, TypeError):
            query_num = str(query_num_raw)
        
        if evaluator and patient_id and query_num:
            key = f"{evaluator}_{patient_id}_{query_num}"
            created_keys.append(key)
            
            if key not in evaluations:
                evaluations[key] = {
                    'started': True,
                    'model_a_graded': True,
                    'model_b_graded': True,
                    'comparison_done': True,
                    'model_a_data': {},
                    'model_b_data': {},
                    'comparison_data': {}
                }
            else:
                # Update to mark as completed
                evaluations[key].update({
                    'started': True,
                    'model_a_graded': True,
                    'model_b_graded': True,
                    'comparison_done': True
                })
    
    save_evaluations(evaluations)
    return len(submitted_data), created_keys[:5]  # Return count and sample keys

