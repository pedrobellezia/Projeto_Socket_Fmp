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