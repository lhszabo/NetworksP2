import socket, sys
import threading
import time

BUFSIZE = 1024
TIME_TO_LIVE = 15
KEEP_ALIVE_HEADER = "keepalive"
LSA_HEADER = "LSA"
seq_num = 0
lock_peers = threading.Lock()
lock_graph = threading.Lock()

class Network_node():
  def __init__(self, uuid, name, port, peers, graph, uuid_to_name):
    self.uuid = uuid
    self.name = name
    self.port = port
    self.peers = peers # dictionary of network_peer's where key is uuid
    self.graph = graph # current graph of whole network
    self.uuid_to_name = uuid_to_name # dictionary to fill in for official map
    self.host = None
    
class Network_peer():
  def __init__(self, host, port, metric):
    self.host = host
    self.port = port
    self.metric = metric
    self.last_keep_alive = time.time() # initialized in constructor
    self.last_lsa = -1
    
def parse_conf(conf_file):
  f = open(conf_file, "r")
  info = f.readlines()
  uuid = None
  name = None
  port = None
  peers = dict() # map uuid's to network_peers
  check_peers = False
  graph = dict()
  uuid_to_name = dict()
  for line in info:
    # handling trailing whitespace and missing spaces
    line = line.strip()
    line = line.replace(" ", "")
    fields = line.split("=")
    if ("uuid" in fields):
      uuid = fields[-1]
    elif ("name" in fields):
      name = fields[-1]  
      graph[name] = dict()
    elif ("backend_port" in fields):
      port = int(fields[-1]) 
    elif ("peer_count" in fields):
      check_peers = True
    elif (check_peers):
      peer = fields[-1]
      peer = peer.replace(" ", "")
      peer_info = peer.split(",")
      peer_uuid = peer_info[0]
      peer_host = peer_info[1]
      peer_port = int(peer_info[2])
      peer_metric = int(peer_info[3])
      new_peer = Network_peer(peer_host, peer_port, peer_metric)
      peers[peer_uuid] = new_peer
      graph[name][peer_uuid] = peer_metric
  uuid_to_name[uuid] = name
  new_node = Network_node(uuid, name, port, peers, graph, uuid_to_name)
  return new_node

def node_identifier(node):
  uuid = node.uuid
  res_dict = dict()
  res_dict["uuid"] = uuid
  return res_dict

def make_keep_alive(node):
  keep_alive = KEEP_ALIVE_HEADER + "." + node.name + "." + node.uuid + "." + node.host + "." + str(node.port) + "."
  return keep_alive

def is_keep_alive(msg):
  # keep alive format: "KEEP_ALIVE_HEADER.name.host.port.metric"
  msg_fields = msg.split(".")
  keep_alive_header = msg_fields[0]
  return (keep_alive_header == KEEP_ALIVE_HEADER)

def parse_keep_alive(ka):
  msg_fields = ka.split(".")
  name = msg_fields[1]
  uuid = msg_fields[2]
  host = msg_fields[3]
  port = int(msg_fields[4])
  metric = int(msg_fields[5])
  return name, uuid, host, port, metric

def add_neighbor_ka(node, name, uuid, host, port, metric):
  node.peers[uuid] = Network_peer(host, port, metric)
  node.peers[uuid].name = name
  node.uuid_to_name[uuid] = name 

def kill_peers(node, dead_nodes):
  new_peers = dict()
  for peer_uuid in node.peers:
    if (peer_uuid not in dead_nodes):
      new_peers[peer_uuid] = node.peers[peer_uuid]
  return new_peers

def kill_graph(node, dead_nodes):
  new_graph = dict()
  cur_graph = node.graph
  for neighbor in cur_graph:
    if (neighbor not in dead_nodes):
      conns = cur_graph[neighbor]
      for conn in conns:
        if (conn not in dead_nodes):
          new_graph[neighbor] = dict()
          new_graph[neighbor][conn] = cur_graph[neighbor][conn] 
  return new_graph
   
def kill_nodes(node, dead_nodes):
  # permanently modifing peer dictionary
  new_peers = kill_peers(node, dead_nodes)
  with lock_peers:
    node.peers = new_peers
  new_graph = kill_graph(node, dead_nodes)
  with lock_graph:
    node.graph = new_graph
    
def is_lsa(msg):
  msg_fields = msg.split(".")
  return msg_fields[0] == LSA_HEADER

