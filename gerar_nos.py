import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"
COMPOSE_FILE = BASE_DIR / "docker-compose.yml"
NODES_FILE = APP_DIR / "nodes.json"


if len(sys.argv) != 2:
    print("Uso: python gerar_nos.py <quantidade>")
    sys.exit(1)

try:
    quantidade = int(sys.argv[1])
except ValueError:
    print("A quantidade precisa ser um número inteiro.")
    sys.exit(1)

if quantidade < 1:
    print("A quantidade precisa ser maior que zero.")
    sys.exit(1)


# ============================================================
# nodes.json
# ============================================================

config = {
    "nos": [
        {
            "id": i,
            "host": f"node{i}",
            "porta": 5000
        }
        for i in range(1, quantidade + 1)
    ]
}

APP_DIR.mkdir(exist_ok=True)

with open(NODES_FILE, "w", encoding="utf-8") as arquivo:
    json.dump(
        config,
        arquivo,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# docker-compose.yml
# ============================================================

linhas = ["services:"]

for i in range(1, quantidade + 1):
    linhas.extend([
        f"  node{i}:",
        "    build: .",
        "    environment:",
        f"      NODE_ID: {i}",
        "    stdin_open: true",
        "    tty: true",
        ""
    ])

with open(COMPOSE_FILE, "w", encoding="utf-8") as arquivo:
    arquivo.write("\n".join(linhas))


print("=" * 50)
print(f"{quantidade} nós configurados.")
print(f"nodes.json: {NODES_FILE}")
print(f"docker-compose.yml: {COMPOSE_FILE}")
print("=" * 50)