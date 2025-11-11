#!/usr/bin/env python3
from mininet.log import setLogLevel, info
from topology import Environment  # importa la classe Environment dalla topologia

def run_tests():
    setLogLevel('info')

    # Avvio ambiente
    info("[TEST] Avvio rete dalla topologia\n")
    env = Environment()
    net = env.net

    # Prendo gli host
    h1 = net.get('h1')
    h2 = net.get('h2')
    h3 = net.get('h3')
    h4 = net.get('h4')

    # Lista test: (host_sorgente, host_destinazione, True=deve funzionare, False=deve FALLIRE)
    tests = [
        (h1, h3, True),
        (h3, h1, True),
        (h2, h4, True),
        (h4, h2, True),
        (h1, h2, False),
        (h1, h4, False),
        (h2, h3, False),
        (h3, h4, False)
    ]
    
    info('Pingall della rete:\n')
    net.pingAll()

    for src, dst, should_work in tests:
        info(f"\n[TEST] Ping da {src.name} a {dst.name} (deve {'funzionare' if should_work else 'FALLIRE'}):\n")
        result = src.cmd(f'ping -c 2 {dst.IP()}')
        info(result)

    # Ferma rete
    env.stop()
    info("[TEST] Rete fermata e pulita\n")


if __name__ == '__main__':
    run_tests()

