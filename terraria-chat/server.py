import asyncio
import json
import os
import websockets

CLIENTS = {}

async def handler(websocket):
    CLIENTS[websocket] = {"name": "Anon", "server": "unknown", "channel": "global"}
    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "auth":
                CLIENTS[websocket].update({
                    "name": data.get("name"),
                    "server": data.get("server"),
                    "channel": data.get("channel", "global")
                })

            elif msg_type == "change_channel":
                CLIENTS[websocket]["channel"] = data.get("channel")

            elif msg_type == "channel_msg":
                sender_info = CLIENTS[websocket]
                for client_ws, info in CLIENTS.items():
                    if client_ws == websocket: continue
                        
                    
                    ch = sender_info["channel"]
                    if info["channel"] == ch:
                        if ch == "server" and info["server"] != sender_info["server"]:
                            continue 
                            
                        await client_ws.send(json.dumps({
                            "type": "channel", 
                            "channel": ch,
                            "sender": sender_info["name"], 
                            "text": data.get("text")
                        }))

            elif msg_type == "dm":
                for client_ws, info in CLIENTS.items():
                    if info["name"].lower() == data.get("target").lower():
                        await client_ws.send(json.dumps({
                            "type": "dm", "sender": CLIENTS[websocket]["name"], "text": data.get("text")
                        }))
                        break
    except websockets.ConnectionClosed:
        pass
    finally:
        if websocket in CLIENTS: del CLIENTS[websocket]

async def main():
    port = int(os.environ.get("PORT", 8765))
    async with websockets.serve(handler, "0.0.0.0", port):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())