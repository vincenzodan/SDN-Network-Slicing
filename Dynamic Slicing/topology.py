
import threading
import random
import time
from mininet.log import setLogLevel, info
from mininet.topo import Topo
from mininet.net import Mininet, CLI
from mininet.node import OVSKernelSwitch, Host, Controller
from mininet.link import TCLink, Link
from mininet.node import RemoteController
from mininet.util import dumpNodeConnections

class Environment(object):
    def __init__(self):

        info("[NET-DEF] Starting controller\n")
    
        self.net = Mininet(controller=RemoteController, link=TCLink)
        c1 = self.net.addController( 'c1', controller=RemoteController, port=6653, ip='127.0.0.1') #Controller
        c1.start()

        info("[NET-DEF] Adding hosts and switches\n")

        self.h1 = self.net.addHost('h1', mac= '00:00:00:00:00:01', ip= '10.0.0.1')
        self.h2 = self.net.addHost('h2', mac= '00:00:00:00:00:02', ip= '10.0.0.2')
        self.h3 = self.net.addHost('h3', mac= '00:00:00:00:00:03', ip= '10.0.0.3')
        self.h4 = self.net.addHost('h4', mac= '00:00:00:00:00:04', ip= '10.0.0.4')

        self.s1 = self.net.addSwitch('s1')
        self.s2 = self.net.addSwitch('s2')
        self.s3 = self.net.addSwitch('s3')
        self.s4 = self.net.addSwitch('s4')
        
        
        info("[NET-DEF] Connecting hosts\n")  
        
        self.net.addLink(self.h1, self.s1, delay='0.01ms', port1=1, port2=1)
        self.net.addLink(self.h2, self.s1, delay='0.01ms', port1=1, port2=2)
        self.net.addLink(self.h3, self.s4, delay='0.01ms', port1=1, port2=3)
        self.net.addLink(self.h4, self.s4, delay='0.01ms', port1=1, port2=4)

        self.net.addLink(self.s1, self.s2, bw=10, delay='0.025ms', port1=3, port2=1)
        self.net.addLink(self.s2, self.s4, bw=10, delay='0.025ms', port1=2, port2=1)

        self.net.addLink(self.s1, self.s3, bw=1, delay='0.025ms', port1=4, port2=1)
        self.net.addLink(self.s3, self.s4, bw=1, delay='0.025ms', port1=2, port2=2)

        info("[NET-DEF] Starting network\n")
        self.net.build()
        self.net.start()
        
    def stop(self):
        """Ferma la rete e pulisce eventuali residui"""
        if hasattr(self, 'net'):
            from mininet.log import info
            import os
            info("[MAIN] Arresto rete\n")
            self.net.stop()
            os.system("mn -c")

if __name__ == '__main__':
    
    setLogLevel('info')
    info('[MAIN] Starting the environment\n')
    
    env = Environment()

    info("[MAIN] Running CLI\n")
    CLI(env.net)
