import os
import socket
import threading
import time
import json


# ============================================================
# CONFIGURAÇÃO
# ============================================================

NODE_ID = int(os.getenv("NODE_ID", "0"))

with open("nodes.json", "r", encoding="utf-8") as arquivo:
    CONFIG = json.load(arquivo)

NOS = CONFIG["nos"]
N = len(NOS)

MEU_NO = next(no for no in NOS if no["id"] == NODE_ID)
PORT = MEU_NO["porta"]

# Inicialmente o maior ID é o sequenciador.
lider_id = max(no["id"] for no in NOS)


# ============================================================
# ESTADO LOCAL
# ============================================================

vetor = [0] * N
seq_global = 0

ordem_global = []
ordem_local = []

contador_local = 0

state_lock = threading.Lock()
local_lock = threading.Lock()

em_eleicao = False
election_lock = threading.Lock()

snapshot_lock = threading.Lock()
snapshot_respostas = {}


# ============================================================
# UTILITÁRIOS
# ============================================================

def buscar_no(node_id):
    return next(
        (no for no in NOS if no["id"] == node_id),
        None
    )


def registrar_evento_local(tipo, descricao):
    global contador_local

    with local_lock:
        contador_local += 1

        evento = {
            "ordem": contador_local,
            "tipo": tipo,
            "descricao": descricao
        }

        ordem_local.append(evento)


def receber_dados(conn):
    partes = []

    while True:
        dados = conn.recv(4096)

        if not dados:
            break

        partes.append(dados)

    return b"".join(partes)


def enviar(no_destino, mensagem, timeout=1):
    if no_destino is None:
        return False

    try:
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        ) as sock:

            sock.settimeout(timeout)

            sock.connect(
                (
                    no_destino["host"],
                    no_destino["porta"]
                )
            )

            dados = json.dumps(
                mensagem
            ).encode("utf-8")

            sock.sendall(dados)

        return True

    except (
        ConnectionRefusedError,
        socket.timeout,
        socket.gaierror,
        OSError
    ):
        return False


def broadcast_rede(mensagem):
    for no in NOS:
        enviar(no, mensagem)


# ============================================================
# RELÓGIO VETORIAL
# ============================================================

def incrementar_relogio():
    with state_lock:
        vetor[NODE_ID - 1] += 1
        return vetor.copy()


def atualizar_vetor(vetor_recebido):
    if vetor_recebido is None:
        return

    with state_lock:
        for i in range(N):
            vetor[i] = max(
                vetor[i],
                vetor_recebido[i]
            )


# ============================================================
# MENSAGEM PRIVADA
# ============================================================

def enviar_privada(destino_id, payload):
    destino = buscar_no(destino_id)

    if destino is None:
        print("Nó de destino inexistente.")
        return

    vetor_envio = incrementar_relogio()

    mensagem = {
        "tipo": "PRIVATE",
        "origem": NODE_ID,
        "destino": destino_id,
        "vetor": vetor_envio,
        "payload": payload
    }

    sucesso = enviar(
        destino,
        mensagem
    )

    if sucesso:
        registrar_evento_local(
            "ENVIO_PRIVADO",
            f"Para nó {destino_id}: {payload}"
        )

        print()
        print(
            f"[Nó {NODE_ID}] Mensagem privada enviada "
            f"para nó {destino_id}."
        )
        print(
            f"[Nó {NODE_ID}] Vetor: {vetor_envio}"
        )

    else:
        print(
            f"[Nó {NODE_ID}] "
            f"Não foi possível acessar o nó {destino_id}."
        )


def receber_privada(mensagem):
    atualizar_vetor(
        mensagem["vetor"]
    )

    registrar_evento_local(
        "RECEBIMENTO_PRIVADO",
        (
            f"Do nó {mensagem['origem']}: "
            f"{mensagem['payload']}"
        )
    )

    print()
    print("=" * 60)
    print(
        f"[PRIVADA] Nó {mensagem['origem']} -> Nó {NODE_ID}"
    )
    print(
        f"Mensagem: {mensagem['payload']}"
    )
    print(
        f"Vetor recebido: {mensagem['vetor']}"
    )
    print(
        f"Vetor local: {vetor}"
    )
    print("=" * 60)


# ============================================================
# ORDEM TOTAL
# ============================================================

