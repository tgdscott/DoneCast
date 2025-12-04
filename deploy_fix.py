import subprocess
import sys
import os

def run_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        print(e.stderr)
        sys.exit(1)

def main():
    print("==> Deploying Podcast Website Routing Fixes (Python Version)")
    print("")

    project_id = "podcast612"
    region = "us-west1"

    # Step 1: Get API Service URL
    print("[1/3] Fetching API Service URL...")
    try:
        cmd = f"gcloud run services describe podcast-api --region={region} --project={project_id} --format=\"value(status.url)\""
        api_url = run_command(cmd)
        api_host = api_url.replace("https://", "")
        print(f"Found API URL: {api_url}")
    except Exception as e:
        print("Failed to fetch API URL. Make sure you are logged in to gcloud.")
        sys.exit(1)

    # Step 2: Update nginx.conf
    print("[2/3] Configuring Frontend Proxy...")
    
    nginx_content = f"""server {{
  listen 8080;
  server_name _;
  root /usr/share/nginx/html;
  index index.html;

  # Proxy RSS feeds to the backend API
  location /rss/ {{
    resolver 8.8.8.8;
    proxy_pass {api_url};
    proxy_ssl_server_name on;
    proxy_set_header Host {api_host};
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }}

  # SPA fallback
  location / {{
    try_files $uri /index.html;
  }}
}}
"""
    
    nginx_path = os.path.join("frontend", "nginx.conf")
    with open(nginx_path, "w", encoding="utf-8") as f:
        f.write(nginx_content)
    
    print(f"Updated {nginx_path} to proxy to {api_host}")
    print("")

    # Step 3: Wildcard Domain Mapping
    print("[3/3] Checking Wildcard Domain Mapping...")
    choice = input("Create wildcard domain mapping? (y/n): ").lower()
    if choice == 'y':
        try:
            cmd = f"gcloud beta run domain-mappings create --service=podcast-web --domain=\"*.podcastplusplus.com\" --region={region} --project={project_id} --quiet"
            subprocess.run(cmd, shell=True, check=True)
            print("Wildcard domain mapping created.")
        except subprocess.CalledProcessError:
            print("Note: Domain mapping might already exist.")
    
    print("")

    # Step 4: Deploy
    choice = input("Deploy updated frontend? (y/n): ").lower()
    if choice == 'y':
        print("Triggering Cloud Build...")
        subprocess.run(f"gcloud builds submit --config=cloudbuild.yaml --project={project_id}", shell=True)

    print("")
    print("Done!")
    print("1. RSS Feed should work IMMEDIATELY after deployment.")
    print("2. Subdomains (*.podcastplusplus.com) will take 10-15 mins for SSL.")

def debug_mode():
    print("==> Debugging Subdomain Connection")
    import socket
    
    domain = "cardiac-cowboys.podcastplusplus.com"
    print(f"Checking DNS for {domain}...")
    try:
        ip = socket.gethostbyname(domain)
        print(f"DNS Resolution: {domain} -> {ip}")
    except Exception as e:
        print(f"DNS Resolution FAILED: {e}")

    print("\nChecking Cloud Run Domain Mapping...")
    try:
        cmd = 'gcloud beta run domain-mappings describe --domain="*.podcastplusplus.com" --region=us-west1 --project=podcast612 --format="value(status.resourceRecords)"'
        subprocess.run(cmd, shell=True)
    except Exception as e:
        print(f"Mapping check failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        debug_mode()
    else:
        main()
