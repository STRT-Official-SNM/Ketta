# app.py

import sys
import os
import threading
import queue
import asyncio
import websockets
import time
import control

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5 import QtWebEngineWidgets, QtGui, QtCore
from PyQt5.QtCore import QUrl, QObject, pyqtSlot, Qt
from PyQt5.QtNetwork import QUdpSocket, QHostAddress

# --- Web Server Imports ---
import http.server
import socketserver

# --- Configuration ---
HTTP_PORT = 8000
WEBSOCKET_PORT = 8765
COMMAND_UDP_PORT = 45454
LOUDNESS_UDP_PORT = 45455

loudness_queue = queue.Queue()

# --- 1. WebSocket Server ---
clients = set()
async def loudness_broadcaster(q):
    while True:
        try:
            loudness = await asyncio.to_thread(q.get)
            if clients:
                await asyncio.gather(*[client.send(str(loudness)) for client in clients])
        except Exception:
            await asyncio.sleep(1)

async def handler(websocket, path):
    clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        clients.remove(websocket)

def run_websocket_server(q):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    start_server = websockets.serve(handler, "localhost", WEBSOCKET_PORT)
    loop.run_until_complete(asyncio.gather(start_server, loudness_broadcaster(q)))
    loop.run_forever()

# --- 2. Custom WebEnginePage to Intercept Clicks ---
class ClickableWebEnginePage(QtWebEngineWidgets.QWebEnginePage):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        # We need a reference to the main window to call its methods
        self.main_window = window

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        """
        This method is called every time the web page wants to navigate.
        We check for our custom URL scheme here.
        """
        # Check if the URL scheme is our special signal
        if url.scheme() == 'ketta-signal':
            # Check the "host" part of the url for the command
            if url.host() == 'click':
                print("Click signal received from JavaScript via URL.")
                # Perform the desired Python actions
                self.main_window.hide()
                control.send_tts_command('stop_audio')
                self.main_window.page.runJavaScript("setMode('reset');")

            # Block the navigation from actually happening
            return False
        
        # For all other URLs (http, etc.), allow them to proceed normally.
        return super().acceptNavigationRequest(url, _type, isMainFrame)


# --- 3. PyQt Main Application ---
class MainWindow(QMainWindow):
    def __init__(self, loudness_q):
        super().__init__()
        self.loudness_q = loudness_q
        
        self.setWindowIcon(QtGui.QIcon('logo.png'))
        self.setWindowTitle('Ketta')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.view = QtWebEngineWidgets.QWebEngineView()
        
        # Use our custom page class instead of the default one
        self.page = ClickableWebEnginePage(self)
        self.view.setPage(self.page)

        self.page.setBackgroundColor(Qt.transparent)

        # -- Setup Local Web Server --
        base_dir = os.path.dirname(os.path.abspath(__file__))
        html_dir = os.path.join(base_dir, 'html_files')
        os.makedirs(html_dir, exist_ok=True)
        
        os.chdir(html_dir)
        self.http_server = http.server.HTTPServer(("", HTTP_PORT), http.server.SimpleHTTPRequestHandler)
        self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
        self.http_thread.start()
        
        self.view.load(QUrl(f"http://localhost:{HTTP_PORT}/html_files/app.html"))
        self.setCentralWidget(self.view)
        
        os.chdir(base_dir)

        # -- Setup UDP Sockets --
        self.command_socket = QUdpSocket(self)
        self.command_socket.bind(QHostAddress.LocalHost, COMMAND_UDP_PORT)
        self.command_socket.readyRead.connect(self.process_command_datagrams)
        print(f"Listening for UI commands on UDP port {COMMAND_UDP_PORT}")

        self.loudness_socket = QUdpSocket(self)
        self.loudness_socket.bind(QHostAddress.LocalHost, LOUDNESS_UDP_PORT)
        self.loudness_socket.readyRead.connect(self.process_loudness_datagrams)
        print(f"Listening for loudness on UDP port {LOUDNESS_UDP_PORT}")

    def keyPressEvent(self, event):
        """Closes the application when the Escape key is pressed."""
        if event.key() == Qt.Key_Escape:
            self.close()

    def process_command_datagrams(self):
        """Processes incoming UDP commands for the UI."""
        while self.command_socket.hasPendingDatagrams():
            datagram = self.command_socket.receiveDatagram()
            command = bytes(datagram.data()).decode('utf-8').strip()
            print(f"Received UI command: '{command}'")
            if command == 'show':
                self.show()
                self.raise_()
                self.activateWindow()
            elif command == 'hide':
                self.hide()
            else:
                self.page.runJavaScript(f"setMode('{command}');")

    def process_loudness_datagrams(self):
        """Receives loudness data and puts it in the queue for the WebSocket server."""
        while self.loudness_socket.hasPendingDatagrams():
            datagram = self.loudness_socket.receiveDatagram()
            try:
                loudness_str = bytes(datagram.data()).decode('utf-8').strip()
                self.loudness_q.put(float(loudness_str))
            except (ValueError, UnicodeDecodeError):
                pass # Ignore malformed data

    def closeEvent(self, event):
        """Ensures servers are shut down when the window closes."""
        print("Shutting down servers and closing application...")
        control.send_tts_command('stop_audio')
        time.sleep(0.1) # Give the command a moment to be processed
        self.http_server.shutdown()
        super().closeEvent(event)

# --- Main Execution ---
if __name__ == '__main__':
    websocket_thread = threading.Thread(target=run_websocket_server, args=(loudness_queue,), daemon=True)
    websocket_thread.start()

    app = QApplication(sys.argv)
    app.setApplicationName('Ketta')

    screen = app.primaryScreen().geometry()
    base_dim = min(screen.width(), screen.height())
    win_size = int(base_dim * 0.25)
    
    window = MainWindow(loudness_queue)
    window.setGeometry((screen.width() - win_size) // 2, (screen.height() - win_size) // 2, win_size, win_size)
    
    print("Orb application is running in the background. Send a 'show' command to make it visible.")
    
    sys.exit(app.exec_())
