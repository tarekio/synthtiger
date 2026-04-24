import argparse
import re
import sys
import os

allowed_set = r"٠١٢٣٤٥٦٧٨٩ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهوىي؟؛«»—،%!#$&'()*+,-./:;<=>?@[\]^_`{|}~×÷“”‘’…"

# 2. Mappings: Bad/Variant Char -> Good Char
# Maps characters from your "Second List" to the "Target List".
mappings = {
    # --- Explicit Removal ---
    'ـ': '', 

    # --- Hamza Normalization ---
    # 'أ': 'ا', 'إ': 'ا', 'آ': 'ا',
    # 'ؤ': 'و', 'ئ': 'ي',
    'ٲ': 'أ', 'ٳ': 'إ', 'ٶ': 'و', 'ٸ': 'ي',

    # --- Ta Marbuta Normalization ---
    'ة': 'ة', 'ۃ': 'ة',

    # --- Presentation Forms (Visual Glyphs) -> Standard ---
    'ﻢ': 'م', 'ﻤ': 'م', 'ﻣ': 'م', 'ﻡ': 'م',
    'ﺎ': 'ا', 'ﺍ': 'ا',
    'ﻫ': 'ه', 'ﻬ': 'ه', 'ﻪ': 'ه', 'ﻩ': 'ه',
    'ﺫ': 'ذ', 'ﺬ': 'ذ',
    'ﺑ': 'ب', 'ﺒ': 'ب', 'ﺐ': 'ب', 'ﺏ': 'ب',
    'ﺤ': 'ح', 'ﺣ': 'ح', 'ﺢ': 'ح',
    'ﺨ': 'خ', 'ﺧ': 'خ', 'ﺦ': 'خ',
    'ﺮ': 'ر',
    'ﺗ': 'ت', 'ﺘ': 'ت', 'ﺖ': 'ت', 'ﺕ': 'ت',
    'ﺩ': 'د', 'ﺪ': 'د',
    'ﻛ': 'ك', 'ﻜ': 'ك', 'ﻚ': 'ك', 'ﻙ': 'ك',
    'ﻴ': 'ي', 'ﻳ': 'ي', 'ﻲ': 'ي', 'ﻱ': 'ي',
    'ﻨ': 'ن', 'ﻧ': 'ن', 'ﻦ': 'ن', 'ﻥ': 'ن',
    'ﻞ': 'ل', 'ﻟ': 'ل', 'ﻠ': 'ل', 'ﻝ': 'ل',
    'ﺴ': 'س', 'ﺳ': 'س', 'ﺲ': 'س',
    'ﺸ': 'ش', 'ﺷ': 'ش', 'ﺶ': 'ش',
    'ﻌ': 'ع', 'ﻋ': 'ع', 'ﻊ': 'ع',
    'ﻐ': 'غ', 'ﻏ': 'غ', 'ﻎ': 'غ',
    'ﻔ': 'ف', 'ﻓ': 'ف', 'ﻒ': 'ف',
    'ﻘ': 'ق', 'ﻗ': 'ق', 'ﻖ': 'ق',
    'ﻀ': 'ض', 'ﺿ': 'ض', 'ﺾ': 'ض',
    'ﺼ': 'ص', 'ﺻ': 'ص', 'ﺺ': 'ص',
    'ﻄ': 'ط', 'ﻃ': 'ط', 'ﻂ': 'ط',
    'ﻈ': 'ظ', 'ﻇ': 'ظ', 'ﻆ': 'ظ',
    # 'ﺔ': 'ه', 'ﺓ': 'ه',
    'ﺰ': 'ز', 'ﺯ': 'ز',
    'ﺞ': 'ج', 'ﺟ': 'ج', 'ﺠ': 'ج',
    'ﺖ': 'ة',  # Ta Marbuta presentation forms

    # --- Western Arabic Numbers -> Eastern Arabic Numbers ---
    '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤', 
    '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩',

    # --- Persian/Urdu Numbers -> Eastern Arabic Numbers ---
    '۰': '٠', '۱': '١', '۲': '٢', '۳': '٣', '۴': '٤', 
    '۵': '٥', '۶': '٦', '۷': '٧', '۸': '٨', '۹': '٩',

    # --- Variants & Extra Letters ---
    'ٹ': 'ت', 'ٺ': 'ت', 'ټ': 'ت',
    'ډ': 'د', 'ڊ': 'د',
    'ړ': 'ر', 'ڔ': 'ر', 'ڕ': 'ر',
    'ڙ': 'ز',
    'ڜ': 'ش',
    'ڠ': 'غ',
    'ڧ': 'ق', 'ڨ': 'ق',
    'ڪ': 'ك', 'ګ': 'ك', 'ڬ': 'ك', 'ڭ': 'ك', 
    'ڰ': 'ك', 
    'ڵ': 'ل', 'ڷ': 'ل',
    'ں': 'ن', 'ڼ': 'ن',
    'ھ': 'ه', 'ہ': 'ه', 'ە': 'ه', 
    'ۆ': 'و', 'ۇ': 'و', 'ۈ': 'و', 'ۉ': 'و', 'ۋ': 'و', 'ۥ': 'و',
    'ێ': 'ي', 'ې': 'ي', 'ے': 'ي', 'ۓ': 'ي', 'ۦ': 'ي', 'ى': 'ي',
}

