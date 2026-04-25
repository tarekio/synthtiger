import re
import argparse
import sys
import os

allowed_set = r"٠١٢٣٤٥٦٧٨٩ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهوىي؟؛«»—،%!#$&'()*+,-./:;<=>?@[\]^_`{|}~×÷“”‘’…"

# Maps characters from your "Second List" to the "Target List".
mappings = {
    # --- Explicit Removal ---
    'ـ': '', 

    # --- Hamza Normalization ---
    'أ': 'ا', 'إ': 'ا', 'آ': 'ا',
    'ؤ': 'و', 'ئ': 'ي',
    'ٲ': 'ا', 'ٳ': 'ا', 'ٶ': 'و', 'ٸ': 'ي',

    # --- Ta Marbuta Normalization ---
    'ة': 'ه', 'ۃ': 'ه',

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
    'ﺔ': 'ه', 'ﺓ': 'ه',
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

def clean_line(text):
    # Includes: Standard Arabic, English, Numbers, Punctuation, and New Symbols (×÷“”‘’…)
    # Note: 'ـ' (Tatweel) is intentionally excluded.
    cleaned_chars = []

    for char in text:
        # 0. skip spaces (optional, can be included if you want to keep them)
        if char.isspace():
            cleaned_chars.append(char)
        # 1. Check Mapping
        elif char in mappings:
            cleaned_chars.append(mappings[char])
        # 2. Check Allowed List
        elif char in allowed_set:
            cleaned_chars.append(char)
        # 3. Else: Drop (it's dirty and unmapped)
        
    return "".join(cleaned_chars)

def process_files(input_files, output_file):
    # This set will hold unique words from ALL files combined
    master_unique_words = set()
    files_processed = 0

    print(f"--- Starting processing ---")

    for file_path in input_files:
        if not os.path.exists(file_path):
            print(f"⚠️  Warning: File '{file_path}' not found. Skipping.")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as infile:
                print(f"Processing: {file_path}...") # Optional: uncomment for verbose output
                
                for line in infile:
                    parts = line.strip().split()
                    
                    # Ensure the line has at least 3 parts (ID, Text, Number)
                    if len(parts) < 3:
                        continue

                    # The Arabic text is everything between the first and last column
                    raw_text = " ".join(parts[1:-1])

                    # Normalize: Remove Tashkeel
                    clean_text = clean_line(raw_text)

                    # Filter: Keep only Arabic words
                    words = clean_text.split()
                    for word in words:
                        if len(word) < 20:
                            master_unique_words.add(word)
                            
            
            files_processed += 1

        except Exception as e:
            print(f"❌ Error reading '{file_path}': {e}")

    # Write the aggregated results to the output file
    if files_processed > 0:
        try:
            with open(output_file, 'w', encoding='utf-8') as outfile:
                for word in sorted(master_unique_words):
                    outfile.write(word + '\n')
            
            print(f"--- Completed ---")
            print(f"Processed {files_processed} files.")
            print(f"Extracted {len(master_unique_words)} unique words.")
            print(f"Saved to: {output_file}")
            
        except Exception as e:
            print(f"Error writing output file: {e}")
    else:
        print("No files were successfully processed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract and normalize unique Arabic words from multiple text files."
    )

    # nargs='+' allows accepting one or more file paths
    parser.add_argument(
        "inputs", 
        nargs='+', 
        help="The input .txt files (e.g., file1.txt file2.txt)"
    )
    
    parser.add_argument(
        "-o", "--output", 
        help="The name of the output file (default: output.txt)", 
        default="output.txt"
    )

    args = parser.parse_args()

    process_files(args.inputs, args.output)