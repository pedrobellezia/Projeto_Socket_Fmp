# Agente
Foram utilizadas as seguintes biliotecas:

- zlib
- json
- subprocess
- socket
- time
- re

---

```python
IPS_PERMITIDOS = [
    '192.168.0.10',
    '192.168.0.20',
    '127.0.0.1'
]

PORTA = 9999
BUFFER_SIZE = 2048
IP_LIMIT = 3
SEC_INTERVAL = 60
acessos_por_ip = {}
```

- **IPS_PERMITIDOS**: IPs com permissão para enviar pacotes para o socket
- **BUFFER_SIZE**: limite de bytes que cada pacote pode ter (caso o pacote exceda esse limite o script irá receber apenas os primeiros `{BUFFER_SIZE}` Bytes)
- **acessos_por_ip**, **IP_LIMIT**, **SEC_INTERVAL**: Define quantos pacotes podem ser enviados pelo mesmo IP numa certa quantidade de tempo antes de ser bloqueado
- **PORTA**: Define qual porta o socket irá escutar

---

```python
def get_serial_number():
    data = subprocess.check_output('wmic bios get serialnumber').decode("utf-8")
    serial_number = re.search(r'SerialNumber\s+[\r\n]+([A-Z0-9]+)', data)
    return serial_number.group(1) if serial_number else None
```

Utilizo a biblioteca `subprocess` para obter o número de série do computador.  
Como `wmic bios get serialnumber` não retorna o número de série diretamente, eu uso a biblioteca de regex para limpar a string e pegar apenas o número de série.

---

```python
def processar_pacote(data: bytes, addr: str):
    serial_number = get_serial_number()
    resultado = json.loads(zlib.decompress(data).decode('utf-8'))
    
    mensagem = resultado.get('data_package')
    if mensagem:
        print(mensagem)
        response = 'Mensagem recebida com sucesso'
    else:
        response = "Mensagem não foi recebida"
    
    resposta = {
        'sent_id': resultado.get('sent_id'),
        'response': response,
        'serial_number': serial_number
    }

    return zlib.compress(json.dumps(resposta).encode('utf-8'))
```

Chama a função `get_serial_number` para obter o número de série e processa o pacote recebido.  
Como o pacote de dados é comprimido com zlib, eu descomprimo ele, converto de bytes para string, e finalmente converto de string para json com `json.loads`.

Essa função retorna um pacote de dados a ser enviado de volta para o servidor contendo informações que serão adicionadas ao banco de dados.

---

```python
def servidor_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORTA))
    print(f"Servidor escutando na porta {PORTA}")
    while True:
        try:
            data, (ip, port) = sock.recvfrom(BUFFER_SIZE)
            if ip not int IPS_PERMITIDOS:
                continue

            agora = time.time()
            if ip not in acessos_por_ip:
                acessos_por_ip[ip] = []
            
            
            fila[:] = acessos_por_ip[ip]
            acessos_por_ip[ip] = [t for t in fila if agora - t <= SEC_INTERVAL]

            if len(fila) < IP_LIMIT:
                fila.append(agora)                
                if data:
                    new_data = processar_pacote(data, ip)
                    sock.sendto(new_data, (ip, port))
                else:
                    print(f"Pacote vazio recebido de {ip}")                
            else:
                print(f"Limite de requisições atingido para {ip}")
        except Exception as e:
            print(f"Erro no servidor: {e}")
```

Utilizando `socket.socket()`, abro um socket com as configurações `AF_INET` e `SOCK_DGRAM`:

AF_INET: Indica que o socket utilizará o protocolo IPv4.

SOCK_DGRAM: Indica que o socket será do tipo UDP.

Com `sock.bind`, associo o socket a qualquer IP disponível na máquina onde este script está rodando, na porta especificada.

O código entra em modo de espera ao chegar na linha `sock.recvfrom(BUFFER_SIZE)`, aguardando o recebimento de algum pacote.

Ao receber um pacote, o script realiza algumas validações para decidir se o pacote será processado ou não:

1. Primeiro, verifica se o IP ultrapassou o limite de envios.
2. Em seguida, checa se o pacote está vazio ou não.

ao final ele processa o pacote e envia de volta para o servidor

---

# Servidor 
Este Script utiliza as bibliotecas 

- `zlib`
- `json`
- `asyncio`
- `socket`
- `threading`
- `os` 

## Funcionamento da classe UDPClient

