import os
import sys
import ast
import re

def get_imports_from_file(filepath):
    imports = set()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content, filename=filepath)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    imports.add(node.module.split('.')[0])
    except Exception as e:
        # Silently skip files that fail to parse (e.g., syntax errors)
        pass
    return imports

def main():
    print("Scanning project for imports...")
    src_dir = "MSK_core"
    used_modules = set()
    for root, _, files in os.walk(src_dir):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                used_modules.update(get_imports_from_file(filepath))
                
    for file in ["main.py", "gui_main.py"]:
        if os.path.exists(file):
            used_modules.update(get_imports_from_file(file))

    exe_path = "exe.py"
    if not os.path.exists(exe_path):
        print("[X] exe.py not found.")
        return

    with open(exe_path, 'r', encoding='utf-8') as f:
        exe_content = f.read()

    def extract_list(var_name):
        match = re.search(f"{var_name}\s*=\s*\\[(.*?)\\]", exe_content, re.DOTALL)
        if match:
            # find all strings inside the list (including tuples)
            items = re.findall(r"['\"]([a-zA-Z0-9_\-\.]+)['\"]", match.group(1))
            return [i.split('.')[0].replace('-', '_') for i in items]
        return []

    req_pkgs = extract_list("REQUIRED_PACKAGES")
    inc_pkgs = extract_list("INCLUDE_PACKAGES")
    inc_mods = extract_list("INCLUDE_MODULES")

    exe_modules = set()
    exe_modules.update(req_pkgs)
    exe_modules.update(inc_pkgs)
    exe_modules.update(inc_mods)

    # Standard library modules
    stdlib = set(sys.builtin_module_names)
    if hasattr(sys, 'stdlib_module_names'):
        stdlib.update(sys.stdlib_module_names)

    missing = []
    # Internal packages/files
    ignore = {'MSK_core', 'main', 'gui_main', 'exe'}

    for mod in used_modules:
        mod_root = mod.split('.')[0]
        if mod_root in stdlib or mod_root in ignore or mod_root.startswith('_'):
            continue
        
        if mod_root not in exe_modules:
            missing.append(mod_root)

    print("-" * 50)
    if missing:
        print("[!] STATUS: exe.py is OUTDATED!")
        print("The following modules are used in the source code but NOT found in exe.py:")
        for m in sorted(set(missing)):
            print(f"  - {m}")
        print("\nPlease update REQUIRED_PACKAGES, INCLUDE_PACKAGES, or INCLUDE_MODULES in exe.py.")
    else:
        print("[+] STATUS: exe.py is UP TO DATE!")
        print("All imported external modules seem to be accounted for in exe.py.")

if __name__ == "__main__":
    main()
