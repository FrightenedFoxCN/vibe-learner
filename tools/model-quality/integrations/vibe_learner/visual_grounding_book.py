"""Private user-provided book pages; OCR is identically shared by every arm."""
from pathlib import Path
from .visual_grounding_book_detector import propose_book
from .visual_grounding_natural import grounded_proposals

def book_proposals(context,source,variant):
    layout,ocr=propose_book(Path(source['path']).read_bytes())
    if variant=='dino':
        proposals,det=grounded_proposals(context,source,'dino')
        det['full_ocr_lines']=ocr['full_ocr_lines'];det['ocr_layout_diagnostic']=ocr
        return proposals,det
    return layout,ocr

from .visual_grounding import run_sample,source_manifest
