"""Remove email nodes from n8n workflow JSON files."""
import os
import json

n8n_dir = r"G:\Meu Drive\IA\Canal Dark\canal-dark\n8n"

for filename in os.listdir(n8n_dir):
    if not filename.endswith('.json'):
        continue
    filepath = os.path.join(n8n_dir, filename)

    # Try UTF-8, then UTF-16
    for encoding in ['utf-8', 'utf-8-sig', 'utf-16']:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                data = json.load(f)
            print(f"Read {filename} with {encoding}")
            break
        except UnicodeDecodeError:
            continue

    # Remove email nodes
    original_nodes = len(data['nodes'])
    data['nodes'] = [n for n in data['nodes'] if n.get('type') != 'n8n-nodes-base.email']

    # Remove connections to email nodes
    nodes_removed = original_nodes - len(data['nodes'])
    if nodes_removed > 0:
        print(f"  Removed {nodes_removed} email node(s) from {filename}")

    for node_name in list(data['connections'].keys()):
        if any(x in node_name.lower() for x in ['email', 'notificar', 'e-mail']):
            del data['connections'][node_name]
            print(f"  Removed connection: {node_name}")

    # Save back
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {filename}")

print("\nDone! Please re-import the workflows into n8n.")
