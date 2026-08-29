"""
detection/indian_plate_formatter.py — Post-OCR extraction and normalisation
for Indian vehicle registration plates.

Indian plates follow a strict positional format:
    [State: 2 letters][District: 2 digits][Series: 1-3 letters][Number: 4 digits]

Examples:
    GJ02EC7324   (Gujarat, district 02, series EC, number 7324)
    KL13AK6389   (Kerala, district 13, series AK, number 6389)
    MH12AB1234   (Maharashtra, district 12, series AB, number 1234)
    DL01CA0001   (Delhi, district 01, series CA, number 0001)

This module provides two functions:
1. extract_indian_plate()  — Regex-scan raw OCR text to find the plate substring.
2. normalize_plate_chars() — Position-aware O/0, I/1, S/5, B/8 correction.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Indian state/UT codes (2-letter RTO prefixes).  Used to validate that the
# extracted plate starts with a real state code, not random letters.
# ---------------------------------------------------------------------------
_INDIAN_STATE_CODES = frozenset({
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "GA",
    "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH",
    "ML", "MN", "MP", "MZ", "NL", "OD", "PB", "PY", "RJ", "SK",
    "TN", "TR", "TS", "UK", "UP", "WB",
})

# ---------------------------------------------------------------------------
# Primary regex: matches the standard Indian plate format.
# Allows common OCR confusions in letter and digit positions.
# ---------------------------------------------------------------------------
L = r'[A-Z01245678]'
D = r'[0-9OISBZGDQJLTAC]'

_PLATE_REGEX = re.compile(
    f'({L}{{2}}'       # State code (2 letters)
    f'{D}{{2}}'        # District number (2 digits)
    f'{L}{{1,3}}'      # Series letters (1-3 letters)
    f'{D}{{1,4}})'     # Registration number (1-4 digits)
)

# Bharat (BH) series: YYBBHNNNNLL
_BH_REGEX = re.compile(
    r'(\d{2}BH\d{4}[A-Z]{1,2})'
)

# Expanded fix mappings for aggressive OCR correction
DIGIT_FIXES = {
    'O': '0', 'D': '0', 'Q': '0', 'C': '0',
    'I': '1', 'J': '1', 'L': '1',
    'Z': '2',
    'A': '4',
    'S': '5',
    'G': '6',
    'T': '7',
    'B': '8',
}

LETTER_FIXES = {
    '0': 'O', 
    '1': 'I', 
    '2': 'Z',
    '4': 'A',
    '5': 'S',
    '6': 'G',
    '7': 'T',
    '8': 'B',
}

def _fix_state_code(code: str) -> str:
    """
    Attempt to aggressively fix a 2-char state code by exploring combinations
    of known OCR confusions (like '0' -> 'D' for DL, '8' -> 'B' for BR).
    """
    if len(code) != 2:
        return code
        
    chars = list(code)
    options = []
    
    for c in chars:
        opts = [c]
        if c in LETTER_FIXES:
            opts.append(LETTER_FIXES[c])
        # Special context-aware additions for state codes
        if c == '0':
            opts.append('D')  # DL, DD
        if c == '1':
            opts.append('J')  # JK, JH, GJ, RJ, MZ
        if c == '5':
            opts.append('G')  # GJ, GA
        options.append(opts)
        
    # Generate all pairs and return the first valid state code
    for c1 in options[0]:
        for c2 in options[1]:
            candidate = c1 + c2
            if candidate in _INDIAN_STATE_CODES:
                return candidate
                
    # Fallback to standard letter fixes
    return ''.join(LETTER_FIXES.get(c, c) for c in chars)

def extract_indian_plate(raw_text: str) -> Optional[str]:
    """
    Scan the raw OCR text for an Indian registration plate substring.

    Args:
        raw_text: Raw OCR output (already uppercased, alphanumeric only).

    Returns:
        The extracted plate string, or None.
    """
    if not raw_text or len(raw_text) < 6:
        return None

    text = raw_text.upper().strip()

    # Try Bharat series first (less common but distinct format)
    bh_match = _BH_REGEX.search(text)
    if bh_match:
        return bh_match.group(1)

    # Search for overlapping matches to prevent garbage prefixes from consuming valid plates
    all_matches = []
    for i in range(len(text)):
        m = _PLATE_REGEX.match(text[i:])
        if m:
            span = m.group(1)
            all_matches.append((span, len(span)))

    if not all_matches:
        return None

    # Filter to matches whose original span (after normalisation)
    # starts with a valid Indian state code
    valid_matches = []
    for original_span, length in all_matches:
        state = _fix_state_code(original_span[:2])
        if state in _INDIAN_STATE_CODES:
            valid_matches.append((original_span, length))

    if not valid_matches:
        # We no longer fall back to all_matches. 
        # Because the regex is forgiving, falling back would extract garbage like 'ERSITY9127'.
        return None

    # Prefer the longest match (most complete plate read)
    best_span, _ = max(valid_matches, key=lambda x: x[1])

    # Minimum length sanity check: shortest valid plates are ~8 chars
    if len(best_span) < 8:
        return None

    return best_span


def normalize_plate_chars(plate: str) -> str:
    """
    Apply position-aware character normalisation to an Indian plate string.

    Args:
        plate: Extracted plate string (uppercase, alphanumeric only).

    Returns:
        Normalised plate string.
    """
    if not plate or len(plate) < 8:
        return plate

    # BH-series plates (e.g. 22BH1234AB) have a completely different
    # structural layout — digits first, not state letters. Skip standard
    # normalization which assumes positions 0-1 are letters.
    if _BH_REGEX.match(plate):
        return plate

    chars = list(plate)

    # Fix state code (positions 0-1) using context-aware mapping
    state_fixed = _fix_state_code(''.join(chars[:2]))
    if len(state_fixed) == 2:
        chars[0], chars[1] = state_fixed[0], state_fixed[1]

    # Fix district code (positions 2-3): must be digits
    for i in range(2, min(4, len(chars))):
        if chars[i] in DIGIT_FIXES:
            chars[i] = DIGIT_FIXES[chars[i]]

    # For the remaining characters, find the split point between
    # the series letters and the registration number digits.
    if len(chars) > 4:
        # The registration number is at most 4 digits.
        # We scan up to 4 characters from the end.
        reg_start = len(chars)
        for i in range(len(chars) - 1, max(3, len(chars) - 5), -1):
            if chars[i].isdigit() or chars[i] in DIGIT_FIXES:
                reg_start = i
            else:
                break

        # Ensure we leave at least one character for the series 
        # (Series starts at index 4, so reg_start must be at least 5)
        if reg_start < 5:
            reg_start = 5

        # Fix series letters (position 4 to reg_start-1)
        # 'O' is not used in Indian plate series, usually it's a misread 'D'
        for i in range(4, reg_start):
            if chars[i] == 'O' or chars[i] == '0':
                chars[i] = 'D'
            elif chars[i] in LETTER_FIXES:
                chars[i] = LETTER_FIXES[chars[i]]

        # Fix registration digits (reg_start to end)
        for i in range(reg_start, len(chars)):
            if chars[i] in DIGIT_FIXES:
                chars[i] = DIGIT_FIXES[chars[i]]

    return ''.join(chars)