```python
class UDPClient:
    def __init__(self, porta: int = 9999, porta_local: int = 9998) -> None:
        self.fila = asyncio.Queue()  # Fila de pacotes recebidos
        self.porta = porta  # Porta de destino dos pacotes enviados
        self.porta_local = porta_local  # Porta local para recener pacotes
        self.sock = None  # Socket UDP
        self.worker_task = None  # Tarefa assíncrona de processamento de pacotes(Instância da classe Asyncio.Task)
        self.loop = asyncio.new_event_loop()  # Event loop exclusivo para esta instância(Instância da classe AbstractEventLoop)

    def start_loop(self):
        asyncio.set_event_loop(self.loop)  # Define o event loop na thread atual
        self.loop.run_forever()  # Mantém o event loop rodando

    async def open_socket(self) -> None:
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Cria socket UDP
            self.sock.bind(("", self.porta_local))  # Escuta em qualquer IP na porta local
            self.sock.settimeout(5)  # Timeout de 5 segundos para receber pacotes, levanta um erro quando passar desses 5 segundos

            # Inicia o event loop em uma thread separada, se não estiver rodando
            if not self.loop.is_running():
                threading.Thread(target=self.start_loop, daemon=True).start()

            # Utiliza da thread responsável pelo self.loop para executar data_worker()
            self.worker_task = asyncio.run_coroutine_threadsafe(self.data_worker(), self.loop)
            # Cria uma thread para receber pacotes
            threading.Thread(target=self.ouvir_respostas, daemon=True).start()

    async def close_socket(self) -> None:
        # Fecha o socket e cancela a tarefa de processamento
        # Ao fechar o socket, a thread responsável por escutar as respostas é encerrada. Já a thread do event loop self.loop permanece ativa, mas seu consumo é mínimo, pois não está executando nenhuma tarefa.
        if self.sock:
            self.sock.close()
            self.sock = None
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

    async def data_worker(self):
        # Processa pacotes da fila, um por vez, de forma assíncrona
        while True:
            data, addr = await self.fila.get()
            await self.work(data, addr)
            self.fila.task_done()
    
    @staticmethod
    async def work(data, addr):
        # Descomprime, decodifica e processa o pacote recebido
        resultado = json.loads(zlib.decompress(data).decode("utf-8"))
        sent_id = resultado.pop("sent_id")
        computer_serial = resultado["serial_number"]
        response = resultado.pop("response")
        resultado["ip"] = addr
        db.check_pc(resultado) # Checa as informações do computador no banco de dados
        db.task_recv(response=response, sent_id=sent_id, computer_id=computer_serial) # adiciona as informações ao banco de dados

    def ouvir_respostas(self) -> None:
        # Escuta pacotes UDP e coloca na fila para processamento 
        while self.sock:
            try:
                data, addr = self.sock.recvfrom(2048)
                asyncio.run_coroutine_threadsafe(
                    self.fila.put((data, addr[0])), self.loop
                )
            except socket.timeout:
                continue
            except OSError:
                break

    async def enviar_pacote(
        self, ip_string: str, task_id: str, usuario_id: str
    ) -> None:
        # 
        ip_list: list[str] = list(ip_itter(ip_string)) 

        if not self.sock:
            print("Erro: o socket não está aberto.")
            return

        # Busca dados da tarefa no banco
        task_data = db.rollingback(
            lambda session: session.query(db.Task)
            .filter(db.Task.id == 1)
            .first()
            .__dict__.copy()
        )()

        if not task_data:
            print(f"Erro: Task com ID {task_id} não encontrada.")
            return

        data_package = task_data["instructions"]

        for ip in ip_list:
            hexid = urandom(8).hex()  # Gera ID único para o envio
            datapack = {"sent_id": hexid, "data_package": data_package}
            compressed_json = zlib.compress(json.dumps(datapack).encode("utf-8"))
            destino = (ip, self.porta)
            try:
                db.task_sent(usuario_id, task_id, ip, hexid)  # Registra envio no banco
                self.sock.sendto(compressed_json, destino)  # Envia pacote UDP
                print(f"data '{data_package}' enviado para {ip}")
            except Exception as e:
                print(f"Erro ao enviar para {ip}: {e}")

    async def socket_status(self):
        # Retorna status do socket
        return "Aberto" if self.sock else "Fechado"
```

- Ao criar uma instância são definidos as portas de comunicação entre os socket e inicializado o socket e a fila de tarefas.
- O método `open_socket` abre o socket UDP e inicia o event loop definido na construção da instância em uma thread separada. Também inicia a escuta de pacotes em outra thread.
- O método `close_socket` fecha o socket e cancela a tarefa de processamento de pacotes.
- O método `data_worker` é uma função assíncrona que pega itens da fila e processa cada pacote recebido.
- O método `work` descomprime e decodifica o pacote, extrai informações e atualiza o banco de dados.
- O método `ouvir_respostas` fica esperando pacotes e coloca cada pacote recebido na fila para ser processado pelo `data_worker`.
- O método `enviar_pacote` prepara os dados, comprime e envia para cada IP de destino, registrando o envio no banco de dados.
- O método `socket_status` retorna se o socket está aberto ou fechado.
- Foram utilizadas 2 módulo locais, db e ip_itter, db é uma classe responsável pelo tratamento do banco de dados no meu código, ip_itter transforma uma string numa lista de IPs, por exemplo: "192.168.4.168-192.168.4.170" = ["192.168.4.168", "192.168.4.169", "192.168.4.170"]


# Melhorias, Brechas e Observações

- O projeto será compilado para um executável utilizando **Nuitka**, dificultando o acesso direto ao código fonte.
- O executável será registrado como um serviço Windows utilizando **NSSM**, garantindo execução automática, segura e contínua.
- A instalação será feita via **.msi**. Durante a instalação, o cliente poderá definir as variáveis `IPS_PERMITIDOS`, `PORTA`, `BUFFER_SIZE`, `IP_LIMIT`, `SEC_INTERVAL`, que serão armazenadas como variáveis de ambiente ou chaves de registro do Windows (a definir).
- Atualmente, o pacote de dados não é encriptado. Pretendo utilizar **HMAC** para assinar e criptografar o pacote, garantindo validação e confidencialidade dos dados.
- Também será incluído um **timestamp único** em cada pacote para evitar ataques de replay (reutilização de pacotes antigos).
- Pretendo utilizar **DTLS (Datagram Transport Layer Security)** para adicionar uma camada de segurança ao protocolo UDP, protegendo os dados transmitidos contra interceptação e adulteração. O DTLS garante autenticação, integridade e confidencialidade, tornando a comunicação mais segura sem perder a performance do UDP.

