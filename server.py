#!/usr/bin/env python3

# import asyncio
# # import websockets
# import json
# import uuid

print("Welcome to the Game Boy Online Server!")

import json
import uuid
import asyncio
import datetime
import random
import websockets
import string
import ssl
# Global scope #YOLO
active_games = {
}

# Because Python sucks
class Game:
    pass
import time

import logging
class Client:
    STATE_ALIVE = 0
    STATE_DEAD = 1
    STATE_WINNER = 2

    def __init__(self, socket, name):
        self.game = None
        self.name = name
        self.uuid = str(uuid.uuid4())
        self.socket = socket
        self.level = 0
        self.state = self.STATE_ALIVE
    
    def set_game(self, game):
        print("Setting game...")
        self.game = game

    async def process(self):
        async for msg in self.socket:
            # Maybe also should have max duration or so.. not sure.
            if self.game.state == Game.GAME_STATE_FINISHED:
                print("Game finished")
                return
            print("Await..")
            await self.game.process(self, json.loads(msg))
            print("Post process...")
    

    def set_dead(self):
        self.state = self.STATE_DEAD
    
    def set_winner(self):
        self.state = self.STATE_WINNER

    async def send(self, f):
        print("Sending..")
        await self.socket.send(f)
        print("Done")
    
    def serialize(self):
        return {
            "name": self.name,
            "level": self.level,
            "state": self.state,
            "uuid": self.uuid
        }

class Game:
    GAME_STATE_LOBBY = 0
    GAME_STATE_RUNNING = 1
    GAME_STATE_FINISHED = 2

    def _generate_name(self):
        return ''.join(random.choice(string.ascii_uppercase) for i in range(8))

    def __init__(self, admin_socket):
        self.name = self._generate_name()
        self.admin_socket = admin_socket
        self.clients = [admin_socket]
        self.state = self.GAME_STATE_LOBBY
    
    def get_gameinfo(self):
        users = []
        for client in self.clients:
            users.append(client.serialize())

        return {
            "type": "game_info",
            "name": self.name,
            "status": self.state,
            "users": users
        }

    async def send_lines(self, lines, sender_uuid):
        for c in self.clients:
            if c.uuid == sender_uuid:
                print("Don't send lines to sender")
                continue
            await c.send(json.dumps({
                "type": "lines",
                "lines": lines
            }))

    async def send_gameinfo(self):
        for s in self.clients:
            await self.send_gameinfo_client(s)

    async def send_gameinfo_client(self, client):
        game_info = json.dumps(self.get_gameinfo())
        await client.send(game_info)


    async def send_all(self, data):
        for c in self.clients:
            # TODO: Serialized, might wanna create_task here
            await c.send(json.dumps(data))


    async def add_client(self, client):
        if self.state != self.GAME_STATE_LOBBY:
            raise("Game not in lobby")
        self.clients.append(client)
        await self.send_gameinfo()

    async def start_game(self):
        self.state = self.GAME_STATE_RUNNING
        await self.send_all({
            "type": "start_game",
            "tiles": self.generate_tiles()
        })
    
    def alive_count(self):
        count = 0
        for c in self.clients:
            if c.state == Client.STATE_ALIVE:
                count += 1
        return count

    def get_last_alive(self):
        for c in self.clients:
            if c.state == Client.STATE_ALIVE:
                return c
        return None

    def generate_tiles(self):
        tiles = [
            "00",
            "04",
            "08", # I Tile
            "0C", # Square Tile
            "10", # Z Tile,
            "14", # S Tile
            "18"  # T Tile
        ]
        ret = ""
        modern = 0 #somehow toggle this in frontend
        if modern: #7-bag randomization

            i = 0
            while i < 256:
                bag = tiles
                random.shuffle(bag)
                for tile in bag:
                    if i < 256:
                        ret += tile
                        i += 1

        else: #classic pure random randomization
            for i in range(256):
                ret += random.choice(tiles)

        return ret


    async def process(self, client, msg):
        print(f"Processing {client.name} with msg {msg}")
        if msg["type"] == "start":
            # Check if game state is correct.
            if self.state != self.GAME_STATE_LOBBY:
                print("Error: Game already running or finished")
                return
            # Check if admin.
            if client != self.admin_socket:
                print("Error: Not an admin.")
                return
            print("Starting game!")
            await self.start_game()
        elif msg["type"] == "update":
            if self.state != self.GAME_STATE_RUNNING:
                print("Game is not running. Error.")
                return
            level = msg["level"]
            client.level = level
            await self.send_gameinfo()
        elif msg["type"] == "lines":
            print("Lines received")
            if self.state != self.GAME_STATE_RUNNING:
                print("Game is not running. Error.")
                return
            await self.send_lines(msg["lines"], client.uuid)
        elif msg["type"] == "dead":
            if self.state == self.GAME_STATE_FINISHED:
                print("User might just have died.. ignore")
                return
            if self.state != self.GAME_STATE_RUNNING:
                print("Game is not running. Error.")
                return
            print("User died")
            # Get alive count..
            alive_count = self.alive_count()
            if alive_count == 2:
                # We have a winner!
                client.set_dead()
                winner = self.get_last_alive()
                winner.set_winner()
                await winner.send(json.dumps({
                    "type": "win"
                }))
                self.state = self.GAME_STATE_FINISHED
            elif alive_count > 1:
                print("Set dead")
                client.set_dead()
            else:
                print("Solo")
                client.set_dead()
            await self.send_gameinfo()
        
            

    

class GameHandler:
    def __init__(self):
        pass

sockets = []

games = {}

def parse_register_msg(msg):
    j = json.loads(msg)
    if j["type"] != "register":
        print("Not a registration message")
        return None
    
    return j

async def newserver(websocket, path):
    print("Newserver")
    # First wait for registration message.
    # Without it we don't do anything.
    msg = parse_register_msg(await websocket.recv())
    if msg == None:
        error = {
            "type": "error",
            "msg": "Invalid registration message"
        }
        await websocket.send(json.dumps(error))
        return
    name = msg["name"]

    print(f"New client with name: {name}")
    
    # Next we create a client structure
    client = Client(websocket, name)
    # Send uuid to client
    await client.send(json.dumps({
        "type": "user_info",
        "uuid": client.uuid
    }))

    # Either create a new game
    if(path == "/create"):
        print("Create game")
        new_game = Game(client)
        while new_game.name in games:
            new_game = Game(client)
        client.set_game(new_game)

        print("Sending gameinfo..")
        await new_game.send_gameinfo()
        print("Done")

        games[new_game.name] = new_game

        await client.process()
    # Or join an existing game
    elif(path.startswith("/join/")):
        game_name = path[6:]
        print(f"join game with id: >{game_name}<")
        if not game_name in games:
            error = {
                "type": "error",
                "msg": "Game not found."
            }
            await websocket.send(json.dumps(error))
            return

        game = games[game_name]
        client.set_game(game)

        await game.add_client(client)

        print("Sending gameinfo..")
        await game.send_gameinfo()
        await client.process()

        
    else:
        print(f"Unhandled path: {path}")



ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
cert = "..."
key = "..."

ssl_context.load_cert_chain(certfile=cert, keyfile=key)

start_server = websockets.serve(newserver, '0.0.0.0', 5678, ping_interval=None, ssl=ssl_context)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
