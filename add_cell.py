import json
import sys

notebook_path = sys.argv[1]
code_file_path = sys.argv[2]

with open(code_file_path, "r", encoding="utf-8") as f:
    code_to_add = f.read()

with open(notebook_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

new_cell = {
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": [line + "\n" for line in code_to_add.split("\n")]
}
# Remove the last newline from the last line to be clean
if new_cell["source"]:
    new_cell["source"][-1] = new_cell["source"][-1].rstrip("\n")

nb["cells"].append(new_cell)

with open(notebook_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print("Cell added successfully!")
