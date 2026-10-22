from __future__ import annotations

from pathlib import Path


def metadata_row_problems(row: dict, expected_patient_id: str | None = None) -> list[str]:
    problems = []
    patient_id = row.get('patient_id')
    if not isinstance(patient_id, str) or not patient_id:
        problems.append('patient_id_missing')
    elif expected_patient_id is not None and patient_id != str(expected_patient_id):
        problems.append('requested_patient_mismatch')
    if row.get('split') != 'train':
        problems.append('non_train_metadata')
    for source in row.get('report_sources') or []:
        parts = Path(str(source).replace('\\', '/')).parts
        if not parts or parts[0] != patient_id or '..' in parts:
            problems.append('report_source_patient_mismatch')
    for image_ref in row.get('image_references') or []:
        parts = Path(str(image_ref).replace('\\', '/')).parts
        if not parts or parts[0] != patient_id or '..' in parts:
            problems.append('image_patient_mismatch')
    return sorted(set(problems))


def chat_request_error(message: object, has_image: bool = False) -> str:
    return ('Image request failed: ' if has_image else 'Request failed: ') + str(message)
