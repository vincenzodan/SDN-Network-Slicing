from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet, ipv4, udp

UDP_PORT_STREAMING = 9999

class RyuController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(RyuController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

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

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
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
        link_set = dw_links.get(dpid, set())
        ip4 = pkt.get_protocol(ipv4.ipv4)
        
        udp_video = ip4 and ip4.proto == 17 and udp_pkt and udp_pkt.dst_port == UDP_PORT_STREAMING
        
        if udp_video:
            link_set = up_links.get(dpid, set())
        
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            actions = [parser.OFPActionOutput(out_port)]
            self.logger.info(f"[LEARNING] dpid={dpid}, {src}->{dst}, out={out_port}")
        else:
            # flood controllato su host + link_set
            for p in host_ports.get(dpid, set()):
                if p != in_port:
                    actions.append(parser.OFPActionOutput(p))
            for p in link_set:
                if p != in_port:
                    actions.append(parser.OFPActionOutput(p))
            self.logger.info(f"[CONTROLLED FLOOD] dpid={dpid}, {src}->{dst}, out={[a.port for a in actions]}")

        # installazione flow se univoco
        if len(actions) == 1:
            match = parser.OFPMatch(in_port=in_port, eth_src=src, eth_dst=dst)
            self.add_flow(datapath, priority=1, match=match, actions=actions)

        # invio pacchetto
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data
        )
        datapath.send_msg(out)


