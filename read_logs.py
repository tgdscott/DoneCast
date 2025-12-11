import os

def read_file(path, out):
    out.write(f"\n--- Reading {path} ---\n")
    if not os.path.exists(path):
        out.write("File not found.\n")
        return
    
    content = ""
    try:
        # Try UTF-16 LE
        with open(path, 'r', encoding='utf-16-le') as f:
            content = f.read()
    except Exception:
        pass

    if not content:
        try:
             with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            out.write(f"Read failed: {e}\n")
            return

    out.write(content)

with open('final_log.txt', 'w', encoding='utf-8') as out:
    out.write(f"Current Directory: {os.getcwd()}\n")
    read_file('gcloud_output.txt', out)
    read_file('pip_output.txt', out)
    read_file('python_path.txt', out)
    read_file('pip_venv_output.txt', out)
    read_file('curl_test.txt', out)
    read_file('prod_test_output.txt', out)
    read_file('prod_debug_output.txt', out)
    read_file('cloud_run_logs.json', out)
    read_file('import_error_log.txt', out)
    read_file('deploy_output.txt', out)
    read_file('local_startup_test.txt', out)
    
print("Done writing final_log.txt")
