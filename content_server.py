import socket, sys
import threading
import time

BUFSIZE = 1024

class Network_node():
  def __init__(self, uuid, name, backend_port, peers):
    self.uuid = uuid
    self.name = name
    self.backend_port = backend_port
    self.peers = peers # dictionary of network_peer's where key is uuid
    
class Network_peer():
  def __init__(self, server_addr, backend_port, dist):
    self.server_addr = server_addr
    self.backend_port = backend_port
    self.dist = dist
    self.alive = True
    
def parse_conf(conf_file):
  f = open(conf_file, "r")
  info = f.readlines()
  uuid = None
  name = None
  backend_port = None
  peers = dict() # map uuid's to network_peers
  check_peers = False
  for line in info:
    # handling trailing whitespace and missing spaces
    line = line.strip()
    line = line.replace(" ", "")
    fields = line.split("=")
    if ("uuid" in fields):
      uuid = fields[-1]
      
    if ("name" in fields):
      name = fields[-1]
      
    if ("backend_port" in fields):
      backend_port = int(fields[-1])
      
    if ("peer_count" in fields):
      check_peers = True
      
    elif (check_peers):
      peer = fields[-1]
      peer = peer.replace(" ", "")
      peer_info = peer.split(",")
      peer_uuid = peer_info[0]
      peer_server_addr = peer_info[1]
      peer_port = int(peer_info[2])
      peer_dist = int(peer_info[3])
      new_peer = Network_peer(peer_server_addr, peer_port, peer_dist)
      peers[peer_uuid] = new_peer
      
    new_node = Network_node(uuid, name, backend_port, peers)
  return new_node

def node_identifier(node):
  uuid = node.uuid
  res_dict = dict()
  res_dict["uuid"] = uuid
  return res_dict

def rx_thread(name, socket):
  while True:
    rx_string, addr = socket.recvfrom(BUFSIZE)
    print('rx', rx_string.decode())
  
def tx_thread(name, socket, node):
  while True:
    '''
    keep alive messages:
    - send roughly every 3 seconds
    - assure neighbors you are alive -> broadcast current uuid 
    - for all neighbors IF they are also alive 
    '''
    msg = node.uuid
    for peer_uuid in node.peers:
      peer = node.peers[peer_uuid]
      if (peer.alive):
        addr = peer.server_addr
        port = peer.backend_port
        socket.sendto(msg.encode(), (addr, port))
    time.sleep(3)
  
if __name__ == '__main__':
  if len(sys.argv) < 2:
    print('Format: python3 /path/udpserver.py <conf_file>\nExiting...')
    sys.exit(-1)
  else:
    conf_file = sys.argv[1]
    
  node = parse_conf(conf_file)
  server_address = "127.0.0.1"
    
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.bind((server_address, node.backend_port))
    
  # two theads: one receiving requests, one sending requests
  
  tx = threading.Thread(target=tx_thread, args=(1,s, node), daemon=True)
  tx.start()
  
  rx = threading.Thread(target=rx_thread, args=(2,s), daemon=True)
  rx.start()
  
  
  while True:
    for line in sys.stdin:
      cmd = line.rstrip()
      if (cmd == "uuid"):
        print(node_identifier(node))
        
  
  
  
  
  