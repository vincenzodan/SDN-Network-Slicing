from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ether_types

class SliceSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SliceSwitch, self).__init__(*args, **kwargs)
        # MAC degli host
        self.h1 = '00:00:00:00:00:01'
        self.h2 = '00:00:00:00:00:02'
        self.h3 = '00:00:00:00:00:03'
        self.h4 = '00:00:00:00:00:04'

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, flags=0):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            flags=flags
        )
        datapath.send_msg(mod)

    def add_mac_flow(self, datapath, src, dst, out_port, priority=10):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(eth_src=src, eth_dst=dst)
        actions = [parser.OFPActionOutput(out_port)]
        self.add_flow(datapath, priority, match, actions)

    def add_arp_flow(self, datapath, src_mac, out_port, priority=20):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(
            eth_src=src_mac,
            eth_dst='ff:ff:ff:ff:ff:ff',
            eth_type=0x0806
        )
        if isinstance(out_port, int):
            actions = [parser.OFPActionOutput(out_port)]
        else:
            actions = [parser.OFPActionOutput(p) for p in out_port]
        self.add_flow(datapath, priority, match, actions)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        dpid = datapath.id
        self.logger.info(f"[FEATURES] Configuring switch {dpid}")

        # s1
        if dpid == 1:
            # h1->h3 slice
            self.add_mac_flow(datapath, self.h1, self.h3, out_port=3)
            self.add_mac_flow(datapath, self.h3, self.h1, out_port=1)
            self.add_arp_flow(datapath, self.h1, 3)
            self.add_arp_flow(datapath, self.h3, 1)

            # h2->h4 slice
            self.add_mac_flow(datapath, self.h2, self.h4, out_port=4)
            self.add_mac_flow(datapath, self.h4, self.h2, out_port=2)
            self.add_arp_flow(datapath, self.h2, 4)
            self.add_arp_flow(datapath, self.h4, 2)

        # s2 (Up slice)
        elif dpid == 2:
            self.add_mac_flow(datapath, self.h1, self.h3, out_port=2)  # verso s4
            self.add_mac_flow(datapath, self.h3, self.h1, out_port=1)  # verso s1
            self.add_arp_flow(datapath, self.h1, 2)
            self.add_arp_flow(datapath, self.h3, 1)

        # s3 (Down slice)
        elif dpid == 3:
            self.add_mac_flow(datapath, self.h2, self.h4, out_port=2)  # verso s4
            self.add_mac_flow(datapath, self.h4, self.h2, out_port=1)  # verso s1
            self.add_arp_flow(datapath, self.h2, 2)
            self.add_arp_flow(datapath, self.h4, 1)

        # s4
        elif dpid == 4:
            # h1->h3 slice
            self.add_mac_flow(datapath, self.h1, self.h3, out_port=3)  # verso h3
            self.add_mac_flow(datapath, self.h3, self.h1, out_port=1)  # verso s2
            self.add_arp_flow(datapath, self.h1, 3)
            self.add_arp_flow(datapath, self.h3, 1)

            # h2->h4 slice
            self.add_mac_flow(datapath, self.h2, self.h4, out_port=4)  # verso h4
            self.add_mac_flow(datapath, self.h4, self.h2, out_port=2)  # verso s3
            self.add_arp_flow(datapath, self.h2, 4)
            self.add_arp_flow(datapath, self.h4, 2)

#Evita che il controller gestisca ARP, perchè già configurati staticamente

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        arp_pkt = pkt.get_protocol(arp.arp)

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        if arp_pkt:
            self.logger.info(f"[DROP ARP] {eth.src} -> {eth.dst}")

