# app.py

import sys
import os
import threading
import queue
import asyncio
import websockets

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5 import QtWebEngineWidgets
from PyQt5.QtCore import QUrl, QObject, pyqtSignal, Qt # <-- MODIFIED
from PyQt5.QtNetwork import QUdpSocket, QHostAddress

# --- Web Server Imports ---
import http.server
import socketserver

# --- Configuration ---
HTTP_PORT = 8000          # Port for serving HTML file
WEBSOCKET_PORT = 8765   # Port for streaming audio data to browser
COMMAND_UDP_PORT = 45454  # Port for receiving commands (listening, etc.)
LOUDNESS_UDP_PORT = 45455 # Port for receiving loudness data from vad.py

# A thread-safe queue to pass loudness data from the UDP thread to the websocket thread
loudness_queue = queue.Queue()

# --- 1. WebSocket Server ---
clients = set()

async def loudness_broadcaster(q):
    """Pulls loudness data from the queue and sends it to all connected WebSocket clients."""
    while True:
        try:
            # Use asyncio.to_thread for non-blocking queue access
            loudness = await asyncio.to_thread(q.get)
            if clients:
                # Use asyncio.gather for efficient sending to multiple clients
                await asyncio.gather(*[client.send(str(loudness)) for client in clients])
        except Exception as e:
            print(f"Error in WebSocket broadcast loop: {e}")
            await asyncio.sleep(1)

async def handler(websocket, path):
    """Handles new WebSocket connections."""
    print(f"JavaScript client connected from {websocket.remote_address}")
    clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        print("JavaScript client disconnected.")
        clients.remove(websocket)

def run_websocket_server(q):
    """Sets up and runs the asyncio event loop for the WebSocket server."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    start_server = websockets.serve(handler, "localhost", WEBSOCKET_PORT)
    
    # Run both the server and the data broadcaster concurrently
    loop.run_until_complete(asyncio.gather(start_server, loudness_broadcaster(q)))
    loop.run_forever()


# --- 2. PyQt Main Application ---
class MainWindow(QMainWindow):
    def __init__(self, loudness_q):
        super().__init__()
        self.loudness_q = loudness_q
        self.setWindowTitle("Feelings App - Central Control")
        self.setGeometry(100, 100, 800, 600)

        # Combine all necessary flags
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        # --- NEW: MAKE THE WINDOW BACKGROUND TRANSPARENT ---
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.view = QtWebEngineWidgets.QWebEngineView()
        self.page = self.view.page()

        # --- NEW: MAKE THE WEB VIEW BACKGROUND TRANSPARENT ---
        self.page.setBackgroundColor(Qt.transparent)

        # Serve the HTML file via a simple HTTP server
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.http_server = http.server.HTTPServer(("", HTTP_PORT), http.server.SimpleHTTPRequestHandler)
        self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
        self.http_thread.start()
        print(f"Serving HTML on http://localhost:{HTTP_PORT}")
        
        self.view.load(QUrl(f"http://localhost:{HTTP_PORT}/html_files/app.html"))
        self.setCentralWidget(self.view)
        
        # ... the rest of your __init__ method is unchanged ...
        self.command_socket = QUdpSocket(self)
        self.command_socket.bind(QHostAddress.LocalHost, COMMAND_UDP_PORT)
        self.command_socket.readyRead.connect(self.process_command_datagrams)
        print(f"Listening for commands on UDP port {COMMAND_UDP_PORT}")

        self.loudness_socket = QUdpSocket(self)
        self.loudness_socket.bind(QHostAddress.LocalHost, LOUDNESS_UDP_PORT)
        self.loudness_socket.readyRead.connect(self.process_loudness_datagrams)
        print(f"Listening for loudness on UDP port {LOUDNESS_UDP_PORT}")
    # --- ADD A WAY TO CLOSE THE FRAMELESS WINDOW ---
    def keyPressEvent(self, event):
        """Closes the application when the Escape key is pressed."""
        if event.key() == Qt.Key_Escape:
            self.close()

    def process_command_datagrams(self):
        """Receives a command (e.g., 'listening') and passes it to the JavaScript UI."""
        while self.command_socket.hasPendingDatagrams():
            datagram = self.command_socket.receiveDatagram()
            command = bytes(datagram.data()).decode('utf-8').strip()
            print(f"Received command: '{command}'")
            self.page.runJavaScript(f"setMode('{command}');")

    def process_loudness_datagrams(self):
        """Receives loudness data and puts it in the queue for the WebSocket server."""
        while self.loudness_socket.hasPendingDatagrams():
            datagram = self.loudness_socket.receiveDatagram()
            try:
                # The data is the loudness value, e.g., "0.453"
                loudness_str = bytes(datagram.data()).decode('utf-8').strip()
                loudness_val = float(loudness_str)
                # Put it in the queue to be broadcast by the other thread
                self.loudness_q.put(loudness_val)
            except (ValueError, UnicodeDecodeError) as e:
                print(f"Could not parse loudness data: {e}")

    def closeEvent(self, event):
        """Ensure the HTTP server is shut down when the window closes."""
        print("Shutting down servers and closing application...")
        self.http_server.shutdown()
        super().closeEvent(event)


# --- Main Execution ---
if __name__ == '__main__':
    # Start the WebSocket server thread
    # It will broadcast data placed into the loudness_queue
    websocket_thread = threading.Thread(target=run_websocket_server, args=(loudness_queue,), daemon=True)
    websocket_thread.start()

    # Start the PyQt GUI
    # It listens for UDP and puts data into the loudness_queue
    app = QApplication(sys.argv)
    window = MainWindow(loudness_queue)
    window.show()
    sys.exit(app.exec_())
