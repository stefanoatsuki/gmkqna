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
            # Use .get() with empty string default, but preserve the actual value (don't strip here - preserve as-is)
            model_a_data = {
                'source_yes_no': str(submission.get('a_source', '') or '').strip(),
                'source_explain': str(submission.get('a_source_f', '') or ''),  # Preserve comments as-is
                'hallucination_yes_no': str(submission.get('a_hallucination', '') or '').strip(),
                'hallucination_explain': str(submission.get('a_hall_f', '') or ''),  # Preserve comments as-is
                'safety_yes_no': str(submission.get('a_safety', '') or '').strip(),
                'safety_explain': str(submission.get('a_safety_f', '') or ''),  # Preserve comments as-is
                'content_yes_no': str(submission.get('a_completeness', '') or '').strip(),
                'content_explain': str(submission.get('a_comp_f', '') or ''),  # Preserve comments as-is
                'extraneous_yes_no': str(submission.get('a_extraneous', '') or '').strip(),
                'extraneous_explain': str(submission.get('a_extra_f', '') or ''),  # Preserve comments as-is
                'flow_yes_no': str(submission.get('a_flow', '') or '').strip(),
                'flow_explain': str(submission.get('a_flow_f', '') or '')  # Preserve comments as-is
            }
            
            # Restore Model B evaluation data
            model_b_data = {
                'source_yes_no': str(submission.get('b_source', '') or '').strip(),
                'source_explain': str(submission.get('b_source_f', '') or ''),  # Preserve comments as-is
                'hallucination_yes_no': str(submission.get('b_hallucination', '') or '').strip(),
                'hallucination_explain': str(submission.get('b_hall_f', '') or ''),  # Preserve comments as-is
                'safety_yes_no': str(submission.get('b_safety', '') or '').strip(),
                'safety_explain': str(submission.get('b_safety_f', '') or ''),  # Preserve comments as-is
                'content_yes_no': str(submission.get('b_completeness', '') or '').strip(),
                'content_explain': str(submission.get('b_comp_f', '') or ''),  # Preserve comments as-is
                'extraneous_yes_no': str(submission.get('b_extraneous', '') or '').strip(),
                'extraneous_explain': str(submission.get('b_extra_f', '') or ''),  # Preserve comments as-is
                'flow_yes_no': str(submission.get('b_flow', '') or '').strip(),
                'flow_explain': str(submission.get('b_flow_f', '') or '')  # Preserve comments as-is
            }
            
            # Restore comparison data
            comparison_data = {
                'preference': submission.get('preference', ''),
                'preference_reasons': submission.get('pref_reasons', '')
            }
            
            # Determine what's been completed based on what data exists
            # Check if Model A has any scores OR comments (at least one metric filled)
            has_model_a_scores = any([
                submission.get('a_source', '').strip(),
                submission.get('a_hallucination', '').strip(),
                submission.get('a_safety', '').strip(),
                submission.get('a_completeness', '').strip(),
                submission.get('a_extraneous', '').strip(),
                submission.get('a_flow', '').strip()
            ])
            has_model_a_comments = any([
                submission.get('a_source_f', '').strip(),
                submission.get('a_hall_f', '').strip(),
                submission.get('a_safety_f', '').strip(),
                submission.get('a_comp_f', '').strip(),
                submission.get('a_extra_f', '').strip(),
                submission.get('a_flow_f', '').strip()
            ])
            has_model_a_data = has_model_a_scores or has_model_a_comments
            
            # Check if Model B has any scores OR comments (at least one metric filled)
            has_model_b_scores = any([
                submission.get('b_source', '').strip(),
                submission.get('b_hallucination', '').strip(),
                submission.get('b_safety', '').strip(),
                submission.get('b_completeness', '').strip(),
                submission.get('b_extraneous', '').strip(),
                submission.get('b_flow', '').strip()
            ])
            has_model_b_comments = any([
                submission.get('b_source_f', '').strip(),
                submission.get('b_hall_f', '').strip(),
                submission.get('b_safety_f', '').strip(),
                submission.get('b_comp_f', '').strip(),
                submission.get('b_extra_f', '').strip(),
                submission.get('b_flow_f', '').strip()
            ])
            has_model_b_data = has_model_b_scores or has_model_b_comments
            
            # Check if comparison is done (preference is filled)
            has_preference = bool(submission.get('preference', '').strip())
            
            # Determine if anything has been started
            has_any_data = has_model_a_data or has_model_b_data or has_preference
            
            if key not in evaluations:
                evaluations[key] = {
                    'started': has_any_data,
                    'model_a_graded': has_model_a_scores,  # Only mark as graded if scores exist
                    'model_b_graded': has_model_b_scores,  # Only mark as graded if scores exist
                    'comparison_done': has_preference,
                    'model_a_data': model_a_data if has_model_a_data else {},
                    'model_b_data': model_b_data if has_model_b_data else {},
                    'comparison_data': comparison_data if has_preference else {}
                }
            else:
                # Update with restored data (Google Sheets is source of truth)
                # Only update fields that have data, preserve existing if Google Sheets is empty
                existing = evaluations[key]
                evaluations[key].update({
                    'started': has_any_data or existing.get('started', False),
                    'model_a_graded': has_model_a_scores or existing.get('model_a_graded', False),
                    'model_b_graded': has_model_b_scores or existing.get('model_b_graded', False),
                    'comparison_done': has_preference or existing.get('comparison_done', False)
                })
                # Only update data if we have it from Google Sheets (including comments)
                if has_model_a_data:
                    evaluations[key]['model_a_data'] = model_a_data
                if has_model_b_data:
                    evaluations[key]['model_b_data'] = model_b_data
                if has_preference:
                    evaluations[key]['comparison_data'] = comparison_data
    
    save_evaluations(evaluations)
    return len(submitted_data), created_keys[:5]  # Return count and sample keys

