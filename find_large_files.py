
import os
import sys

print("Script started", file=sys.stderr)

def count_lines(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def scan_dir(root_dir, extensions):
    results = []
    for root, dirs, files in os.walk(root_dir):
        if 'node_modules' in root or '.venv' in root or '__pycache__' in root:
            continue
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                path = os.path.join(root, file)
                lines = count_lines(path)
                if lines > 400:  # threshold
                    results.append((path, lines))
    return results

backend_files = scan_dir('backend', ['.py'])
frontend_files = scan_dir('frontend/src', ['.js', '.jsx', '.ts', '.tsx'])

backend_files.sort(key=lambda x: x[1], reverse=True)
frontend_files.sort(key=lambda x: x[1], reverse=True)


with open('monolithic_candidates.txt', 'w') as f:
    f.write("TOP BACKEND FILES:\n")
    for path, count in backend_files[:15]:
        f.write(f"{count}: {path}\n")

    f.write("\nTOP FRONTEND FILES:\n")
    for path, count in frontend_files[:15]:
        f.write(f"{count}: {path}\n")