# make message back into dictionary
def parse_lsa(msg):
  msg = msg.split(".")
  sender_name = msg[1]
  cur_seq_num = int(msg[-1])
  edges = msg[2].split(",")
  lsa_graph = {sender_name: dict()}
  for edge in edges:
    edge = edge.split(":")
    end = edge[0]
    metric = int(edge[1])
    lsa_graph[sender_name][end] = metric 
  return sender_name, lsa_graph, cur_seq_num

def is_uuid(s):
  return "-" in s

def get_uuid(node, sender_name):
  for uuid in node.uuid_to_name:
    name = node.uuid_to_name[uuid]
    if (name == sender_name):
      return uuid
  return None

def get_name(node, neighbor_uuid):
  if (neighbor_uuid in node.uuid_to_name):
    return node.uuid_to_name[neighbor_uuid]
  else:
    return None

def update_uuid_to_name(node, key, metric):
  # looking for node.graph[node.name][uuid -> key] = metric
  own_neighbors = node.graph[node.name]
  for neighbor in own_neighbors:
    if (own_neighbors[neighbor] == metric and is_uuid(neighbor)):
      node.uuid_to_name[neighbor] = key

# def update_dict(node, named_graph):
#   for key in named_graph:
#     connections = named_graph[key]
#     for conn in connections:
#       conn_name = get_name(node, conn) 
#       named_conn = conn
#       if (conn_name != None):
#         named_conn = conn_name
#       metric = named_graph[key][conn]
#       if (named_conn == node.name):
#         update_uuid_to_name(node, key, metric)

def check_edge_peers(node, metric, name):
  for peer_uuid in node.peers:
    peer = node.peers[peer_uuid]
    if (peer.metric == metric):
      # print('hello')
      peer.name = name
      node.uuid_to_name[peer_uuid] = name
      return 

# lsa_graph has node name subbed in
def update_uuid_to_name(node, named_lsa_graph):
  for neighbor in named_lsa_graph:
    conns = named_lsa_graph[neighbor]
    for conn in conns:
      # check if same edge with same metric in peers
      # print('conn', conn)
      # print('node name', node.name)
      if (get_name(node, conn) == node.name):
        # print('in here')
        metric = named_lsa_graph[neighbor][conn]
        check_edge_peers(node, metric, neighbor)
      

# def sub_own_name(node, lsa_graph):
#   named_graph = dict()
#   for neighbor in lsa_graph:
#     neighbor_name = get_name(node, neighbor)
#     named_key = neighbor
#     if (neighbor_name != None):
#       named_key = neighbor_name
#     named_graph[named_key] = lsa_graph[neighbor]
#   final_graph = sub_own_name_key(node, named_graph)
#   return final_graph

# def name_cur_graph(node):
#   new_graph = dict()
#   cur_graph = node.graph
#   for key in cur_graph:
#     if (get_name(key) != None):
#       new_graph[get_name(key)] = dict()
      
def replace_keys(old_dict, key_dict):
  new_dict = { }
  for key in old_dict.keys():
      new_key = key_dict.get(key, key)
      if isinstance(old_dict[key], dict):
          new_dict[new_key] = replace_keys(old_dict[key], key_dict)
      else:
          new_dict[new_key] = old_dict[key]
  return new_dict

def sub_name(node, cur_graph):
  final_graph = dict()
  for neighbor in cur_graph:
    if (neighbor in node.uuid_to_name):
      final_graph[node.uuid_to_name[neighbor]] = dict()
      conns = cur_graph[neighbor]
      for conn in conns:
        if (conn in node.uuid_to_name):
          final_graph[node.uuid_to_name[neighbor]][node.uuid_to_name[conn]] = cur_graph[neighbor][conn]
        else:
          final_graph[node.uuid_to_name[neighbor]][conn] = cur_graph[neighbor][conn]    
    else:
      final_graph[neighbor] = dict()
      conns = cur_graph[neighbor]
      for conn in conns:
        if (conn in node.uuid_to_name):
          final_graph[neighbor][node.uuid_to_name[conn]] = cur_graph[neighbor][conn]
        else:
          final_graph[neighbor][conn] = cur_graph[neighbor][conn]  
  return final_graph
      
    
    
def update_graph(node, sender_name, lsa_graph, cur_seq_num):
  # if seq number higher than last lsa -> update
  # otherwise, disregard
  sender_uuid = get_uuid(node, sender_name)
  if (sender_uuid != None):
    last_seq = node.peers[sender_uuid].last_lsa
    if (cur_seq_num <= last_seq):
      return
  # substitute own name in received lsa for uuid
  named_graph = replace_keys(lsa_graph, node.uuid_to_name)
  # print('named lsa graph', named_graph)
  update_uuid_to_name(node, lsa_graph)
  # print('uuid to name', node.uuid_to_name)
  # substitute known names in own graph
  named_cur_graph = sub_name(node, node.graph)
  print('named own graph', named_cur_graph)
  
  for key in named_graph:
    if (key not in named_cur_graph):
      named_cur_graph[key] = named_graph[key]
  node.graph = named_cur_graph
  print("updated graph", node.graph)
  
