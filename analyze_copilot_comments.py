import json

# Load the Copilot comments
with open('pr201_comments_formatted.json', encoding='utf-8-sig') as f:
    comments = json.load(f)

print(f"Total Copilot Comments: {len(comments)}\n")
print("=" * 80)

# Categorize comments
categories = {
    "unused_variable": [],
    "unreachable_code": [],
    "empty_except": [],
    "redundant_condition": [],
    "parameter_not_used": [],
    "simplification": [],
    "other": []
}

for i, comment in enumerate(comments, 1):
    body = comment['body']
    path = comment['path']
    line = comment.get('line', comment.get('original_line', '?'))
    
    # Categorize by keyword
    if "not used" in body.lower() or "never used" in body.lower():
        categories["unused_variable"].append((i, path, line, body[:150]))
    elif "unreachable" in body.lower():
        categories["unreachable_code"].append((i, path, line, body[:150]))
    elif "except" in body.lower() and ("pass" in body.lower() or "does nothing" in body.lower()):
        categories["empty_except"].append((i, path, line, body[:150]))
    elif "redundant" in body.lower() or "always" in body.lower():
        categories["redundant_condition"].append((i, path, line, body[:150]))
    elif "parameter" in body.lower() and ("not used" in body.lower() or "never used" in body.lower()):
        categories["parameter_not_used"].append((i, path, line, body[:150]))
    elif "simplif" in body.lower() or "could be" in body.lower():
        categories["simplification"].append((i, path, line, body[:150]))
    else:
        categories["other"].append((i, path, line, body[:150]))

# Print summary
print("\nCATEGORY SUMMARY:")
print("-" * 80)
for cat_name, items in categories.items():
    if items:
        print(f"{cat_name.replace('_', ' ').title()}: {len(items)}")

print("\n" + "=" * 80)
print("\nDETAILED BREAKDOWN:")
print("=" * 80)

for cat_name, items in categories.items():
    if not items:
        continue
    print(f"\n### {cat_name.replace('_', ' ').upper()} ({len(items)} comments) ###")
    print("-" * 80)
    for num, path, line, body_preview in items:
        file_name = path.split('/')[-1]
        print(f"\n{num}. {file_name}:{line}")
        print(f"   {body_preview}...")
