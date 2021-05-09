#!/usr/bin/env python3
# Game Boy Online Server
# -*- coding: utf-8 -*-

# Programmed by stacksmashing

__title__ = 'Game Boy Online Server'
__author__ = 'stacksmashing'
__version__ = '1.0.0'
__ver_major__ = 1
__ver_minor__ = 0
__ver_patch__ = 0

import json
import uuid
import asyncio
import datetime
import random
import websockets
import string
import ssl
# Global scope #YOLO
active_games = {}

import time

import logging

class Client:
    """Object that represents a client in a game."""
    STATE_ALIVE = 0
    STATE_DEAD = 1
    STATE_WINNER = 2

    def __init__(self, socket, name):
        """Requres client socket and client name."""
        self.game = None
        self.name = name
        self.uuid = str(uuid.uuid4())
        #socket is really a websockets.WebSocketServerProtocol
        self.socket = socket
        self.level = 0
        self.state = self.STATE_ALIVE
    
    def set_game(self, game):
        """Set self.game to game."""
        print("Setting game...")
        self.game = game
    
    async def process(self):
        """Process packets from client."""
        async for packet in self.socket:
            # Maybe also should have max duration or so.. not sure.
            if self.game.state == Game.GAME_STATE_FINISHED:
                print('Game finished.')
                return
            print('Await...')
            # Try to load packet with json, but in the event of mangled packet,
            # don't process it and break something.
            try:
                msg = json.loads(packet)
            except:
                pass
            else:
                await self.game.process(self, msg)
            print('Post process...')
    
    def set_dead(self):
        """Set self.state to dead state."""
        self.state = self.STATE_DEAD
    
    def set_winner(self):
        """Set self.state to winner state."""
        self.state = self.STATE_WINNER

    async def send(self, packet):
        """Send packet on self.socket."""
        print('Sending..')
        await self.socket.send(packet)
        print('Done')
    
    def serialize(self):
        """Return a dictionary containing name, level, state, and uuid of self."""
        return {
            'name': self.name,
            'level': self.level,
            'state': self.state,
            'uuid': self.uuid
        }
    pass

class Game:
    """Object that represents a running tetris game."""
    GAME_STATE_LOBBY = 0
    GAME_STATE_RUNNING = 1
    GAME_STATE_FINISHED = 2
    
    @staticmethod
    def _generate_name():
        """Return a random string of 8 uppercase letters."""
        return ''.join(random.choice(string.ascii_uppercase) for i in range(8))
    
    def __init__(self, admin_socket):
        """Requires admin socket to start the game."""
        self.name = self._generate_name()
        self.admin_socket = admin_socket
        self.clients = [admin_socket]
        self.state = self.GAME_STATE_LOBBY
    
    def get_gameinfo(self):
        """Return dictionary with type, name, status, and users."""
        users = [client.serialize() for client in self.clients]
        return {
            'type': 'game_info',
            'name': self.name,
            'status': self.state,
            'users': users
        }
    
    async def send_lines(self, lines, sender_uuid):
        """Send lines to everyone but the client who sent them."""
        packet = json.dumps({
            'type': 'lines',
            'lines': lines
            })
        # Initialize all coroutines, THEN wait for them all to finish
        coros = [c.send(packet) for c in self.clients if not c.uuid == sender_uuid]
        await asyncio.gather(*coros)
    
    async def send_gameinfo_client(self, client):
        """Send game info to an individual client."""
        game_info = json.dumps(self.get_gameinfo())
        await client.send(game_info)
    
    async def send_gameinfo(self):
        """Send game info to all connected clients."""
##        # Initialize all coroutines, THEN wait for them all to finish
##        coros = [self.send_gameinfo_client(s) for s in self.clients]
##        await asyncio.gather(*coros)
        # Just use send all method we have defined!
        await self.send_all(self.get_gameinfo())
    
    async def send_all(self, data):
        """Send data as dumped json to all clients."""
