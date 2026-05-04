#!/usr/bin/env python3
"""Serve a cropper HTML file from localhost so File System Access API works.
Usage: python3 serve_cropper.py <path_to_cropper.html> [port]
"""
import http.server, socketserver, sys, os, webbrowser, urllib.parse

if len(sys.argv) < 2:
    print("Usage: python3 serve_cropper.py <cropper.html> [port]")
    sys.exit(1)

html_file = os.path.abspath(sys.argv[1])
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
serve_dir = os.path.dirname(html_file)
filename = os.path.basename(html_file)

os.chdir(serve_dir)

handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", port), handler) as httpd:
    url = f"http://localhost:{port}/{urllib.parse.quote(filename)}"
    print(f"Serving at {url}")
    print(f"Directory: {serve_dir}")
    print("Press Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
