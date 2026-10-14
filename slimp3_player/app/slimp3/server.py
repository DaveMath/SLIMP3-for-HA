# SPDX-License-Identifier: GPL-2.0-only
import asyncio
import socket
import time

from .player import Player
from .protocol import PORT, discovery_reply, hello, mac_of, parse_ack


class Server(asyncio.DatagramProtocol):
    """UDP endpoint for SLIMP3 devices: discovery, hello, IR, acks."""

    def __init__(self, seed_ips=(), log=print):
        self.players = {}
        self.seed_ips = list(seed_ips)
        self.log = log
        self.on_new_player = None
        self.on_reboot = None
        self.transport = None
        self.last_seen = {}
        self.player_defaults = {}

    async def start(self, host="0.0.0.0", port=PORT):
        loop = asyncio.get_event_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((host, port))
        sock.setblocking(False)
        self.transport, _ = await loop.create_datagram_endpoint(lambda: self, sock=sock)
        self.log("listening on UDP %d" % port)
        loop.create_task(self._keepalive())

    def send(self, addr, data):
        if self.transport:
            self.transport.sendto(data, addr)

    async def _keepalive(self):
        while True:
            for p in self.players.values():
                self.send(p.addr, hello())
            if not self.players:
                for ip in self.seed_ips:
                    self.send((ip, PORT), hello())
            await asyncio.sleep(3 if not self.players else 10)

    def datagram_received(self, data, addr):
        if len(data) < 18:
            return
        t = chr(data[0])
        if t == "d":
            self.send(addr, discovery_reply())
            self.send(addr, hello())
            self.log("discovery from %s" % addr[0])
            for p in self.players.values():     # a known player discovering again has restarted
                if p.addr[0] == addr[0] and self.on_reboot:
                    self.on_reboot(p)
        elif t == "h":
            mac = mac_of(data)
            p = self.players.get(mac)
            if p is None:
                p = self.players[mac] = Player(self, mac, addr, self.log)
                p.fw = "%d.%d" % (data[2] >> 4, data[2] & 15)
                for k, v in self.player_defaults.items():
                    setattr(p, k, v)
                self.log("player %s at %s fw %d.%d" % (mac, addr[0], data[2] >> 4, data[2] & 15))
                if self.on_new_player:
                    self.on_new_player(p)
            p.addr = addr
            p.fw = "%d.%d" % (data[2] >> 4, data[2] & 15)
            self.last_seen[mac] = time.time()
        elif t == "a":
            p = self.players.get(mac_of(data))
            if p and p.stream:
                p.stream.on_ack(*parse_ack(data))
        elif t == "i":
            p = self.players.get(mac_of(data))
            if p and p.on_ir:
                p.on_ir(data[8:12].hex())