def make_lsa(node):
  lsa = LSA_HEADER + "."+ node.name + "."
  for peer_uuid in node.peers:
    peer = node.peers[peer_uuid]
    edge = peer_uuid + ":" + str(peer.metric) + ","
    lsa += edge
  final_lsa = lsa[:-1] # disregard final comma
  global seq_num
  final_lsa += "." + str(seq_num)
  seq_num += 1
  return final_lsa
  
def reachability(node):
  res_dict = dict()
  res_dict["neighbors"] = dict()
  for peer_uuid in node.peers:
    peer = node.peers[peer_uuid]
    peer_name = peer.name
    res_dict["neighbors"][peer_name] = dict()
    res_dict["neighbors"][peer_name]["uuid"] = peer_uuid
    res_dict["neighbors"][peer_name]["host"] = peer.host
    res_dict["neighbors"][peer_name]["backend_port"] = peer.port
    res_dict["neighbors"][peer_name]["metric"] = peer.metric
  return res_dict

def add_neighbor_cmd(node, cmd):
  return 

def get_map(node):
  return {"map": dict()}

def rank(node):
  return {"rank": dict()}

def tx_thread(name, socket, node):
  while True:
    keep_alive = make_keep_alive(node)
    lsa = make_lsa(node)
    for peer_uuid in node.peers:
      peer = node.peers[peer_uuid]
      addr = peer.host
      port = peer.port
      keep_alive += str(peer.metric)
      try:
        socket.sendto(keep_alive.encode(), (addr, port))
      except Exception as e:
        print(f"Error sending data: {str(e)}")
      try:
        socket.sendto(lsa.encode(), (addr, port))
      except Exception as e:
        print(f"Error sending data: {str(e)}")  
    time.sleep(3)
    
def rx_thread(name, socket, node):
  while True:
    msg, addr = socket.recvfrom(BUFSIZE)
    msg = msg.decode()
    
    dead_nodes = []
    if (is_keep_alive(msg)):
      name, uuid, host, port, metric = parse_keep_alive(msg)
      if (uuid in node.peers):
        node.peers[uuid].last_keep_alive = time.time()
      else:
        # seeing new uuid
        # TO TEST WHEN ADDING NEIGHBORS
        add_neighbor_ka(node, name, uuid, host, port, metric)
    if (is_lsa(msg)):
      sender_name, lsa_graph, cur_seq_num = parse_lsa(msg)
      print('LSA', sender_name, lsa_graph, cur_seq_num)
      with lock_graph:
        update_graph(node, sender_name, lsa_graph, cur_seq_num)
        time.sleep(1) # found online, don't know if necessary with lock
    for peer_uuid in node.peers:
      peer = node.peers[peer_uuid]
      cur_time = time.time()
      last_keep_alive = peer.last_keep_alive
      # if you miss three consecutive keep alive's -> dead
      if (abs(last_keep_alive - cur_time) >= TIME_TO_LIVE):
        dead_nodes.append(peer_uuid)
    kill_nodes(node, dead_nodes)  

if __name__ == '__main__':
  conf_file = None
  if len(sys.argv) != 3:
    sys.exit(-1)
  else:
    flag = sys.argv[1]
    if (flag == "-c"):
      conf_file = sys.argv[2] # -c flag
    
  node = parse_conf(conf_file)
  local_host = "127.0.0.1"
  node.host = local_host
    
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.bind((local_host, node.port))
  
  tx = threading.Thread(target=tx_thread, args=(1, s, node), daemon=True)
  tx.start()
  
  rx = threading.Thread(target=rx_thread, args=(2, s, node), daemon=True)
  rx.start()
  
  while True:
    cmd = input()
    cmd = cmd.rstrip()
    if (cmd == "uuid"):
      print(node_identifier(node))
    elif (cmd == "neighbors"):
      print(reachability(node))
    elif ("addneighbor" in cmd):
      add_neighbor_cmd(node, cmd)
    elif (cmd == "map"):
      print(get_map(node))
    elif (cmd == "rank"):
      print(rank(node))
    elif (cmd == "kill"):
      pass