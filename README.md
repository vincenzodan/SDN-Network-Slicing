# 🖧 SDN Network Slicing

Questo progetto si concentra sulla gestione del traffico in reti Software Defined Network (SDN) tramite Mininet e controller Ryu, implementando diverse politiche di slicing per isolare e prioritizzare flussi di traffico.

- [Topology Slicing](./Topology_Slicing): implementa una rete slice-specifica dove determinati host comunicano solo attraverso percorsi prestabiliti.  
  • H1 comunica esclusivamente con H3 tramite lo slice superiore (upper path).  
  • H2 comunica esclusivamente con H4 tramite lo slice inferiore (lower path).  
  Include inoltre una dashboard per il monitoraggio visivo della rete.
- [Service Slicing](./Service_Slicing): separa il traffico video (UDP porta 9999) da quello normale, garantendo priorità ai pacchetti video.
- [Dynamic Slicing](./Dynamic_Slicing): permette al traffico normale di utilizzare temporaneamente lo slice video quando la banda disponibile lo consente, mantenendo sempre priorità al traffico video.

## 📘 Documentazione Tecnica

Consulta la [documentazione tecnica](./Documentazione.pdf) per dettagli completi sulla topologia, implementazione e test.

---
## 🛠️ Tecnologie

<table>
  <tr>
    <td align="center">
      <a href="https://www.python.org/" target="_blank">
        <img src="https://raw.githubusercontent.com/devicons/devicon/master/icons/python/python-original.svg" width="50" height="50"/><br>
        Python
      </a>
    </td>
    <td align="center">
      <a href="https://mininet.org/" target="_blank">
        <img width="50" height="50" alt="image" src="https://github.com/user-attachments/assets/6d83f1f6-baae-444a-9fba-bd53128c0bb2" /><br>
        Mininet
      </a>
    </td>
    <td align="center">
      <a href="https://ryu.readthedocs.io/" target="_blank">
        <img width="50" height="50" alt="image" src="https://github.com/user-attachments/assets/4c6910aa-764b-444a-b825-c2904dba548d" /><br>
        Ryu
      </a>
    </td>
  </tr>
</table>




## ⚙️ Prerequisiti

1. **VM Setup**
   - Installare VirtualBox, VMware o altro e creare una VM Ubuntu 22.04.

2. **Installazione pacchetti**
   Aprire il terminale sulla VM e lanciare i seguenti comandi:
   ```bash
   sudo apt update
   sudo apt install git
   sudo apt install python3-pip
   sudo pip3 install pandas
   pip install ryu
   sudo apt install d-itg
   sudo apt install nload
   ```
   
3. **Installazione Mininet**
    ```bash
   git clone https://github.com/mininet/mininet
   cd mininet
   git tag
   git checkout -b mininet-2.3.0 2.3.0
   cd ..
   sudo PYTHON=python3 mininet/util/install.sh -nv
   sudo mn --switch ovsbr --test pingall  # Test installazione
   ```

## 📖 Istruzioni per l'Esecuzione

1. **Avvio del controller**: Posizionarsi nella cartella del controller desiderato (Topology / Service / Dynamic) e avviare:
   ```bash
   ryu-manager controller_slicing.py # oppure controller_serv.py, controller_dynamic.py a seconda del caso
   ```
2. **Avvio della topologia**:
   ```bash
   sudo python3 topology.py
   ```

## 🧪 Verifica

- Eseguire pingall in Mininet per controllare la connettività di base.
- Generare traffico UDP/TCP/ICMP con iperf per testare separazione e priorità dei flussi.
- Usare Wireshark per monitorare i pacchetti e osservare il comportamento dei flussi e degli slice.

🗂️ Struttura del Progetto
.
├── Documentazione.pdf
├── README.md
├── Topology Slicing/
│   ├── topology.py
│   ├── controller_topo.py
│   └── dashboard/ (HTML, CSS, JS)
├── Service Slicing/
│   ├── topology.py
│   └── controller_serv.py
└── Dynamic Slicing/
    ├── topology.py
    └── controller_dynamic.py

👥 Contributors

@Vincenzo D'Angelo
