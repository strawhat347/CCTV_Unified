import re

class PlateCorrector:
    def __init__(self):
        # Mappings for common OCR mistakes
        self.letter_to_number = {
            'O': '0', 'Q': '0', 'D': '0',
            'I': '1', 'L': '1', 'T': '1',
            'Z': '2',
            'E': '3',
            'A': '4',
            'S': '5',
            'G': '6',
            'B': '8'
        }
        self.number_to_letter = {
            '0': 'O',
            '1': 'I',
            '2': 'Z',
            '3': 'E',
            '4': 'A',
            '5': 'S',
            '6': 'G',
            '7': 'T',
            '8': 'B',
            '9': 'P'
        }

    def _fix_char(self, char: str, expect_type: str) -> str:
        if expect_type == 'letter':
            if char.isdigit():
                return self.number_to_letter.get(char, char)
            return char
        elif expect_type == 'number':
            if char.isalpha():
                return self.letter_to_number.get(char, char)
            return char
        return char

    def correct(self, text: str) -> str:
        # Remove spaces and non-alphanumeric chars
        cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
        if len(cleaned) < 5 or len(cleaned) > 11:
            return text  # Leave it alone if it's completely malformed

        # Check for BH Series: YY BH #### XX
        if len(cleaned) >= 8:
            char2, char3 = cleaned[2], cleaned[3]
            # If it loosely matches "BH"
            if char2 in ['B', '8'] and char3 in ['H', '4', 'N', 'M']:
                corrected = ""
                # YY (Numbers)
                corrected += self._fix_char(cleaned[0], 'number')
                corrected += self._fix_char(cleaned[1], 'number')
                # BH
                corrected += "BH"
                # #### (Numbers)
                for i in range(4, min(8, len(cleaned))):
                    corrected += self._fix_char(cleaned[i], 'number')
                # XX (Letters)
                for i in range(8, len(cleaned)):
                    corrected += self._fix_char(cleaned[i], 'letter')
                return corrected

        # Standard Indian Format dynamic correction
        chars = list(cleaned)
        
        # State Code (first 2 must be letters)
        if len(chars) >= 2:
            chars[0] = self._fix_char(chars[0], 'letter')
            chars[1] = self._fix_char(chars[1], 'letter')
            
        # District Code (next 2 must be numbers)
        for i in range(2, min(4, len(chars))):
            chars[i] = self._fix_char(chars[i], 'number')
            
        if len(chars) > 4:
            # Registration digits are at the end (up to 4)
            # Find where registration digits start by scanning from the end
            reg_start = len(chars)
            scan_limit = max(4, len(chars) - 4)
            for i in range(len(chars) - 1, scan_limit - 1, -1):
                if chars[i].isdigit() or chars[i] in self.letter_to_number:
                    reg_start = i
                else:
                    break
                    
            if reg_start < 5:
                reg_start = 5  # Leave at least one series letter if length permits, or start at 5 (index 4) if 0 series letters
                
            # Series letters
            for i in range(4, min(reg_start, len(chars))):
                chars[i] = self._fix_char(chars[i], 'letter')
                
            # Registration numbers
            for i in range(reg_start, len(chars)):
                chars[i] = self._fix_char(chars[i], 'number')
                
        return ''.join(chars)
