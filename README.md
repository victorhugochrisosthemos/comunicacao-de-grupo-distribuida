# Sistemas Distribuídos — Trabalho M1

Projeto acadêmico desenvolvido para a disciplina de **Sistemas Distribuídos**, com foco em comunicação entre múltiplos nós, relógio vetorial, ordem total de mensagens, eleição de líder e captura de estado global.

## Objetivo

Implementar um sistema distribuído executado em múltiplos containers Docker, no qual cada nó possui estado próprio e se comunica exclusivamente pela rede.

A aplicação implementa:

- comunicação **unicast via TCP**;
- mensagens privadas entre nós;
- mensagens para todo o grupo;
- **relógio vetorial**;
- **ordem total** de mensagens por sequenciador;
- **eleição de líder pelo algoritmo Bully**;
- continuidade da sequência global após falha do líder;
- captura de **estado global**;
- interface interativa por terminal;
- execução configurável com **3, 8 ou 15 nós**.

## Estrutura do projeto

```text
M1/
├── app/
│   ├── main.py
│   └── nodes.json
├── abrir_15_nos.bat
├── docker-compose.yml
├── Dockerfile
├── gerar_nos.py
├── Relatorio_Trabalho1_Sistemas_Distribuidos.docx
└── README.md
```

### Arquivos principais

`app/main.py`  
Implementação do nó distribuído. Contém servidor TCP, comunicação entre nós, relógio vetorial, sequenciador, algoritmo Bully, snapshot e menu interativo.

`app/nodes.json`  
Catálogo estático dos nós, contendo ID, hostname e porta.

`gerar_nos.py`  
Gera automaticamente o `nodes.json` e o `docker-compose.yml` para a quantidade de nós informada.

`docker-compose.yml`  
Define os containers utilizados na simulação distribuída.

`Dockerfile`  
Cria a imagem Python utilizada por cada nó.

`abrir_15_nos.bat`  
Abre automaticamente terminais conectados aos 15 containers.

`Relatorio_Trabalho1_Sistemas_Distribuidos.docx`  
Relatório técnico do projeto.

## Tecnologias

- Python 3.12
- Docker
- Docker Compose
- TCP Sockets
- JSON
- Threads

## Arquitetura

Cada nó executa em um container Docker independente.

```text
Nó 1 ─┐
Nó 2 ─┤
Nó 3 ─┤
 ...   ├── TCP / Rede Docker
Nó N ─┘
```

Os nós são identificados por nomes como:

```text
node1
node2
node3
...
node15
```

Todos utilizam a porta interna `5000`.

## Ordem total

As mensagens de grupo são enviadas inicialmente ao nó líder, que atua como **sequenciador**.

Fluxo simplificado:

```text
Nó remetente
     |
     | GROUP_REQUEST
     v
Líder / Sequenciador
     |
     | atribui seq_global
     v
GROUP_DELIVERY
     |
     +----> Nó 1
     +----> Nó 2
     +----> ...
     +----> Nó N
```

Exemplo:

```text
Mensagem A -> seq = 1
Mensagem B -> seq = 2
Mensagem C -> seq = 3
```

Todos os nós armazenam as mensagens seguindo o mesmo número de sequência global.

## Relógio vetorial

Cada nó mantém um vetor com tamanho igual ao número total de nós.

Exemplo com 3 nós:

```text
Nó 1 envia:   [1, 0, 0]
Nó 2 recebe:  [1, 0, 0]
Nó 2 envia:   [1, 1, 0]
```

O vetor é utilizado para acompanhar relações de causalidade entre eventos.

## Eleição de líder — Bully

O maior ID ativo assume a liderança.

Exemplo com 3 nós:

```text
Líder inicial: Nó 3

Nó 3 falha
   |
   v
Nó 1 inicia eleição
Nó 2 responde
   |
   v
Novo líder: Nó 2
```

O novo líder continua a sequência global a partir do maior valor já conhecido.

## Estado global

O snapshot é coordenado pelo líder.

Cada nó informa:

- ID;
- relógio vetorial;
- líder atual;
- maior sequência global conhecida;
- ordem global;
- ordem local.

Nós indisponíveis são identificados durante a captura.

## Menu interativo

Cada nó apresenta:

```text
1 - Enviar mensagem privada
2 - Enviar mensagem para o grupo
3 - Mostrar relógio vetorial
4 - Mostrar ordem local
5 - Mostrar ordem global
6 - Capturar estado global
7 - Mostrar status do nó
8 - Iniciar eleição manualmente
0 - Sair
```

## Como executar

### Pré-requisitos

- Docker Desktop
- Docker Compose
- Python instalado no Windows, utilizado para gerar a configuração dos nós

### Executar com 3 nós

```bat
python gerar_nos.py 3
docker compose down --remove-orphans
docker compose up -d --build
docker compose ps
```

### Executar com 8 nós

```bat
python gerar_nos.py 8
docker compose down --remove-orphans
docker compose up -d --build
docker compose ps
```

### Executar com 15 nós

```bat
python gerar_nos.py 15
docker compose down --remove-orphans
docker compose up -d --build
docker compose ps
```

## Abrir um nó interativamente

Exemplo para o nó 1:

```bat
docker attach --sig-proxy=false m1-node1-1
```

Para o nó 2:

```bat
docker attach --sig-proxy=false m1-node2-1
```

Para o nó 15:

```bat
docker attach --sig-proxy=false m1-node15-1
```

Para sair do `docker attach` sem finalizar o container:

```text
Ctrl + P
Ctrl + Q
```

## Abrir os 15 nós

Após gerar e iniciar os 15 containers:

```bat
python gerar_nos.py 15
docker compose down --remove-orphans
docker compose up -d --build
```

Execute:

```bat
abrir_15_nos.bat
```

## Testes sugeridos

### Mensagem privada

No Nó 1:

```text
1
Destino: 2
Mensagem: teste privado
```

O Nó 2 deverá receber a mensagem.

### Mensagem de grupo

No Nó 1:

```text
2
Mensagem: teste grupo
```

Todos os nós deverão receber a mesma mensagem com o mesmo `seq`.

### Verificar ordem global

Escolha a opção:

```text
5
```

em diferentes nós. A ordem exibida deve ser idêntica.

### Simular falha do líder

Com 15 nós, o líder inicial é o Nó 15:

```bat
docker stop m1-node15-1
```

O algoritmo Bully deverá eleger o Nó 14 como novo líder.

Com 3 nós:

```bat
docker stop m1-node3-1
```

O Nó 2 deverá assumir a liderança.

## Escalabilidade

A quantidade de nós é definida sem alteração do código principal:

```bat
python gerar_nos.py <quantidade>
```

Exemplos:

```bat
python gerar_nos.py 3
python gerar_nos.py 8
python gerar_nos.py 15
```

## Limitações

- o sequenciador representa um ponto crítico até a conclusão da eleição de um novo líder;
- a captura de estado global utilizada é centralizada;
- não há persistência das mensagens após a destruição dos containers;
- a implementação foi projetada para fins acadêmicos e de simulação.

## Autores

Preencher com os integrantes da equipe.

## Disciplina

**Sistemas Distribuídos — UNIVALI**
