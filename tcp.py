import asyncio
import os
import time
from tcputils import *


class Servidor:
    def __init__(self, rede, porta):
        self.rede = rede
        self.porta = porta
        self.conexoes = {}
        self.callback = None
        self.rede.registrar_recebedor(self._rdt_rcv)

    def registrar_monitor_de_conexoes_aceitas(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que uma nova conexão for aceita
        """
        self.callback = callback

    def _rdt_rcv(self, src_addr, dst_addr, segment):
        src_port, dst_port, seq_no, ack_no, \
            flags, window_size, checksum, urg_ptr = read_header(segment)

        if dst_port != self.porta:
            # Ignora segmentos que não são destinados à porta do nosso servidor
            return
        if not self.rede.ignore_checksum and calc_checksum(segment, src_addr, dst_addr) != 0:
            print('descartando segmento com checksum incorreto')
            return

        payload = segment[4*(flags>>12):]
        id_conexao = (src_addr, src_port, dst_addr, dst_port)

        if (flags & FLAGS_SYN) == FLAGS_SYN:
            # A flag SYN estar setada significa que é um cliente tentando estabelecer uma conexão nova
            # TODO: talvez você precise passar mais coisas para o construtor de conexão
            conexao = self.conexoes[id_conexao] = Conexao(self, id_conexao, int.from_bytes(os.urandom(4), byteorder="big"), seq_no + 1)
            # TODO: você precisa fazer o handshake aceitando a conexão. Escolha se você acha melhor
            # fazer aqui mesmo ou dentro da classe Conexao.
            print("cliente : seq {}, ack {}, tam 0".format(seq_no, ack_no))
            conexao.servidor.rede.enviar(fix_checksum(make_header(dst_port, src_port, conexao.seq_no, conexao.ack_no, (FLAGS_SYN|FLAGS_ACK)), dst_addr, src_addr), id_conexao[0])
            conexao.seq_no += 1
            print("servidor : seq {}, ack {}, tam {}".format(conexao.seq_no, conexao.ack_no, 0))
            if self.callback:
                self.callback(conexao)
        elif id_conexao in self.conexoes:
            # Passa para a conexão adequada se ela já estiver estabelecida
            self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)
        else:
            print('%s:%d -> %s:%d (pacote associado a conexão desconhecida)' %
                  (src_addr, src_port, dst_addr, dst_port))


class Conexao:
    def __init__(self, servidor, id_conexao, seq_no, ack_no):
        self.servidor = servidor
        self.id_conexao = id_conexao
        self.callback = None
        self.dados = []
        self.send_base = seq_no
        self.seq_no = seq_no # do servidor
        self.ack_no = ack_no # do servidor
        self.timer = None
        self.conectado = False
        self.sampleRTT = 0
        self.estimatedRTT = 0
        self.devRTT = 0
        self.tempoEnvio = 0
        self.tempoRecebido = 0
        self.isreenvio = False
        self.Timeout = 1
        self.janela = MSS
        self.fila = None

    def reenvio(self):
        self.isreenvio = True
        if(self.dados):
            if(len(self.dados[0]) > MSS):
                self.servidor.rede.enviar(fix_checksum(make_header(self.id_conexao[3], self.id_conexao[1], self.send_base, self.ack_no, FLAGS_ACK) + self.dados[0][0: MSS], self.id_conexao[2], self.id_conexao[0]), self.id_conexao[0])
            else:
                self.servidor.rede.enviar(fix_checksum(make_header(self.id_conexao[3], self.id_conexao[1], self.send_base, self.ack_no, FLAGS_ACK) + self.dados[0], self.id_conexao[2], self.id_conexao[0]), self.id_conexao[0])
            if(self.janela > MSS):
                self.janela = int(self.janela / MSS / 2 + 0.5) * MSS
            print("REDUZ JANELA: " + str(self.janela))
            self.verifica_timer()
    
    def verifica_timer(self):
        if (self.timer):
            self.timer.cancel()
        self.timer = asyncio.get_event_loop().call_later(self.Timeout, self.reenvio)
     
    def _rdt_rcv(self, seq_no, ack_no, flags, payload):
        # TODO: trate aqui o recebimento de segmentos provenientes da camada de rede.
        # Chame self.callback(self, dados) para passar dados para a camada de aplicação após
        # garantir que eles não sejam duplicados e que tenham sido recebidos em ordem.
        if(self.conectado and len(payload) == 0):
            if(self.isreenvio):
                self.isreenvio = False
            else:
                if(self.dados and self.seq_no - self.send_base == self.janela):
                    self.janela += MSS

                if(self.sampleRTT == 0):
                    primeiro = True
                else:
                    primeiro = False

                self.sampleRTT = time.time() - self.tempoEnvio
                
                if(primeiro):
                    self.estimatedRTT = self.sampleRTT
                    self.devRTT = self.sampleRTT/2
                else:
                    self.estimatedRTT = 0.875*self.estimatedRTT + 0.125*self.sampleRTT
                    self.devRTT = 0.75*self.devRTT + 0.25*abs(self.sampleRTT - self.estimatedRTT)
                
                self.Timeout = self.estimatedRTT + 4*self.devRTT
                
        print("cliente : seq {}, ack {}, tam {}".format(seq_no, ack_no, len(payload)))
        if(seq_no == self.ack_no and len(payload) > 0):
            self.ack_no = seq_no + len(payload)
            self.servidor.rede.enviar(fix_checksum(make_header(self.id_conexao[3], self.id_conexao[1], self.seq_no, self.ack_no, FLAGS_ACK), self.id_conexao[2], self.id_conexao[0]), self.id_conexao[0])
            self.callback(self, payload)
        elif((flags & FLAGS_FIN) == FLAGS_FIN):
            self.ack_no = seq_no + 1
            self.servidor.rede.enviar(fix_checksum(make_header(self.id_conexao[3], self.id_conexao[1], self.seq_no, self.ack_no, FLAGS_FIN|FLAGS_ACK), self.id_conexao[2], self.id_conexao[0]), self.id_conexao[0])
            self.callback(self, b'')
        elif(len(payload) == 0 and ack_no > self.seq_no):
            # payload tamanho 0 é encontrado na solicitação de conexão, que não vem para cá; acks, mas que o ack_no é igual ao self.seq_no,
            # Exceto no desligamento, em que propositalmente não foi incrementado 1 ao self.seq_no.
            # Talvez não seja a melhor forma de fazer isso
            del self.servidor.conexoes[self.id_conexao]
        elif(self.dados):
            if(ack_no > self.send_base):
                self.send_base = ack_no
                if(self.send_base < self.seq_no):
                    # Caso tenha mais pacotes no vetor, deleta o primeiro quando confirmar ele
                    if(len(self.dados[0][MSS:]) == 0):
                        del self.dados[0]
                    else:
                        self.dados[0] = self.dados[0][MSS:]
                    self.verifica_timer()
                elif(self.fila):
                    print("CONTINUA")
                    del self.dados[0]
                    self.enviar(self.fila)
                else:
                    if(self.timer):
                        self.timer.cancel()
                    del self.dados[0]
        else:
            self.conectado = True
        self.isreenvio = False
        #print('recebido payload: %r' % payload)

    # Os métodos abaixo fazem parte da API
    
    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    def enviar(self, dados):
        """
        Usado pela camada de aplicação para enviar dados
        """
        # TODO: implemente aqui o envio de dados.
        # Chame self.servidor.rede.enviar(segmento, dest_addr) para enviar o segmento
        # que você construir para a camada de rede.
        tam = len(dados)
        if(not self.dados):
            self.send_base = self.seq_no
        x = min(tam, self.janela)
        print("TAMANHO DADOS: " + str(tam) + " | JANELA: " + str(self.janela) + " | X: " + str(x)+ " | VEZES: " + str(int((x + MSS - 1)/MSS)))
        for i in range(int((x + MSS - 1)/MSS)):
            if((i+1) * MSS > x):
                print("servidor : seq {}, ack {}, tam {}".format(self.seq_no + i * MSS, self.ack_no, len(dados[i*MSS: x - (x % MSS)])))
                self.servidor.rede.enviar(fix_checksum(make_header(self.id_conexao[3], self.id_conexao[1], self.seq_no + i * MSS, self.ack_no, FLAGS_ACK) + dados[i*MSS: x - (x % MSS)], self.id_conexao[2], self.id_conexao[0]), self.id_conexao[0])
                self.verifica_timer()
            else:
                print("servidor : seq {}, ack {}, tam {}".format(self.seq_no + i * MSS, self.ack_no, len(dados[i*MSS: (i+1)*MSS])))
                self.servidor.rede.enviar(fix_checksum(make_header(self.id_conexao[3], self.id_conexao[1], self.seq_no + i * MSS, self.ack_no, FLAGS_ACK) + dados[i*MSS: (i+1)*MSS], self.id_conexao[2], self.id_conexao[0]), self.id_conexao[0])
                self.verifica_timer()
        if(tam > self.janela):
            self.fila = dados[self.janela:]
            self.dados.append(dados[0:self.janela])
            self.seq_no += self.janela
        else:
            self.dados.append(dados)
            self.fila = None
            self.seq_no += tam
        self.tempoEnvio = time.time()
        pass

    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        # TODO: implemente aqui o fechamento de conexão
        self.servidor.rede.enviar(fix_checksum(make_header(self.id_conexao[3], self.id_conexao[1], self.seq_no, self.ack_no, (FLAGS_FIN|FLAGS_ACK)), self.id_conexao[2], self.id_conexao[0]), self.id_conexao[0])
        self.verifica_timer()
        print("servidor : seq {}, ack {}, tam 0".format(self.seq_no, self.ack_no))
        pass