def solicitar_mensagem_grupo(payload):
    global lider_id

    vetor_envio = incrementar_relogio()

    mensagem = {
        "tipo": "GROUP_REQUEST",
        "origem": NODE_ID,
        "vetor": vetor_envio,
        "payload": payload
    }

    lider = buscar_no(lider_id)

    sucesso = enviar(
        lider,
        mensagem
    )

    if sucesso:
        registrar_evento_local(
            "ENVIO_GRUPO",
            payload
        )

        print(
            f"[Nó {NODE_ID}] "
            f"Mensagem enviada ao sequenciador {lider_id}."
        )

    else:
        print(
            f"[Nó {NODE_ID}] "
            f"Líder {lider_id} não respondeu."
        )

        iniciar_eleicao()

        print(
            "A eleição foi iniciada. "
            "Envie novamente após o novo líder ser anunciado."
        )


def processar_como_lider(mensagem):
    global seq_global

    with state_lock:
        seq_global += 1
        seq = seq_global

    mensagem_ordenada = {
        "tipo": "GROUP_DELIVERY",
        "origem": mensagem["origem"],
        "vetor": mensagem["vetor"],
        "seq": seq,
        "payload": mensagem["payload"]
    }

    print()
    print(
        f"[LÍDER {NODE_ID}] "
        f"seq={seq} atribuído à mensagem "
        f"do nó {mensagem['origem']}"
    )

    broadcast_rede(
        mensagem_ordenada
    )


def entregar_mensagem(mensagem):
    global seq_global

    atualizar_vetor(
        mensagem["vetor"]
    )

    with state_lock:
        seq_global = max(
            seq_global,
            mensagem["seq"]
        )

        # Evita duplicação.
        if any(
            item["seq"] == mensagem["seq"]
            for item in ordem_global
        ):
            return

        ordem_global.append({
            "seq": mensagem["seq"],
            "origem": mensagem["origem"],
            "payload": mensagem["payload"]
        })

        ordem_global.sort(
            key=lambda item: item["seq"]
        )

    registrar_evento_local(
        "ENTREGA_GLOBAL",
        (
            f"#{mensagem['seq']} "
            f"nó {mensagem['origem']}: "
            f"{mensagem['payload']}"
        )
    )

    print()
    print("=" * 60)
    print(
        f"[GRUPO #{mensagem['seq']}] "
        f"Nó {mensagem['origem']}: "
        f"{mensagem['payload']}"
    )
    print("=" * 60)


# ============================================================
# ALGORITMO BULLY
# ============================================================

def anunciar_coordenador():
    global lider_id
    global em_eleicao

    lider_id = NODE_ID

    with election_lock:
        em_eleicao = False

    print()
    print("=" * 60)
    print(
        f"[ELEIÇÃO] NÓ {NODE_ID} É O NOVO LÍDER"
    )
    print(
        f"[ELEIÇÃO] Próxima sequência global: "
        f"{seq_global + 1}"
    )
    print("=" * 60)

    registrar_evento_local(
        "ELEICAO",
        f"Nó {NODE_ID} tornou-se líder"
    )

    mensagem = {
        "tipo": "COORDINATOR",
        "origem": NODE_ID
    }

    for no in NOS:
        if no["id"] != NODE_ID:
            enviar(no, mensagem)


def aguardar_coordenador():
    global em_eleicao

    time.sleep(4)

    iniciar_novamente = False

    with election_lock:
        if em_eleicao:
            em_eleicao = False
            iniciar_novamente = True

    if iniciar_novamente:
        print(
            f"[Nó {NODE_ID}] "
            "Coordenador não foi anunciado. "
            "Reiniciando eleição."
        )

        iniciar_eleicao()


def iniciar_eleicao():
    global em_eleicao

    with election_lock:
        if em_eleicao:
            return

        em_eleicao = True

    print()
    print(
        f"[Nó {NODE_ID}] Iniciando eleição Bully..."
    )

    registrar_evento_local(
        "ELEICAO",
        "Eleição iniciada"
    )

    nos_maiores = [
        no
        for no in NOS
        if no["id"] > NODE_ID
    ]

    encontrou_maior = False

    for no in nos_maiores:
        mensagem = {
            "tipo": "ELECTION",
            "origem": NODE_ID
        }

        if enviar(no, mensagem):
            encontrou_maior = True

            print(
                f"[Nó {NODE_ID}] "
                f"ELECTION entregue ao nó {no['id']}."
            )

    if not encontrou_maior:
        anunciar_coordenador()

    else:
        threading.Thread(
            target=aguardar_coordenador,
            daemon=True
        ).start()


def monitorar_lider():
    global lider_id

    time.sleep(3)

    while True:
        time.sleep(3)

        if lider_id == NODE_ID:
            continue

        lider = buscar_no(
            lider_id
        )

        mensagem = {
            "tipo": "PING",
            "origem": NODE_ID
        }

        if not enviar(
            lider,
            mensagem,
            timeout=1
        ):
            print()
            print(
                f"[Nó {NODE_ID}] "
                f"Falha detectada no líder {lider_id}."
            )

            iniciar_eleicao()


