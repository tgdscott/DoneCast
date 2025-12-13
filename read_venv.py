import sys
import os

try:
    # try utf-16 first as suspected
    content = ""
    path = "pip_venv_output.txt"
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-16-le') as f:
                content = f.read()
        except:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        
        print(content)
        # Also write to a clean file
        with open("venv_location_clean.txt", "w", encoding="utf-8") as out:
            out.write(content)
    else:
        print("File not found")
except Exception as e:
    print(f"Error: {e}")
