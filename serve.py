#!/usr/bin/env python3
import http.server, os
os.chdir('/Users/sebasandres/Desktop/the-brief-website')
http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port=8899, bind='127.0.0.1')
