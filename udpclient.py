#!/usr/bin/env python3
# 18-441/741 UDP Server
# It keeps receiving messages from possible clients
# And echoes back

import socket, sys

SERVER_HOST = '' # Symbolic name, meaning all available interfaces
BUFSIZE = 1024 # size of receiving buffer

if __name__ == '__main__':
  # get server information from keyboard input
  if len(sys.argv) < 3:
    print('Format: python3 /path/udpclient.py <server_ip_address> <server_port_number>\nExiting...')
    sys.exit(-1)
  else:
    server_address = sys.argv[1]
    server_port = int(sys.argv[2])
    
  # create socket
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  
  # get message from keyboard
  msg_string = input('Send this to the server: ')
  
  # send message to server
  s.sendto(msg_string.encode(), (server_address, server_port))
  
  # get echo message
  echo_string, addr = s.recvfrom(BUFSIZE)
  
  # print echo message
  print('Echo from the server: '+echo_string.decode())
  
  # exit
  s.close()
  sys.exit(0)