##        for c in self.clients:
##            # TODO: Serialized, might wanna create_task here
##            await c.send(json.dumps(data))
        # Initialize all coroutines, THEN wait for them all to finish
        packet = json.dumps(data)
        coros = [client.send(packet) for client in self.clients]
        await asyncio.gather(*coros)
    
    async def add_client(self, client):
        """Add a client to the game. Raises an exception if game is not in lobby state."""
        if self.state != self.GAME_STATE_LOBBY:
            raise('Game not in lobby')
        self.clients.append(client)
        await self.send_gameinfo()
    
    async def start_game(self):
        """Start a game."""
        self.state = self.GAME_STATE_RUNNING
        await self.send_all({
            'type': 'start_game',
            'tiles': self.generate_tiles()
        })
    
    def alive_count(self):
        """Return number of clients in alive state."""
        count = 0
        for c in self.clients:
            if c.state == Client.STATE_ALIVE:
                count += 1
        return count
    
    def get_last_alive(self):
        """Return first client found in alive state."""
        for c in self.clients:
            if c.state == Client.STATE_ALIVE:
                return c
        return None
    
    @staticmethod
    def generate_tiles():
        """Return 256 random tiles."""
        tiles = (
            '00',
            '04',
            '08', # I Tile
            '0C', # Square Tile
            '10', # Z Tile,
            '14', # S Tile
            '18'  # T Tile
        )
        return ''.join(random.choice(tiles) for i in range(256))
    
    async def process(self, client, msg):
        """Process a msg from client."""
        print(f'Processing {client.name} with msg {msg}')
        if not isinstance(msg, dict) or not 'type' in msg:
            # Skip broken messages from invalid packets.
            return
        if msg['type'] == 'start':
            # Check if game state is correct.
            if self.state != self.GAME_STATE_LOBBY:
                print('Error: Game already running or finished.')
                return
            # Check if admin.
            if client != self.admin_socket:
                print('Error: Not an admin.')
                return
            print('Starting game!')
            await self.start_game()
        elif msg['type'] == 'update':
            if self.state != self.GAME_STATE_RUNNING:
                print('Game is not running. Error.')
                return
            level = msg['level']
            client.level = level
            await self.send_gameinfo()
        elif msg['type'] == 'lines':
            print('Lines received')
            if self.state != self.GAME_STATE_RUNNING:
                print('Game is not running. Error.')
                return
            await self.send_lines(msg['lines'], client.uuid)
        elif msg['type'] == 'dead':
            if self.state == self.GAME_STATE_FINISHED:
                print('User might just have died.. ignore')
                return
            if self.state != self.GAME_STATE_RUNNING:
                print('Game is not running. Error.')
                return
            print('User died')
            # Get alive count...
            alive_count = self.alive_count()
            if alive_count == 2:
                # We have a winner!
                client.set_dead()
                winner = self.get_last_alive()
                winner.set_winner()
                await winner.send(json.dumps({
                    'type': 'win'
                }))
                self.state = self.GAME_STATE_FINISHED
            elif alive_count > 1:
                print('Set dead')
                client.set_dead()
            else:
                print('Solo')
                client.set_dead()
            await self.send_gameinfo()
    pass

class GameHandler:
    def __init__(self):
        pass
    pass

sockets = []

games = {}

def parse_register_msg(msg):
    """Return json from message if type field is register."""
    # Wrapped in a try except block because we can never trust the clients.
    try:
        j = json.loads(msg)
        if 'type' in j and j['type'] == 'register':
            return j
    except:
        pass
    print('Not a registration message')
    return None

async def newserver(websocket, path):
    """Function called when new server is started."""
    print('New server')
    # First wait for registration message.
    # Without it we don't do anything.
    msg = parse_register_msg(await websocket.recv())
    if msg is None or not 'name' in msg:
        error = {
            'type': 'error',
            'msg': 'Invalid registration message'
        }
        await websocket.send(json.dumps(error))
        return
    name = msg['name']
    
    print(f'New client with name: {name}')
    
    # Next we create a client structure
    client = Client(websocket, name)
    # Send uuid to client
    await client.send(json.dumps({
        'type': 'user_info',
        'uuid': client.uuid
    }))
    
    # Either create a new game
    if path == '/create':
        print('Create game')
        new_game = Game(client)
        
        # If name is already existant, regenerate name.
        while new_game.name in games:
            new_game.name = new_game._generate_name()
        # Immidiately add new game to games list, now that we've allocated it's name.
        # Still a very small chance another asyncronous server could claim
        # the same name at the same time though.
        games[new_game.name] = new_game
        
        client.set_game(new_game)

        print('Sending gameinfo..')
        await new_game.send_gameinfo()
        print('Done')
        
        await client.process()
    # Or join an existing game
    elif path.startswith('/join/'):
        game_name = path[6:]
        print(f'join game with id: >{game_name}<')
        
        # Make tiny function quick for sending invalid game error.
        async def invalid_game():
            error = {
                'type': 'error',
                'msg': 'Game not found.'
            }
            await websocket.send(json.dumps(error))
        
        # If game name is not valid, tell client it's invalid.
        if not game_name in games:
            await invalid_game()
            return
        
        game = games[game_name]
        
        # Ensure game is joinable to avoid exception when adding client
        if game.state != self.GAME_STATE_LOBBY:
            # Really, message should be "Game is not in lobby state.",
            # but that would likely require interface modifications.
            await invalid_game()
            return
        
        client.set_game(game)
        
        await game.add_client(client)
        
        print('Sending gameinfo...')
        await game.send_gameinfo()
        await client.process()
    # Otherwise, path is invalid and we don't care about it.
    else:
        print(f'Unhandled path: {path}')
    return

def run():
    print('Welcome to the Game Boy Online Server!')
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cert = "..."
    key = "..."

    ssl_context.load_cert_chain(certfile=cert, keyfile=key)
    
    start_server = websockets.serve(newserver, '0.0.0.0', 5678, ping_interval=None)#, ssl=ssl_context)
    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(start_server)
    event_loop.run_forever()

if __name__ == '__main__':
    print('%s v%s\nProgrammed by %s.' % (__title__, __version__, __author__))
    run()    
