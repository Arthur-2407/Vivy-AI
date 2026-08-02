with open('D:/Vivy/animation_authoring_pipeline.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

lines.insert(460, '                        print(f"DEBUG: f_count={f_count}, last_f_count={last_f_count}, size={size}")\n')

with open('D:/Vivy/animation_authoring_pipeline.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
