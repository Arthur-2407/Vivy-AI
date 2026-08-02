import os
import re

base_dir = r"d:\Vivy"
files_to_check = []
for root, dirs, files in os.walk(os.path.join(base_dir, "perception")):
    for file in files:
        if file.endswith(".py"):
            files_to_check.append(os.path.join(root, file))
files_to_check.append(os.path.join(base_dir, "web_server.py"))

for filepath in files_to_check:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines):
            # match * but exclude comments, docstrings, imports (from __future__ import annotations, etc.), and **
            clean_line = line.split("#")[0].strip()
            if not clean_line:
                continue
            if "*" in clean_line:
                # ignore **
                if "**" in clean_line:
                    # check if there's also a single *
                    # simple check: replace ** with empty and check if * is still there
                    temp = clean_line.replace("**", "")
                    if "*" not in temp:
                        continue
                # print filename, line number, content
                print(f"{os.path.relpath(filepath, base_dir)}:{idx+1}: {line.strip()}")
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