def clean_line(text, whitespace=False):
    # 1. The Allowed Vocabulary (Target List)
    # Includes: Standard Arabic, English, Numbers, Punctuation, and New Symbols (×÷“”‘’…)
    # Note: 'ـ' (Tatweel) is intentionally excluded.
    cleaned_chars = []
    if whitespace:
        allowed_set.add(' ')  # Add space to allowed characters if whitespace preservation is enabled

    for char in text:
        # 1. Check Mapping
        if char in mappings:
            cleaned_chars.append(mappings[char])
        # 2. Check Allowed List
        elif char in allowed_set:
            cleaned_chars.append(char)
        # 3. Else: Drop (it's dirty and unmapped)
        
    return "".join(cleaned_chars)
    

def process_files(input_files, output_file, whitespace):
    print(f"--- Processing {len(input_files)} files ---")
    
    try:
        with open(output_file, 'w', encoding='utf-8') as outfile:
            for file_path in input_files:
                if not os.path.exists(file_path):
                    print(f"⚠️  Warning: File '{file_path}' not found. Skipping.")
                    continue

                with open(file_path, 'r', encoding='utf-8') as infile:
                    for line in infile:
                        # Split by tab to remove the ID (assuming format: ID \t Text)
                        parts = line.split('\t', 1)
                        
                        if len(parts) > 1:
                            # We have an ID and text
                            raw_text = parts[1]
                        else:
                            # No tab found, process the whole line
                            raw_text = line

                        # Clean the text
                        final_text = clean_line(raw_text, whitespace=whitespace)

                        # Only write if there is text left (don't write empty lines)
                        if final_text:
                            # spilt by whitespace
                            final_text = final_text.split()
                            for word in final_text:
                                # print(f"Writing word: '{word}'")  # Optional: uncomment for verbose output
                                if len(word) < 20:  # Optional: filter out very long "words"
                                    outfile.write(word + '\n')
                                else:
                                    print(f"Filtered out long word: '{word}' from file: {file_path} raw: '{raw_text}' cleaned: '{final_text}'") # Optional: uncomment for verbose output
                            # outfile.write(final_text + '\n') # Original line writing (commented out for word-by-word writing)
                            # outfile.write(final_text + '\n')

        print(f"✅ Success! Cleaned sentences saved to: {output_file}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean Arabic text files: Remove IDs, non-Arabic words/symbols, and merge into one file."
    )
    
    parser.add_argument(
        "inputs", 
        nargs='+', 
        help="List of input .txt files"
    )
    
    parser.add_argument(
        "-o", "--output", 
        default="cleaned_dataset.txt",
        help="Output filename (default: cleaned_dataset.txt)"
    )

    parser.add_argument(
        "-w", "--whitespace",
        action='store_true',
        help="Preserve whitespace characters (default: False)"
    )

    args = parser.parse_args()
    process_files(args.inputs, args.output, args.whitespace)