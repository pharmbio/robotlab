import socketserver

class Echo(socketserver.BaseRequestHandler):
    """
    The request handler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def handle(self):
        # self.request is the TCP socket connected to the client
        print('handling data')
        data = self.request.recv(1024).strip()
        print("{} wrote:".format(self.client_address[0]))
        print(data.decode())
        # just send back the same data, but upper-cased
        # self.request.sendall(self.data.upper())

HOST, PORT = "localhost", 32021

with socketserver.TCPServer((HOST, PORT), Echo) as server:
    # Activate the server; this will keep running until you
    # interrupt the program with Ctrl-C
    print('serving...')
    server.serve_forever()
