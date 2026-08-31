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
        if len(cleaned) < 8 or len(cleaned) > 10:
            return text  # Leave it alone if it's completely malformed

        # Check for BH Series: YY BH #### XX (9 or 10 chars)
        # Check if index 2 and 3 look like BH (e.g., BH, 8H, B4, 84)
        if len(cleaned) in [9, 10]:
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
                for i in range(4, 8):
                    corrected += self._fix_char(cleaned[i], 'number')
                # XX (Letters)
                for i in range(8, len(cleaned)):
                    corrected += self._fix_char(cleaned[i], 'letter')
                return corrected

        # Standard Indian Format: LL NN LL NNNN (10 chars) or LL NN L NNNN (9 chars)
        if len(cleaned) in [9, 10]:
            corrected = ""
            # State Code (LL)
            corrected += self._fix_char(cleaned[0], 'letter')
            corrected += self._fix_char(cleaned[1], 'letter')
            
            # RTO Code (NN)
            corrected += self._fix_char(cleaned[2], 'number')
            corrected += self._fix_char(cleaned[3], 'number')
            
            # For remaining, it depends on length
            if len(cleaned) == 10:
                # LL NNNN
                corrected += self._fix_char(cleaned[4], 'letter')
                corrected += self._fix_char(cleaned[5], 'letter')
                for i in range(6, 10):
                    corrected += self._fix_char(cleaned[i], 'number')
            else:
                # L NNNN
                corrected += self._fix_char(cleaned[4], 'letter')
                for i in range(5, 9):
                    corrected += self._fix_char(cleaned[i], 'number')
            return corrected

        return text
