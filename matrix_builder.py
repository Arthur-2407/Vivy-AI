import os
import ast
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def build_ast_dependency_graph():
    graph = {}
    for root, _, files in os.walk(BASE_DIR):
        if any(p in root for p in ["venv", ".git", "__pycache__", ".pytest_cache", "tmp"]):
            continue
        for f in files:
            if f.endswith(".py"):
                path = os.path.relpath(os.path.join(root, f), BASE_DIR)
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as file:
                        tree = ast.parse(file.read(), filename=full_path)
                    
                    imports = []
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for n in node.names:
                                imports.append(n.name)
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                imports.append(node.module)
                                
                    graph[path.replace("\\", "/")] = list(set(imports))
                except Exception:
                    pass
    return graph

def main():
    graph = build_ast_dependency_graph()
    out_path = os.path.join(BASE_DIR, "Reports", "static_dependency_graph.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
    print(f"Static dependency graph written to {out_path}")

if __name__ == "__main__":
    main()
