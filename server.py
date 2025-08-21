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
