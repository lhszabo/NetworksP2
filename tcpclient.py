#!/usr/bin/env python3
# 18-441/741 TCP Client
import socket, sys

BUFSIZE = 1024 # size of receiving buffer

if __name__ == '__main__':
  # get server information from keyboard input
  if len(sys.argv) < 3:
    print('Format: python3 /path/tcpclient.py <server_ip_address> <server_port_number>\nExiting...')
    sys.exit(-1)
  else:
    server_address = sys.argv[1]
    server_port = int(sys.argv[2])
    
  # create socket
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  
  # connect to server
  s.connect((server_address, server_port))
  
  # get message from keyboard
  msg_string = input('Send this to the server: ')
  
  # send message to server
  s.send(msg_string.encode())
  
  # get echo message
  echo_string = s.recv(BUFSIZE).decode()
  
  # print echo message
  print('Echo from the server: '+echo_string)
  # exit
  s.close()
  sys.exit(0)
