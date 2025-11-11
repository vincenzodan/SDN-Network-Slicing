# ws_controller_bandwidth_latency.py
import json, time
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet, arp, ether_types
from websocket_server import WebsocketServer

WS_PORT = 8765

class BandwidthLatencyController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}
        self.port_stats = {}
        self.prev_port_stats = {}
        self.switch_latency = {}
        self.echo_sent_time = {}
        self.clients = set()
        self.monitor_thread = hub.spawn(self._monitor)
        self.ws_thread = hub.spawn(self._start_ws_server)

        # MAC degli host
        self.h1 = '00:00:00:00:00:01'
        self.h2 = '00:00:00:00:00:02'
        self.h3 = '00:00:00:00:00:03'
        self.h4 = '00:00:00:00:00:04'

    # ---- Switch connected ----
    @set_ev_cls(ofp_event.EventOFPStateChange, MAIN_DISPATCHER)
    def switch_connected(self, ev):
        dp = ev.datapath
        self.datapaths[dp.id] = dp
        self.logger.info(f"Switch {dp.id} connesso")
        self._install_flows(dp)

    # ---- Regole statiche ----
    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, flags=0):
        inst = [datapath.ofproto_parser.OFPInstructionActions(datapath.ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match,
            instructions=inst, idle_timeout=idle_timeout, flags=flags)
        datapath.send_msg(mod)

    def add_mac_flow(self, datapath, src, dst, out_port, priority=10):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(eth_src=src, eth_dst=dst)
        actions = [parser.OFPActionOutput(out_port)]
        self.add_flow(datapath, priority, match, actions)

    def add_arp_flow(self, datapath, src_mac, out_port, priority=20):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(eth_src=src_mac, eth_dst='ff:ff:ff:ff:ff:ff', eth_type=0x0806)
        actions = [parser.OFPActionOutput(p) for p in out_port] if isinstance(out_port, list) else [parser.OFPActionOutput(out_port)]
        self.add_flow(datapath, priority, match, actions)

    def _install_flows(self, dp):
        dpid = dp.id
        # s1
        if dpid == 1:
            self.add_mac_flow(dp, self.h1, self.h3, 3)
            self.add_mac_flow(dp, self.h3, self.h1, 1)
            self.add_arp_flow(dp, self.h1, 3)
            self.add_arp_flow(dp, self.h3, 1)

            self.add_mac_flow(dp, self.h2, self.h4, 4)
            self.add_mac_flow(dp, self.h4, self.h2, 2)
            self.add_arp_flow(dp, self.h2, 4)
            self.add_arp_flow(dp, self.h4, 2)

        elif dpid == 2:
            self.add_mac_flow(dp, self.h1, self.h3, 2)
            self.add_mac_flow(dp, self.h3, self.h1, 1)
            self.add_arp_flow(dp, self.h1, 2)
            self.add_arp_flow(dp, self.h3, 1)

        elif dpid == 3:
            self.add_mac_flow(dp, self.h2, self.h4, 2)
            self.add_mac_flow(dp, self.h4, self.h2, 1)
            self.add_arp_flow(dp, self.h2, 2)
            self.add_arp_flow(dp, self.h4, 1)

        elif dpid == 4:
            self.add_mac_flow(dp, self.h1, self.h3, 3)
            self.add_mac_flow(dp, self.h3, self.h1, 1)
            self.add_arp_flow(dp, self.h1, 3)
            self.add_arp_flow(dp, self.h3, 1)

            self.add_mac_flow(dp, self.h2, self.h4, 4)
            self.add_mac_flow(dp, self.h4, self.h2, 2)
            self.add_arp_flow(dp, self.h2, 4)
            self.add_arp_flow(dp, self.h4, 2)

    # ---- PacketIn (ARP) ----
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        arp_pkt = pkt.get_protocol(arp.arp)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        if arp_pkt:
            self.logger.info(f"[ARP] {eth.src} -> {eth.dst}")

    # ---- Port stats ----
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        dp = ev.msg.datapath
        now = time.time()
        for stat in ev.msg.body:
            port_no = stat.port_no
            if port_no < 1 or port_no > 65534:
                continue
            key = (dp.id, port_no)
            rx = stat.rx_bytes
            tx = stat.tx_bytes
            prev = self.prev_port_stats.get(key)
            if prev:
                dt = now - prev["time"]
                rx_mbps = (rx - prev["rx_bytes"]) * 8 / dt / 1_000_000
                tx_mbps = (tx - prev["tx_bytes"]) * 8 / dt / 1_000_000
            else:
                rx_mbps = tx_mbps = 0
            self.port_stats[key] = {"rx_mbps": rx_mbps, "tx_mbps": tx_mbps}
            self.prev_port_stats[key] = {"rx_bytes": rx, "tx_bytes": tx, "time": now}

    # ---- Echo reply per latenza ----
    @set_ev_cls(ofp_event.EventOFPEchoReply, MAIN_DISPATCHER)
    def echo_reply_handler(self, ev):
        now = time.time()
        dpid = ev.msg.datapath.id
        sent_time = self.echo_sent_time.get(dpid, None)
        if sent_time:
            latency = (now - sent_time) * 1000  # ms
            self.switch_latency[dpid] = latency
            self.logger.info(f"Latenza Switch {dpid}: {latency:.2f} ms")

    # ---- Monitor ----
    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_port_stats(dp)
                self._send_echo(dp)
            hub.sleep(1)
            self._send_stats_to_ws()

    def _request_port_stats(self, dp):
        dp.send_msg(dp.ofproto_parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY))

    def _send_echo(self, dp):
        self.echo_sent_time[dp.id] = time.time()
        req = dp.ofproto_parser.OFPEchoRequest(dp, data=b'ping')
        dp.send_msg(req)

    # ---- WebSocket ----
    def _start_ws_server(self):
        self.logger.info(f"Avvio WebSocket server ws://0.0.0.0:{WS_PORT}")
        self.server = WebsocketServer(port=WS_PORT, host='0.0.0.0')
        self.server.set_fn_new_client(self.new_client)
        self.server.set_fn_client_left(self.client_left)
        self.server.run_forever()

    def new_client(self, client, server):
        self.logger.info(f"Nuovo client connesso: {client['id']}")
        self.clients.add(client['id'])

    def client_left(self, client, server):
        self.logger.info(f"Client disconnesso: {client['id']}")
        self.clients.discard(client['id'])

    def _send_stats_to_ws(self):
        if not self.clients:
            return
        msg_data = [{"dpid": dpid, "port_no": p,
             "rx_mbps": stats["rx_mbps"],
             "tx_mbps": stats["tx_mbps"],
             "bandwidth_mbps": stats["rx_mbps"] + stats["tx_mbps"],
             "latency_ms": self.switch_latency.get(dpid, None)}   # aggiunto
            for (dpid, p), stats in self.port_stats.items()]
        msg = json.dumps({"type": "bandwidth_stats", "stats": msg_data})
        for client_id in list(self.clients):
            try:
                client_obj = next((c for c in self.server.clients if c['id'] == client_id), None)
                if client_obj:
                    self.server.send_message(client_obj, msg)
            except:
                self.clients.discard(client_id)