# ============================================================
# SNAPSHOT
# ============================================================

def obter_estado_local():
    with state_lock:
        estado = {
            "node_id": NODE_ID,
            "vetor": vetor.copy(),
            "seq_global": seq_global,
            "lider": lider_id,
            "ordem_global": ordem_global.copy()
        }

    with local_lock:
        estado["ordem_local"] = ordem_local.copy()

    return estado


def iniciar_snapshot():
    global snapshot_respostas

    if NODE_ID != lider_id:
        print(
            f"[Nó {NODE_ID}] "
            f"Solicitando snapshot ao líder {lider_id}..."
        )

        lider = buscar_no(
            lider_id
        )

        enviar(
            lider,
            {
                "tipo": "SNAPSHOT_TRIGGER",
                "origem": NODE_ID
            }
        )

        return

    with snapshot_lock:
        snapshot_respostas = {}

    print()
    print("=" * 60)
    print("[SNAPSHOT] Capturando estado global...")
    print("=" * 60)

    mensagem = {
        "tipo": "SNAPSHOT_REQUEST",
        "origem": NODE_ID
    }

    for no in NOS:
        enviar(no, mensagem)

    # Espera respostas sem travar indefinidamente.
    limite = time.time() + 3

    while time.time() < limite:
        with snapshot_lock:
            if len(snapshot_respostas) >= N:
                break

        time.sleep(0.1)

    mostrar_snapshot()


def mostrar_snapshot():
    print()
    print("=" * 60)
    print("ESTADO GLOBAL")
    print("=" * 60)

    with snapshot_lock:
        respostas = snapshot_respostas.copy()

    for no in NOS:
        estado = respostas.get(
            no["id"]
        )

        if estado is None:
            print()
            print(
                f"Nó {no['id']}: INDISPONÍVEL"
            )
            continue

        ordem = [
            (item["seq"], item["origem"])
            for item in estado["ordem_global"]
        ]

        print()
        print(f"Nó {no['id']}:")
        print(
            f"  líder: {estado['lider']}"
        )
        print(
            f"  vetor: {estado['vetor']}"
        )
        print(
            f"  seq_global: {estado['seq_global']}"
        )
        print(
            f"  ordem_global: {ordem}"
        )
        print(
            f"  eventos locais: "
            f"{len(estado['ordem_local'])}"
        )

    print()
    print("=" * 60)


# ============================================================
# PROCESSAMENTO DE MENSAGENS
# ============================================================

def processar_mensagem(mensagem):
    global lider_id
    global em_eleicao

    tipo = mensagem.get("tipo")

    if tipo == "PRIVATE":
        receber_privada(
            mensagem
        )

    elif tipo == "GROUP_REQUEST":
        if NODE_ID == lider_id:
            processar_como_lider(
                mensagem
            )

    elif tipo == "GROUP_DELIVERY":
        entregar_mensagem(
            mensagem
        )

    elif tipo == "PING":
        pass

    elif tipo == "ELECTION":
        origem = mensagem["origem"]

        print(
            f"[Nó {NODE_ID}] "
            f"Recebeu ELECTION do nó {origem}."
        )

        if NODE_ID > origem:
            resposta = {
                "tipo": "OK",
                "origem": NODE_ID
            }

            enviar(
                buscar_no(origem),
                resposta
            )

            threading.Thread(
                target=iniciar_eleicao,
                daemon=True
            ).start()

    elif tipo == "OK":
        print(
            f"[Nó {NODE_ID}] "
            f"Recebeu OK do nó "
            f"{mensagem['origem']}."
        )

    elif tipo == "COORDINATOR":
        lider_id = mensagem["origem"]

        with election_lock:
            em_eleicao = False

        registrar_evento_local(
            "ELEICAO",
            f"Novo líder = {lider_id}"
        )

        print()
        print("=" * 60)
        print(
            f"[Nó {NODE_ID}] "
            f"NOVO LÍDER = {lider_id}"
        )
        print("=" * 60)

    elif tipo == "SNAPSHOT_TRIGGER":
        if NODE_ID == lider_id:
            threading.Thread(
                target=iniciar_snapshot,
                daemon=True
            ).start()

    elif tipo == "SNAPSHOT_REQUEST":
        estado = obter_estado_local()

        resposta = {
            "tipo": "SNAPSHOT_STATE",
            "origem": NODE_ID,
            "estado": estado
        }

        enviar(
            buscar_no(
                mensagem["origem"]
            ),
            resposta
        )

    elif tipo == "SNAPSHOT_STATE":
        with snapshot_lock:
            snapshot_respostas[
                mensagem["origem"]
            ] = mensagem["estado"]


