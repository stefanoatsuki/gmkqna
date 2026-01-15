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
        submitted_data: List of dicts with keys: evaluator, patientId, queryNum, and all
                        evaluation data (model_a_data, model_b_data, comparison_data)
                        (matching what was submitted to Google Sheets)
    
    This fully restores evaluation data including all scores, explanations, and preferences
    from Google Sheets. Useful for recovering progress after Streamlit Cloud file system reset.
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
            
            # Restore Model A evaluation data
            model_a_data = {
                'source_yes_no': submission.get('a_source', ''),
                'source_explain': submission.get('a_source_f', ''),
                'hallucination_yes_no': submission.get('a_hallucination', ''),
                'hallucination_explain': submission.get('a_hall_f', ''),
                'safety_yes_no': submission.get('a_safety', ''),
                'safety_explain': submission.get('a_safety_f', ''),
                'content_yes_no': submission.get('a_completeness', ''),
                'content_explain': submission.get('a_comp_f', ''),
                'extraneous_yes_no': submission.get('a_extraneous', ''),
                'extraneous_explain': submission.get('a_extra_f', ''),
                'flow_yes_no': submission.get('a_flow', ''),
                'flow_explain': submission.get('a_flow_f', '')
            }
            
            # Restore Model B evaluation data
            model_b_data = {
                'source_yes_no': submission.get('b_source', ''),
                'source_explain': submission.get('b_source_f', ''),
                'hallucination_yes_no': submission.get('b_hallucination', ''),
                'hallucination_explain': submission.get('b_hall_f', ''),
                'safety_yes_no': submission.get('b_safety', ''),
                'safety_explain': submission.get('b_safety_f', ''),
                'content_yes_no': submission.get('b_completeness', ''),
                'content_explain': submission.get('b_comp_f', ''),
                'extraneous_yes_no': submission.get('b_extraneous', ''),
                'extraneous_explain': submission.get('b_extra_f', ''),
                'flow_yes_no': submission.get('b_flow', ''),
                'flow_explain': submission.get('b_flow_f', '')
            }
            
            # Restore comparison data
            comparison_data = {
                'preference': submission.get('preference', ''),
                'preference_reasons': submission.get('pref_reasons', '')
            }
            
            if key not in evaluations:
                evaluations[key] = {
                    'started': True,
                    'model_a_graded': True,
                    'model_b_graded': True,
                    'comparison_done': True,
                    'model_a_data': model_a_data,
                    'model_b_data': model_b_data,
                    'comparison_data': comparison_data
                }
            else:
                # Update with restored data (overwrite to ensure we have the latest)
                evaluations[key].update({
                    'started': True,
                    'model_a_graded': True,
                    'model_b_graded': True,
                    'comparison_done': True,
                    'model_a_data': model_a_data,
                    'model_b_data': model_b_data,
                    'comparison_data': comparison_data
                })
    
    save_evaluations(evaluations)
    return len(submitted_data), created_keys[:5]  # Return count and sample keys

