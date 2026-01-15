"""
DOCX Parser Utility for Medical Evaluation Platform
Extracts Model A and Model B responses from DOCX files with full formatting and hyperlinks preserved.
"""

from pathlib import Path
import re
from typing import Dict, Optional, Tuple

try:
    import mammoth
    MAMMOTH_AVAILABLE = True
except ImportError:
    MAMMOTH_AVAILABLE = False
    try:
        from docx import Document
        DOCX_AVAILABLE = True
    except ImportError:
        DOCX_AVAILABLE = False
        Document = None  # Will be checked before use


def parse_docx(file_path: Path, query_num: Optional[str] = None) -> str:
    """
    Extract content from a DOCX file with formatting and hyperlinks preserved.
    Converts DOCX to HTML to preserve all formatting, styles, and hyperlinks.
    If query_num is provided, extracts only that specific query section.
    
    Args:
        file_path: Path to the DOCX file
        query_num: Optional query number to extract (e.g., "1", "2", "3")
        
    Returns:
        HTML string with preserved formatting and hyperlinks (or specific query if query_num provided)
    """
    try:
        if MAMMOTH_AVAILABLE:
            # Use mammoth to convert DOCX to HTML (preserves formatting and hyperlinks)
            with open(file_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html_content = result.value
                
                # If query_num is specified, extract only that query section
                if query_num:
                    html_content = extract_query_section(html_content, query_num)
                
                return html_content
        else:
            # Fallback to plain text extraction if mammoth is not available
            if not DOCX_AVAILABLE or Document is None:
                return f"Error: Neither mammoth nor python-docx is installed. Cannot parse {file_path}"
            doc = Document(file_path)
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            full_text = "\n\n".join(paragraphs)
            
            # If query_num is specified, extract only that query section
            if query_num:
                full_text = extract_query_section_text(full_text, query_num)
            
            return full_text
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return ""


def extract_query_section(html_content: str, query_num: str) -> str:
    """
    Extract a specific query section from HTML content.
    Looks for patterns like "Query 1", "Query 2", etc.
    
    Args:
        html_content: Full HTML content
        query_num: Query number to extract (e.g., "1", "2", "123.0" -> normalized to "123")
        
    Returns:
        HTML content for the specific query only
    """
    import re
    
    # Normalize query_num: remove ".0" suffix if present (e.g., "123.0" -> "123")
    # This handles query numbers stored as floats in assignments
    query_num_str = str(query_num)
    if query_num_str.endswith('.0'):
        normalized_query_num = query_num_str[:-2]  # Remove ".0" suffix
    else:
        normalized_query_num = query_num_str
    
    # Pattern to match "Query X" where X is the query number
    # Handle variations: "Query 1", "Query1", "Query  1", etc.
    pattern = rf'(?:<[^>]*>)?\s*Query\s+{normalized_query_num}\s*(?:</[^>]*>)?'
    
    # Find all query markers
    query_markers = list(re.finditer(r'Query\s+(\d+)', html_content, re.IGNORECASE))
    
    if not query_markers:
        # No query markers found, return all content
        return html_content
    
    # Find the target query
    target_query_idx = None
    for idx, match in enumerate(query_markers):
        if match.group(1) == normalized_query_num:
            target_query_idx = idx
            break
    
    if target_query_idx is None:
        # Query number not found, return all content
        return html_content
    
    # Extract content from this query to the next query (or end)
    start_pos = query_markers[target_query_idx].start()
    
    if target_query_idx + 1 < len(query_markers):
        # There's a next query, extract up to that point
        end_pos = query_markers[target_query_idx + 1].start()
        return html_content[start_pos:end_pos]
    else:
        # This is the last query, extract to the end
        return html_content[start_pos:]


def extract_query_section_text(text_content: str, query_num: str) -> str:
    """
    Extract a specific query section from plain text content.
    
    Args:
        text_content: Full text content
        query_num: Query number to extract (e.g., "1", "2", "123.0" -> normalized to "123")
        
    Returns:
        Text content for the specific query only
    """
    import re
    
    # Normalize query_num: remove ".0" suffix if present (e.g., "123.0" -> "123")
    query_num_str = str(query_num)
    if query_num_str.endswith('.0'):
        normalized_query_num = query_num_str[:-2]  # Remove ".0" suffix
    else:
        normalized_query_num = query_num_str
    
    # Split by query markers
    parts = re.split(r'(Query\s+\d+)', text_content, flags=re.IGNORECASE)
    
    # Find the target query section
    target_query = f"Query {normalized_query_num}"
    for i, part in enumerate(parts):
        if part.strip().lower() == target_query.lower():
            # Found the query marker, return content until next query or end
            if i + 1 < len(parts):
                # Combine the query marker with its content
                return part + parts[i + 1]
            else:
                return part
    
    # Query not found, return all content
    return text_content


def normalize_query_num(query_num: str) -> str:
    """
    Normalize query number to integer string for matching.
    
    The DOCX files use absolute query numbers (Query 25, Query 26, etc.)
    matching the CSV query numbers.
    
    Example:
    - "27.0" -> "27"
    - "27" -> "27"
    """
    try:
        return str(int(float(query_num)))
    except (ValueError, TypeError):
        return query_num


def get_base_patient_patterns(patient_id: str) -> list:
    """
    Get multiple patterns to search for DOCX files.
    
    For Groups B/C, patient IDs vary in the last few digits.
    We generate multiple search patterns to find the right file.
    
    Example:
    - Patient 'a-7654.E-3203720' might match file 'a-7654.E-3203718'
    - Patient 'e--01VpybtxGbfWas5bGmzw5' might match file 'e--01VpybtxGbfWas5bGmzw3'
    """
    pid = str(patient_id)
    patterns = [pid]  # Always try exact match first
    
    # Try stripping last 1, 2, or 3 digits to find base pattern
    if len(pid) > 5:
        patterns.append(pid[:-1])  # Strip 1 digit
        patterns.append(pid[:-2])  # Strip 2 digits
        if len(pid) > 10:
            patterns.append(pid[:-3])  # Strip 3 digits
    
    return patterns


def find_model_responses(docx_folder: Path, patient_id: str, query_num: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Find and extract Model A and Model B responses for a given patient and query.
    
    Expected folder structure:
    - docx_folder/model_a/ contains Model A files
    - docx_folder/model_b/ contains Model B files
    
    Expected file naming patterns:
    - "Patient {PatientID}, Model A.docx"
    - "Patient {PatientID}, Model B.docx"
    
    Args:
        docx_folder: Path to folder containing model_a/ and model_b/ subfolders
        patient_id: Patient ID to match
        query_num: Query number to match (absolute, will be converted to relative 1-4)
        
    Returns:
        Tuple of (model_a_text, model_b_text)
    """
    model_a_text = None
    model_b_text = None
    
    # Normalize query number (e.g., "27.0" -> "27")
    normalized_query = normalize_query_num(query_num)
    
    if not docx_folder.exists():
        return None, None
    
    # Check for model_a and model_b subfolders
    model_a_folder = docx_folder / "model_a"
    model_b_folder = docx_folder / "model_b"
    
    # Pattern: "Patient {PatientID}, Model A.docx"
    # Try exact match first
    patterns_a = [
        f"Patient {patient_id}, Model A.docx",
        f"Patient {patient_id}, Model A",
        f"*Patient*{patient_id}*Model A*.docx",
        f"*{patient_id}*Model A*.docx",
        f"*{patient_id}*A*.docx",
    ]
    
    patterns_b = [
        f"Patient {patient_id}, Model B.docx",
        f"Patient {patient_id}, Model B",
        f"*Patient*{patient_id}*Model B*.docx",
        f"*{patient_id}*Model B*.docx",
        f"*{patient_id}*B*.docx",
    ]
    
    # Get multiple search patterns for fallback
    search_patterns = get_base_patient_patterns(patient_id)
    
    # Search in model_a folder
    if model_a_folder.exists():
        for pattern in patterns_a:
            matches = list(model_a_folder.glob(pattern))
            if matches:
                model_a_text = parse_docx(matches[0], normalized_query)
                break
        
        # If not found, search all files with multiple patterns
        if not model_a_text:
            all_docx = list(model_a_folder.glob("*.docx"))
            for search_pat in search_patterns:
                for file in all_docx:
                    if search_pat in file.stem:
                        model_a_text = parse_docx(file, normalized_query)
                        break
                if model_a_text:
                    break
    
    # Search in model_b folder
    if model_b_folder.exists():
        for pattern in patterns_b:
            matches = list(model_b_folder.glob(pattern))
            if matches:
                model_b_text = parse_docx(matches[0], normalized_query)
                break
        
        # If not found, search all files with multiple patterns
        if not model_b_text:
            all_docx = list(model_b_folder.glob("*.docx"))
            for search_pat in search_patterns:
                for file in all_docx:
                    if search_pat in file.stem:
                        model_b_text = parse_docx(file, normalized_query)
                        break
                if model_b_text:
                    break
    
    # Fallback: search in root folder if subfolders don't exist
    if (not model_a_text or not model_b_text) and not (model_a_folder.exists() and model_b_folder.exists()):
        all_docx = list(docx_folder.glob("*.docx"))
        for file in all_docx:
            if patient_id in file.stem:
                stem_lower = file.stem.lower()
                if 'model a' in stem_lower or ('model' in stem_lower and 'a' in stem_lower):
                    if not model_a_text:
                        model_a_text = parse_docx(file, normalized_query)
                elif 'model b' in stem_lower or ('model' in stem_lower and 'b' in stem_lower):
                    if not model_b_text:
                        model_b_text = parse_docx(file, normalized_query)
    
    return model_a_text, model_b_text


def get_all_docx_files(docx_folder: Path) -> Dict[str, Dict[str, Tuple[str, str]]]:
    """
    Scan folder and organize DOCX files by patient_id and query_num.
    
    Returns:
        Dictionary: {patient_id: {query_num: (model_a_path, model_b_path)}}
    """
    result = {}
    
    if not docx_folder.exists():
        return result
    
    all_docx = list(docx_folder.glob("*.docx"))
    
    for file in all_docx:
        stem = file.stem
        # Try to extract patient_id and query_num from filename
        # This is a heuristic - adjust based on actual naming convention
        parts = re.split(r'[_\-\s]+', stem)
        
        # Look for patterns like: PatientID_QueryNum_ModelA
        # or: PatientID_QueryNum_A
        for i, part in enumerate(parts):
            if part.lower() in ['a', 'b', 'modela', 'modelb', 'model_a', 'model_b']:
                if i >= 2:
                    patient_id = parts[0]
                    query_num = parts[1]
                    
                    if patient_id not in result:
                        result[patient_id] = {}
                    if query_num not in result[patient_id]:
                        result[patient_id][query_num] = (None, None)
                    
                    if 'a' in part.lower():
                        result[patient_id][query_num] = (str(file), result[patient_id][query_num][1])
                    elif 'b' in part.lower():
                        result[patient_id][query_num] = (result[patient_id][query_num][0], str(file))
    
    return result

