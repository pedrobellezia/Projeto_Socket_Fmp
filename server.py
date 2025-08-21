import zlib
import json
import subprocess
import socket
import time
import re


IPS_PERMITIDOS = [
    '192.168.0.10',
    '192.168.0.20',
    '127.0.0.1'
]

PORTA = 9999
BUFFER_SIZE = 2048
LIMITE_POR_IP = 3
INTERVALO_SEGUNDOS = 60
acessos_por_ip = {}

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

def get_serial_number():
    data = subprocess.check_output('wmic bios get serialnumber').decode("utf-8")
    serial_number = re.search(r'SerialNumber\s+[\r\n]+([A-Z0-9]+)', data)
    return serial_number.group(1) if serial_number else None

def servidor_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORTA))
    print(f"Servidor escutando na porta {PORTA}")
    while True:
        try:
            data, (ip, port) = sock.recvfrom(BUFFER_SIZE)
            agora = time.time()
            if ip not in acessos_por_ip:
                acessos_por_ip[ip] = []
            fila = acessos_por_ip[ip]
            fila[:] = [t for t in fila if agora - t <= INTERVALO_SEGUNDOS]
            if len(fila) < LIMITE_POR_IP:
                fila.append(agora)
                if ip in IPS_PERMITIDOS:
                    if data:
                        new_data = processar_pacote(data, ip)
                        sock.sendto(new_data, (ip, port))
                    else:
                        print(f"Pacote vazio recebido de {ip}")
                else:
                    print(f"Pacote recusado de IP não autorizado: {ip}")
            else:
                print(f"Limite de requisições atingido para {ip}")
        except Exception as e:
            print(f"Erro no servidor: {e}")

if __name__ == "__main__":
    servidor_udp()