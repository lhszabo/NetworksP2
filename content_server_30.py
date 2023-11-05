
import socket, sys
import threading
import time
import heapq

BUFSIZE = 1024
TIME_TO_LIVE = 15
KEEP_ALIVE_HEADER = "keepalive"
LSA_HEADER = "LSA"
seq_num = 0
lock = threading.Lock() # for graph
uuid_map_lock = threading.Lock()
keep_rx = True
keep_tx = True
lsa_to_forward = []


class Network_node():
  def __init__(self, uuid, name, port, peers, graph, uuid_to_name):
    self.uuid = uuid
    self.name = name
    self.port = port
    self.peers = peers # dictionary of network_peer's where key is uuid
    self.graph = graph # current graph of whole network
    self.uuid_to_name = uuid_to_name # dictionary to fill in for official map
    self.host = None
    self.lsa_nums = dict()
    
class Network_peer():
  def __init__(self, host, port, metric):
    self.host = host
    self.port = port
    self.metric = metric
    self.last_keep_alive = time.time() # initialized in constructor
    self.name = None

class D_Node:
  def __init__(self):
      self.d=float('inf') #current distance from source node
      self.parent=None
      self.finished=False

def dijkstra(graph,source):
  # print('d graph', graph)
  nodes={}
  for node in graph:
      nodes[node]=D_Node()
  nodes[source].d=0
  queue=[(0,source)] #priority queue
  while queue:
      d,node=heapq.heappop(queue)
      if nodes[node].finished:
          continue
      nodes[node].finished=True
      for neighbor in graph[node]:
          if nodes[neighbor].finished:
              continue
          new_d=d+graph[node][neighbor]
          if new_d<nodes[neighbor].d:
              nodes[neighbor].d=new_d
              nodes[neighbor].parent=node
              heapq.heappush(queue,(new_d,neighbor))
  return nodes
      
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

def is_uuid(s):
  return "-" in s

def node_identifier(node):
  uuid = node.uuid
  res_dict = dict()
  res_dict["uuid"] = uuid
  return res_dict

def is_keep_alive(msg):
  # keep alive format: "KEEP_ALIVE_HEADER.name.host.port.metric"
  msg_fields = msg.split(".")
  keep_alive_header = msg_fields[0]
  return (keep_alive_header == KEEP_ALIVE_HEADER)

# contains necessary information for new neighbor added
def make_keep_alive(node):
  keep_alive = KEEP_ALIVE_HEADER + "." + node.name + "." + node.uuid + "." + node.host + "." + str(node.port) + "."
  return keep_alive

def parse_keep_alive(ka):
  msg_fields = ka.split(".")
  name = msg_fields[1]
  uuid = msg_fields[2]
  host = msg_fields[3]
  port = int(msg_fields[4])
  metric = int(msg_fields[5])
  return name, uuid, host, port, metric

def kill_nodes(node, dead_nodes):
  # permanently modifing peer dictionary
  new_peers = dict()
  for peer_uuid in node.peers:
    if (peer_uuid not in dead_nodes):
      new_peers[peer_uuid] = node.peers[peer_uuid]
  node.peers = new_peers
   
def reachability(node):
  res_dict = dict()
  res_dict["neighbors"] = dict()
  for peer_uuid in node.peers:
    peer_name = get_name(node, peer_uuid)
    peer = node.peers[peer_uuid]
    if (peer_name == None):
      peer_name = peer.name
    res_dict["neighbors"][peer_name] = dict()
    res_dict["neighbors"][peer_name]["uuid"] = peer_uuid
    res_dict["neighbors"][peer_name]["host"] = peer.host
    res_dict["neighbors"][peer_name]["backend_port"] = peer.port
    res_dict["neighbors"][peer_name]["metric"] = peer.metric
  return res_dict

def parse_new_neighbor(cmd):
  args = cmd.split(" ")
  uuid = None
  host = None
  port = None
  metric = None
  for i in range(1, len(args)):
    arg = args[i]
    arg = arg.strip()
    arg = arg.replace(" ", "")
    fields = arg.split("=")
    if ("uuid" in fields):
      uuid = fields[-1]
    elif ("host" in fields):
      host = fields[-1]
    elif ("backend_port" in fields):
      port = int(fields[-1])  
    elif ("metric" in fields):
      metric = int(fields[-1])  
  return uuid, host, port, metric
      
def add_neighbor_cmd(node, cmd):
  # place into our peers list
  # tx thread will automatically start sending keep alive messages 
  # "automatic detection" from other neighbor accomplished by LSAs 
  uuid, host, port, metric =  parse_new_neighbor(cmd)
  node.peers[uuid] = Network_peer(host, port, metric)
  return

def add_neighbor_ka(node, name, uuid, host, port, metric):
  node.peers[uuid] = Network_peer(host, port, metric)
  node.peers[uuid].name = name
  with uuid_map_lock:
    node.uuid_to_name[uuid] = name

def make_lsa(node):
  lsa = LSA_HEADER + "."+ node.name + "."
  for peer_uuid in node.peers:
    peer = node.peers[peer_uuid]
    peer_name = get_name(node, peer_uuid)
    if (peer_name != None):
      peer_uuid = peer_name
    edge = peer_uuid + ":" + str(peer.metric) + ","
    lsa += edge
  final_lsa = lsa[:-1] # disregard final comma
  global seq_num
  final_lsa += "." + str(seq_num)
  seq_num += 1
  return final_lsa

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

def get_name(node, neighbor_uuid):
  if (neighbor_uuid in node.uuid_to_name):
    return node.uuid_to_name[neighbor_uuid]
  else:
    return None