# ============================================================
# SERVIDOR TCP
# ============================================================

def servidor():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    sock.bind(
        ("0.0.0.0", PORT)
    )

    sock.listen()

    print(
        f"[Nó {NODE_ID}] "
        f"Servidor TCP ativo na porta {PORT}"
    )

    while True:
        conn, _ = sock.accept()

        with conn:
            dados = receber_dados(
                conn
            )

        if not dados:
            continue

        try:
            mensagem = json.loads(
                dados.decode("utf-8")
            )

            processar_mensagem(
                mensagem
            )

        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            KeyError
        ) as erro:
            print(
                f"[Nó {NODE_ID}] "
                f"Mensagem inválida: {erro}"
            )


# ============================================================
# EXIBIÇÃO
# ============================================================

def mostrar_relogio():
    with state_lock:
        copia = vetor.copy()

    print()
    print(
        f"Relógio vetorial do nó {NODE_ID}: {copia}"
    )


def mostrar_ordem_global():
    with state_lock:
        copia = ordem_global.copy()

    print()
    print("=" * 60)
    print("ORDEM GLOBAL")

    if not copia:
        print("Nenhuma mensagem entregue.")

    for item in copia:
        print(
            f"#{item['seq']} | "
            f"Nó {item['origem']} | "
            f"{item['payload']}"
        )

    print("=" * 60)


def mostrar_ordem_local():
    with local_lock:
        copia = ordem_local.copy()

    print()
    print("=" * 60)
    print(f"ORDEM LOCAL DO NÓ {NODE_ID}")

    if not copia:
        print("Nenhum evento registrado.")

    for evento in copia:
        print(
            f"{evento['ordem']:03d} | "
            f"{evento['tipo']} | "
            f"{evento['descricao']}"
        )

    print("=" * 60)


def mostrar_status():
    with state_lock:
        vetor_atual = vetor.copy()
        seq_atual = seq_global

    print()
    print("=" * 60)
    print(f"Nó: {NODE_ID}")
    print(f"Líder atual: {lider_id}")
    print(f"Sou líder: {'SIM' if NODE_ID == lider_id else 'NÃO'}")
    print(f"Relógio vetorial: {vetor_atual}")
    print(f"Maior sequência conhecida: {seq_atual}")
    print(f"Número de nós configurados: {N}")
    print("=" * 60)


# ============================================================
# MENU
# ============================================================

def menu():
    while True:
        print()
        print("=" * 60)
        print(f"        SISTEMA DISTRIBUÍDO - NÓ {NODE_ID}")
        print("=" * 60)
        print("1 - Enviar mensagem privada")
        print("2 - Enviar mensagem para o grupo")
        print("3 - Mostrar relógio vetorial")
        print("4 - Mostrar ordem local")
        print("5 - Mostrar ordem global")
        print("6 - Capturar estado global")
        print("7 - Mostrar status do nó")
        print("8 - Iniciar eleição manualmente")
        print("0 - Sair")
        print("=" * 60)

        try:
            opcao = input("Escolha: ").strip()

        except EOFError:
            time.sleep(1)
            continue

        if opcao == "1":
            try:
                destino = int(
                    input("ID do nó destino: ")
                )

                texto = input(
                    "Mensagem: "
                ).strip()

                if texto:
                    enviar_privada(
                        destino,
                        texto
                    )

            except ValueError:
                print("ID inválido.")

        elif opcao == "2":
            texto = input(
                "Mensagem para o grupo: "
            ).strip()

            if texto:
                solicitar_mensagem_grupo(
                    texto
                )

        elif opcao == "3":
            mostrar_relogio()

        elif opcao == "4":
            mostrar_ordem_local()

        elif opcao == "5":
            mostrar_ordem_global()

        elif opcao == "6":
            iniciar_snapshot()

        elif opcao == "7":
            mostrar_status()

        elif opcao == "8":
            iniciar_eleicao()

        elif opcao == "0":
            print(
                f"Encerrando nó {NODE_ID}..."
            )
            os._exit(0)

        else:
            print("Opção inválida.")


# ============================================================
# INICIALIZAÇÃO
# ============================================================

threading.Thread(
    target=servidor,
    daemon=True
).start()

threading.Thread(
    target=monitorar_lider,
    daemon=True
).start()

print()
print("=" * 60)
print(f"NÓ {NODE_ID} INICIADO")
print(f"Líder inicial: {lider_id}")
print(f"Relógio vetorial: {vetor}")
print(f"Número de nós: {N}")
print("=" * 60)

menu()