from iputils import *
from ipaddress import ip_network, ip_address
import struct

class IP:
    def __init__(self, enlace):
        """
        Inicia a camada de rede. Recebe como argumento uma implementação
        de camada de enlace capaz de localizar os next_hop (por exemplo,
        Ethernet com ARP).
        """
        self.callback = None
        self.enlace = enlace
        self.enlace.registrar_recebedor(self.__raw_recv)
        self.ignore_checksum = self.enlace.ignore_checksum
        self.meu_endereco = None
        self.ID = 0

    def __raw_recv(self, datagrama):
        dscp, ecn, identification, flags, frag_offset, ttl, proto, \
           src_addr, dst_addr, payload = read_ipv4_header(datagrama)
        if dst_addr == self.meu_endereco:
            # atua como host
            if proto == IPPROTO_TCP and self.callback:
                self.callback(src_addr, dst_addr, payload)
        else:
            # atua como roteador
            next_hop = self._next_hop(dst_addr)
            #[DONE]PASSO 4
            # TODO: Trate corretamente o campo TTL do datagrama

            ttl-=1

            if ttl > 0 :

                vihl = 0x45
                dscpecn = 0
                totallen = 20+len(payload)
                id = self.ID
                flagsfrag = 0
                protocol = 6
                checksum = 0
            
                header = struct.pack('!BBHHHBBH', vihl, dscpecn, totallen, id, flagsfrag, ttl, protocol, checksum) \
                    + str2addr(src_addr) \
                    + str2addr(dst_addr)
        
                checksum = calc_checksum(header)

                datagrama = struct.pack('!BBHHHBBH', vihl, dscpecn, totallen, id, flagsfrag, ttl, protocol, checksum) \
                    + str2addr(src_addr) \
                    + str2addr(dst_addr) \
                    + payload
                
                self.enlace.enviar(datagrama, next_hop)
                
            else:
                #[DONE] PASSO 5
                next_hop = self._next_hop(src_addr)
            
                type = 11
                code = 0
                icmp_checksum = 0
                unused = 0
                icmp_datagrama = datagrama[:28]
                
                icmp_header = struct.pack('!BBHI', type, code, icmp_checksum, unused) + icmp_datagrama
                icmp_checksum = calc_checksum(icmp_header)
                icmp_payload = struct.pack('!BBHI', type, code, icmp_checksum, unused) + icmp_datagrama
                
                vihl = 0x45
                dscpecn = 0
                totallen = 20+len(icmp_payload)
                id = self.ID
                flagsfrag = 0
                ttl = 64
                protocol = 1
                checksum = 0

                header = struct.pack('!BBHHHBBH', vihl, dscpecn, totallen, id, flagsfrag, ttl, protocol, checksum) \
                    + str2addr(self.meu_endereco) \
                    + str2addr(src_addr)
        
                checksum = calc_checksum(header)

                datagrama = struct.pack('!BBHHHBBH', vihl, dscpecn, totallen, id, flagsfrag, ttl, protocol, checksum) \
                    + str2addr(self.meu_endereco) \
                    + str2addr(src_addr) \
                    + icmp_payload
                
                self.enlace.enviar(datagrama, next_hop)


    def _next_hop(self, dest_addr):
        #[DONE] PASSO 1 e PASSO 3
        # TODO: Use a tabela de encaminhamento para determinar o próximo salto
        # (next_hop) a partir do endereço de destino do datagrama (dest_addr).
        # Retorne o next_hop para o dest_addr fornecido.
    
        n = -1
        #Transforma em um único inteiro de 32bits
        dest_addr, = struct.unpack('!I', str2addr(dest_addr))

        for cidr in self.tabela:
            #ip_network
            net, = struct.unpack('!I', str2addr(cidr[0].split('/')[0]))
            #numero de bits do endereço a serem consideraços
            nbits = int(cidr[0].split('/')[1])
            if net == (dest_addr >> 32-nbits << 32-nbits) and nbits > n:
                next_hop = cidr[1]
                n = nbits
        
        if n > -1:
            return next_hop
        else:
            return None


    def definir_endereco_host(self, meu_endereco):
        """
        Define qual o endereço IPv4 (string no formato x.y.z.w) deste host.
        Se recebermos datagramas destinados a outros endereços em vez desse,
        atuaremos como roteador em vez de atuar como host.
        """
        self.meu_endereco = meu_endereco

    def definir_tabela_encaminhamento(self, tabela):
        """
        Define a tabela de encaminhamento no formato
        [(cidr0, next_hop0), (cidr1, next_hop1), ...]

        Onde os CIDR são fornecidos no formato 'x.y.z.w/n', e os
        next_hop são fornecidos no formato 'x.y.z.w'.
        """
        # [DONE] PASSO 1
        # TODO: Guarde a tabela de encaminhamento. Se julgar conveniente,
        # converta-a em uma estrutura de dados mais eficiente.
        self.tabela = tabela

    def registrar_recebedor(self, callback):
        """
        Registra uma função para ser chamada quando dados vierem da camada de rede
        """
        self.callback = callback

    def enviar(self, segmento, dest_addr):
        """
        Envia segmento para dest_addr, onde dest_addr é um endereço IPv4
        (string no formato x.y.z.w).
        """
        next_hop = self._next_hop(dest_addr)
        #[DONE] PASSO 3
        # TODO: Assumindo que a camada superior é o protocolo TCP, monte o
        # datagrama com o cabeçalho IP, contendo como payload o segmento.

        #Definindo cabeçalho IPV4
        vihl = 0x45
        dscpecn = 0
        totallen = 20+len(segmento)
        id = self.ID
        self.ID+=1
        flagsfrag = 0
        ttl = 64
        protocol = 6
        checksum = 0
        
        header = struct.pack('!BBHHHBBH', vihl, dscpecn, totallen, id, flagsfrag, ttl, protocol, checksum) \
                    + str2addr(self.meu_endereco) \
                    + str2addr(dest_addr)
        
        checksum = calc_checksum(header)

        datagrama = struct.pack('!BBHHHBBH', vihl, dscpecn, totallen, id, flagsfrag, ttl, protocol, checksum) \
                    + str2addr(self.meu_endereco) \
                    + str2addr(dest_addr) \
                    + segmento
        

        self.enlace.enviar(datagrama, next_hop)