def update_uuid_to_name(node, key, metric):
  # looking for node.graph[node.name][uuid -> key] = metric
  if not (is_uuid(key)):
    own_neighbors = node.graph[node.name]
    for neighbor in own_neighbors:
      if (own_neighbors[neighbor] == metric and is_uuid(neighbor)):
        with uuid_map_lock:
          node.uuid_to_name[neighbor] = key
 
def sub_own_name_key(node, named_graph):
  final_graph = dict()
  for key in named_graph:
    connections = named_graph[key]
    final_graph[key] = dict()
    for conn in connections:
      conn_name = get_name(node, conn) 
      named_conn = conn
      if (conn_name != None):
        named_conn = conn_name
      metric = named_graph[key][conn]
      final_graph[key][named_conn] = metric
      if (named_conn == node.name):
        update_uuid_to_name(node, key, metric)
  return final_graph

def sub_own_name(node, lsa_graph):
  named_graph = dict()
  for neighbor in lsa_graph:
    neighbor_name = get_name(node, neighbor)
    named_key = neighbor
    if (neighbor_name != None):
      named_key = neighbor_name
    named_graph[named_key] = lsa_graph[neighbor]
  final_graph = sub_own_name_key(node, named_graph)
  return final_graph

def construct_peer_graph(node):
  peer_graph = dict()
  for peer_uuid in node.peers:
    peer = node.peers[peer_uuid]
    peer_key = peer_uuid
    if (peer.name != None):
      peer_key = peer.name
    peer_graph[peer_key] = peer.metric
  return peer_graph
    
def update_own_graph(node):
  peer_graph = construct_peer_graph(node)
  with lock:
    node.graph[node.name] = peer_graph
          
def update_graph(node, sender_name, lsa_graph, cur_seq_num, msg, socket):
  # if seq number higher than last lsa -> update
  # otherwise, disregard
  if (sender_name not in node.lsa_nums):
    node.lsa_nums[sender_name] = (cur_seq_num, msg)
  else:
    last_lsa = node.lsa_nums[sender_name][0]
    if not (cur_seq_num > last_lsa):
      return
    else:
      node.lsa_nums[sender_name] = (cur_seq_num, msg)
  
  # substitute own name in received lsa for uuid
  named_graph = sub_own_name(node, lsa_graph)
  update_own_graph(node)
  # substitute known names in own graph
  named_cur_graph = sub_own_name(node, node.graph)
  
  for key in named_graph:
    if (key not in named_cur_graph):
      named_cur_graph[key] = named_graph[key]
  with lock:
    node.graph = named_cur_graph
       
def get_map(node):
  # replace all uuid's with names
  cur_graph = node.graph
  return {"map": cur_graph}

def make_graph_bidirectional(cur_graph):
  bi_graph = dict()
  for cur_node in cur_graph:
    bi_graph[cur_node] = cur_graph[cur_node]
    conns = cur_graph[cur_node]
    for conn in conns:
      metric = conns[conn]
      if (conn not in cur_graph):
        bi_graph[conn] = {cur_node: metric}
  return bi_graph
    
def rank(node):
  cur_graph = node.graph
  d_graph = make_graph_bidirectional(cur_graph)
  # shortest_paths = dijkstra(d_graph, node.name)
  # rank_dict = dict()
  # for named_node in shortest_paths:
  #   if (named_node != node.name):
  #     rank_dict[named_node] = shortest_paths[named_node].d
  return {"rank": dict()}

def rx_thread(name, socket, node):
  while (keep_rx):
    msg, addr = socket.recvfrom(BUFSIZE)
    msg = msg.decode()

    dead_nodes = []
    if (is_keep_alive(msg)):
      name, uuid, host, port, metric = parse_keep_alive(msg)
      if (uuid in node.peers):
        node.peers[uuid].last_keep_alive = time.time()
        node.peers[uuid].name = name
      else:
        # seeing new uuid
        add_neighbor_ka(node, name, uuid, host, port, metric)
    if (is_lsa(msg)):
      sender_name, lsa_graph, cur_seq_num = parse_lsa(msg)
      update_graph(node, sender_name, lsa_graph, cur_seq_num, msg, socket)
    for peer_uuid in node.peers:
      peer = node.peers[peer_uuid]
      cur_time = time.time()
      last_keep_alive = peer.last_keep_alive
      # if you miss three consecutive keep alive's -> dead
      if (abs(last_keep_alive - cur_time) >= TIME_TO_LIVE):
        dead_nodes.append(peer_uuid)
    kill_nodes(node, dead_nodes)  
       
def tx_thread(name, socket, node):
  while (keep_tx):
    for sender_name in node.lsa_nums:
      cur_lsa = node.lsa_nums[sender_name][1]
      for peer_uuid in node.peers:
        peer = node.peers[peer_uuid]
        addr = peer.host
        port = peer.port
        try:
          socket.sendto(cur_lsa.encode(), (addr, port))
        except Exception as e:
          pass
    lsa = make_lsa(node)
    for peer_uuid in node.peers:
      keep_alive = make_keep_alive(node)
      peer = node.peers[peer_uuid]
      addr = peer.host
      port = peer.port
      keep_alive += str(peer.metric)
      try:
        socket.sendto(keep_alive.encode(), (addr, port))
      except Exception as e:
        pass
      try:
        socket.sendto(lsa.encode(), (addr, port))
      except Exception as e:
        pass 
    time.sleep(1)
  
if __name__ == '__main__':
  conf_file = None
  if len(sys.argv) != 3:
    sys.exit(-1)
  else:
    flag = sys.argv[1]
    if (flag == "-c"):
      conf_file = sys.argv[2] # -c flag
    
  node = parse_conf(conf_file)
  local_host = "localhost"
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
      keep_rx = False
      keep_tx = False
      break