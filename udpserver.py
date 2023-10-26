#!/usr/bin/env python3
# 18-441/741 UDP Server
# It keeps receiving messages from possible clients
# And echoes back
import socket, sys

SERVER_HOST = '' # Symbolic name, meaning all available interfaces
BUFSIZE = 1024 # size of receiving buffer

if __name__ == '__main__':
  # get server port from keyboard input
  if len(sys.argv) < 2:
    print('Format: python3 /path/udpserver.py <port_number>\nExiting...')
    sys.exit(-1)
  else:
    SERVER_PORT = int(sys.argv[1])
    
  # create socket
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.bind((socket.gethostname(), SERVER_PORT))
  
  # main loop
  while True:
    # accept a packet
    dgram, addr = s.recvfrom(BUFSIZE)
    dgram = dgram.decode()
    # print the message
    print('New connection from '+str(addr[0])+':'+str(addr[1])+'; Message:'+dgram)
    # echo the message back
    s.sendto(dgram.encode(), addr)
    
  # exit
  s.close()
  sys.exit(0)
