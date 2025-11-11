from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet, ipv4, udp
from ryu.lib import hub
import time

UDP_PORT_STREAMING = 9999
BANDWIDTH_THRESHOLD = 8_000_000

class RyuController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(RyuController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}         # tabella MAC → porta
        self.datapaths = {}
        self.port_stats = {}       # stato attuale
        self.port_stats_prev = {}  # stato precedente
        self.monitor_thread = hub.spawn(self._monitor)
        
    def _monitor(self):
        """Thread periodico per chiedere statistiche"""
        while True:
            for dp in self.datapaths.values():
                parser = dp.ofproto_parser
                req = parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY)
                dp.send_msg(req)
            hub.sleep(1)  # ogni secondo

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, flag=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath, priority=priority,
            match=match, instructions=inst,
            idle_timeout=idle_timeout, flags=flag
        )
        datapath.send_msg(mod)
        
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Salva le statistiche correnti"""
        dp = ev.msg.datapath
        dpid = dp.id
        now = time.time()

        for stat in ev.msg.body:
            port_no = stat.port_no
            rx = stat.rx_bytes
            tx = stat.tx_bytes
            prev = self.port_stats.get((dpid, port_no))
            self.port_stats_prev[(dpid, port_no)] = prev
            self.port_stats[(dpid, port_no)] = (rx, tx, now)
        
    def get_port_bandwidth(self, dpid, port_no):
        """Ritorna la banda stimata (bps) su una porta"""
        current = self.port_stats.get((dpid, port_no))
        prev = self.port_stats_prev.get((dpid, port_no))
        if not current or not prev:
            return 0
        rx_diff = current[0] - prev[0]
        tx_diff = current[1] - prev[1]
        t_diff = current[2] - prev[2]
        if t_diff <= 0:
            return 0
        return (rx_diff + tx_diff) * 8 / t_diff
               
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.logger.info(f"[FEATURES HANDLER] dpid={dpid}")

        # regola di default: manda tutto al controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match, actions=actions)

        # impostazioni specifiche per UDP:9999 (piano "up")
        if dpid == 1:
            for host_port in [1, 2]:  # h1,h2
                match = parser.OFPMatch(
                    in_port=host_port,
                    eth_type=0x0800,
                    ip_proto=17,
                    udp_dst=UDP_PORT_STREAMING
                )
                actions = [parser.OFPActionOutput(3)]  # verso s2
                self.add_flow(datapath, priority=100, match=match, actions=actions)

        elif dpid == 2:
            # s2: riceve UDP da s1 e manda a s4
            match = parser.OFPMatch(
                in_port=1,
                eth_type=0x0800,
                ip_proto=17,
                udp_dst=UDP_PORT_STREAMING
            )
            actions = [parser.OFPActionOutput(2)]  # verso s4
            self.add_flow(datapath, priority=100, match=match, actions=actions)
            
            # s2: riceve UDP da s4 e manda a s1
            match = parser.OFPMatch(
                in_port=2,
                eth_type=0x0800,
                ip_proto=17,
                udp_dst=UDP_PORT_STREAMING
            )
            actions = [parser.OFPActionOutput(1)]  # verso s4
            self.add_flow(datapath, priority=100, match=match, actions=actions)

        elif dpid == 3:
            # s3 non inoltra traffico UDP
            pass

        elif dpid == 4:
            # s4: inoltra UDP verso s2
            for host_port in [3, 4]:  # h3,h4
                match = parser.OFPMatch(
                    in_port=host_port,
                    eth_type=0x0800,
                    ip_proto=17,
                    udp_dst=UDP_PORT_STREAMING
                )
                actions = [parser.OFPActionOutput(1)]  # verso s2
                self.add_flow(datapath, priority=100, match=match, actions=actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        dst = eth.dst
        src = eth.src

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        # definizione porte host
        host_ports = {
            1: {1, 2},   # h1,h2
            4: {3, 4}    # h3,h4
        }

        # link "up" (UDP:9999)
        up_links = {
            1: {3},      # s1 -> s2
            2: {2},      # s2 -> s4
            3: set(),    # s3 non inoltra UDP
            4: {1}       # s4 -> s2
        }

        # link "down" (traffico normale)
        dw_links = {
            1: {4},      # s1 -> s3
            3: {2},      # s3 -> s4
            4: {2}       # s4 -> s3
        }

        actions = []

        # scelta dei link da usare
        link_set = up_links.get(dpid, set())
        
        ip4 = pkt.get_protocol(ipv4.ipv4)
        udp_pkt = pkt.get_protocol(udp.udp)
        
        bw_bps = self.get_port_bandwidth(1, 3)
        bw_mbps = bw_bps / 1_000_000
        
        udp_video = ip4 and ip4.proto == 17 and udp_pkt and udp_pkt.dst_port == UDP_PORT_STREAMING
        
        if udp_video:
            link_set = up_links.get(dpid, set())
        elif bw_bps < BANDWIDTH_THRESHOLD:
                self.logger.info(f"[DEBUG][SW{dpid}] Banda {bw_mbps:.2f} Mbps < soglia → uso link superiore {link_set}")
                link_set = up_links.get(dpid, set())  
        else:
            self.logger.info(f"[DEBUG][SW{dpid}] Banda {bw_mbps:.2f} Mbps > soglia → uso link inferiore {link_set}")
            link_set = dw_links.get(dpid, set())  


        # ora flood controllato solo se dobbiamo andare sul link inferiore
        actions = []
        if link_set == dw_links.get(dpid, set()):
            # flood controllato su host + link_set
            for p in host_ports.get(dpid, set()):
                if p != in_port:
                    actions.append(parser.OFPActionOutput(p))
            for p in link_set:
                if p != in_port:
                    actions.append(parser.OFPActionOutput(p))
        else:
            # MAC learning normale
            if dst in self.mac_to_port[dpid]:
                out_port = self.mac_to_port[dpid][dst]
                actions = [parser.OFPActionOutput(out_port)]
            else:
                # se non conosciamo ancora il MAC, possiamo fare flood controllato anche sul link superiore
                for p in host_ports.get(dpid, set()):
                    if p != in_port:
                        actions.append(parser.OFPActionOutput(p))
                for p in link_set:
                    if p != in_port:
                       actions.append(parser.OFPActionOutput(p))
       
        # invio pacchetto
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data
        )
        datapath.send_msg(out)


