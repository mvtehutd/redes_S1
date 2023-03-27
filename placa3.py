#!/usr/bin/env python3
import asyncio
from camadafisica import ZyboSerialDriver
from tcp import Servidor        # copie o arquivo do T2
from ip import IP               # copie o arquivo do T3
from slip import CamadaEnlace   # copie o arquivo do T4
import re

## Implementação da camada de aplicação

lista_de_nicks = {}
lista_de_canais = {}

def validar_nome(nome):
    return re.match(br'^[a-zA-Z][a-zA-Z0-9_-]*$', nome) is not None

def sair(conexao):
    print(conexao, 'conexão fechada')
    if conexao.nickname.upper() in lista_de_nicks:
        del lista_de_nicks[conexao.nickname.upper()]
    for i in conexao.canais:
        canal = i.upper()
        msg = b':%s QUIT :Connection closed\r\n' % (conexao.nickname)
        lista_de_canais[canal].remove(conexao)
        for j in lista_de_canais[canal]:
            j.enviar(msg)
    conexao.fechar()

def analisa_mensagem(conexao, mensagem):
    if mensagem.startswith(b'PING'):
        conexao.enviar(b':server PONG server :' + mensagem.split(b' ', 1)[1])
    elif mensagem.startswith(b'NICK'):
        nome = mensagem.split(b' ', 1)[1][:-2]
        if validar_nome(nome):
            nomeMaiusculo = nome.upper()
            if(nomeMaiusculo not in lista_de_nicks):
                if(conexao.nickname == b'*'):
                    conexao.enviar(b':server 001 ' + nome + b' :Welcome\r\n')
                    conexao.enviar(b':server 422 ' + nome + b' :MOTD File is missing\r\n')
                else:
                    conexao.enviar(b':' + conexao.nickname + b' NICK ' + nome + b'\r\n')
                    del lista_de_nicks[conexao.nickname.upper()]
                lista_de_nicks[nomeMaiusculo] = conexao
                conexao.nickname = nome
            else:
                conexao.enviar(b':server 433 ' + conexao.nickname + b' ' + nome + b' :Nickname is already in use\r\n')       
        else:
            conexao.enviar(b':server 432 ' + conexao.nickname + b' ' + nome + b' :Erroneous nickname\r\n')
    elif mensagem.startswith(b'PRIVMSG'):
        destino = mensagem.split(b' ', 2)[1]
        destinoMaiusculo = destino.upper()
        if(destino[0:1] != b'#' and destinoMaiusculo in lista_de_nicks):
            msg = b':%s PRIVMSG %s %s' % (conexao.nickname, destino, mensagem.split(b' ', 2)[2])
            lista_de_nicks[destinoMaiusculo].enviar(msg)
        elif(destino[0:1] == b'#' and destinoMaiusculo in lista_de_canais):
            msg = b':%s PRIVMSG %s %s' % (conexao.nickname, destino, mensagem.split(b' ', 2)[2])
            for i in lista_de_canais[destinoMaiusculo]:
                if(i != conexao):
                    i.enviar(msg)
    elif mensagem.startswith(b'JOIN'):
        canal = mensagem.split(b' ', 1)[1][:-2]
        canalMaiusculo = canal.upper()
        if(canal[0:1] == b'#' and validar_nome(canal[1:])):
            conexao.canais.append(canal)
            if(canalMaiusculo in lista_de_canais):
                lista_de_canais[canalMaiusculo].append(conexao)
            else:
                lista_de_canais[canalMaiusculo] = [conexao]
            msg = b':%s JOIN :%s\r\n' % (conexao.nickname, canal)
            membros = []
            for i in lista_de_canais[canalMaiusculo]:
                i.enviar(msg)
                membros.append(i.nickname)
            msg = b':server 353 %s = %s :%s\r\n' % (conexao.nickname, canal, b' '.join(sorted(membros)))
            conexao.enviar(msg)
            msg = b':server 366 %s %s :End of /NAMES list.\r\n' % (conexao.nickname, canal)
            conexao.enviar(msg)
        else:
            conexao.enviar(b':server 403 %s :No such channel' % (canal))
    elif mensagem.startswith(b'PART'):
        canal = mensagem.split(b' ', 2)[1]
        if(b'\r\n' in canal):
            canal = canal[:-2]
        canalMaiusculo = canal.upper()
        if(canal[0:1] == b'#' and validar_nome(canal[1:])):
            conexao.canais.remove(canal)
            msg = b':%s PART %s\r\n' % (conexao.nickname, canal)
            for i in lista_de_canais[canalMaiusculo]:
                i.enviar(msg)
            lista_de_canais[canalMaiusculo].remove(conexao)


def dados_recebidos(conexao, dados):
    if dados == b'':
        return sair(conexao)
    mensagem = conexao.fragmentos + dados
    for i in range(mensagem.count(b'\r\n')):
        fim = mensagem.find(b'\r\n')
        analisa_mensagem(conexao, mensagem[0:fim+2])
        mensagem = mensagem[fim+2:]
    conexao.fragmentos = mensagem
        
            
    print(conexao, dados)


def conexao_aceita(conexao):
    print(conexao, 'nova conexão')
    conexao.fragmentos = b''
    conexao.nickname = b'*'
    conexao.canais = []
    conexao.registrar_recebedor(dados_recebidos)

# # Este é um exemplo de um programa que faz eco, ou seja, envia de volta para
# # o cliente tudo que for recebido em uma conexão.

# def dados_recebidos(conexao, dados):
#     if dados == b'':
#         conexao.fechar()
#     else:
#         conexao.enviar(dados)   # envia de volta

# def conexao_aceita(conexao):
#     conexao.registrar_recebedor(dados_recebidos)   # usa esse mesmo recebedor para toda conexão aceita


## Integração com as demais camadas

nossa_ponta = '192.168.200.4'
outra_ponta = '192.168.200.3'
porta_tcp = 7000

driver = ZyboSerialDriver()
linha_serial = driver.obter_porta(0)

enlace = CamadaEnlace({outra_ponta: linha_serial})
rede = IP(enlace)
rede.definir_endereco_host(nossa_ponta)
rede.definir_tabela_encaminhamento([
    ('0.0.0.0/0', outra_ponta)
])
servidor = Servidor(rede, porta_tcp)
servidor.registrar_monitor_de_conexoes_aceitas(conexao_aceita)
asyncio.get_event_loop().run_forever()