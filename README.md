# IsaHacks — A MITM Proxy for Terraria

<img width="1916" height="902" alt="image" src="https://github.com/user-attachments/assets/252a74ea-def3-4ed5-ba21-df50757a8c23" />

*[IsaHacks Web, create an account and test](https://isaedits.pages.dev/)*

A few days ago I was sitting on the balcony, thinking about some pending projects — the kind that have been procrastinated for years — when a friend messaged me on Discord. He knows I play Terraria and had seen me doing “incredible” things on an anarchy server. He asked me how I could do those kinds of things (probably maptp or cloning players). So I told him about the Zaza client — now rebranded as TClient — a project I truly admire and have used for a long time. I wasn't surprised when he said he didn't have a PC, that he played mostly on mobile. It's happened to me many times: mobile players long for the ease that PC hacks provide.

So I thought about porting the full client to Android. But even while vibecoding (the way I've been working ever since those “multibillion dollar computers that probably have over 2-5 tb of ram” literally left me almost jobless — I've never been that good at what I do), it would be hard. I thought about using something like il2cpp and then recompiling with some game engine, but if I went that route, this would become yet another project stalled by procrastination. So I decided to do it in something I know: a language I could debug and fix myself without spending all my tokens, trying to build a project with a real soul. Python. A MITM proxy. I've been using this kind of fix to do things in Terraria for years, even before powerful UI clients existed. Many people used Cheat Engine, but for me, doing MITM in Python was way easier than learning to script in Lua.

So I started making the first commands — well, copying from previous implementations, or hacks like QTR for rainbow letters. Also from old Cheat Engine tables where they used the drone projectile to reveal the map, before the super clever idea of literally asking the server for chunks (implemented in Zaza). Client-side things like full bright or increasing lighting when loading chunks in revmap I couldn't do; those are impossible to implement without injecting or modifying the client.

After half-implementing some commands, I found that many didn't work or only worked partially. I literally had to dump Terraria's network traffic to analyse how it really worked. I made a small script to dump all traffic into a .txt file and left a Claude Code agent working on analysing how everything really works. In my workspace, the agent can do anything: install analysis libraries, run scripts… When I came back, the code had grown considerably. Some commands that I hadn't been able to add myself were fully implemented. Others were broken. After fixing those errors, I got this project — well, not this exact one, but you get the idea.

We have a proxy that you point to a server, then you put the local IP or VPS where the proxy runs into the game and connect. Inside, you get a command system almost worthy of a PC client, but outside your device. This makes this implementation a “cross‑platform hack”. And finally, I was able to satisfy my low‑budget friend.

## Disclaimer

This project is for educational and research purposes only. Using tools that modify the behaviour of an online game may violate Terraria's terms of service and the rules of the servers you connect to. The author is not responsible for any misuse of this software or for any penalties (such as bans) that users may incur. Use it at your own risk and always respect the rules of the communities you play in.

## Commands and implementations

In any case, there are few truly “new” commands or implementations in this project. Most have been analysed and reinterpreted from the best hacks I've seen and tested. Here's a summary:

### Re‑implemented or inspired by ZazaMod (1.3.7)
- Internal logic to notify other proxy users, based on injecting data into an inert packet (case 36, playerzones). It lets you know when another mod user connects.
- The “.” command prefix — I'm very used to these commands and I really love how they are implemented in that client.
- `.killaura` command, taken from the mod's version for 1.4.4.9. Allows users to deal massive damage to enemies in a certain area.
- `.lag` and `.crashmobile` commands, taken from the latest version of the mod. They let you annoy other connected players… Also implemented a block to prevent others from doing it to you.
- The idea: Zaza is a very complete mod that I admire a lot; it was the main inspiration for this project.

### Re‑implemented from QTRHacker
- The `.rainbow` command — I love this one. It lets you write text in the air using the rainbow gun's projectile.

### Implemented using methods similar to those in Cheat Engine scripts, old clients or TShock plugins
- Commands `.god`, `.health`, `.mana`, `.buff`, `.damage`, `.noclip`, `.tp`, `.maptp`, `.revmap`, `.clone`, `.wipe`. Most come from Lua scripts or clients like Fruity.
- Commands `.citem`, `.citem+`, `.maptp` — clearly taken from TShock plugins.

### Almost‑original implementations
- `.item` command. It seems like a simple implementation, but as I said, I'm not good at writing code. I thought about taking the implementation from an old version of Zaza, but it was inaccessible to me. Luckily I could implement something similar thanks to @benzoylmethylecgonin who gave me an idea.
- `.heal` command: having `.item`, it was easy to make something to give many hearts to other players…
- `.spectate`, `.clicktp` and also part of `.revmap` (giving items to teleport or giving the drone to explore the map). It was almost a full implementation, though very simple.
- `.inchat` command: I implemented an invisible chat system for the server. Nothing ingenious — it's invisible because it literally doesn't go through the server. The chat engine is in the renderer and uses websockets to connect users. There's a global chat where you talk to all proxy users, even if they're not on the same server.
- `.bot` command: this is almost a whole project. A CLI client that can autonomously connect to servers and from which you can control chat. It allows adding many bots to a server and has a `!afk` command that lets an LLM (Llama 3.1 8B served via Groq) interact with chat.
- `.proxy` and `.afk` commands: the latter described above. `.proxy` lets you connect via SOCKS5 proxies, either manually configured or pulled from public lists on GitHub.

## Credits

This project contains code, logic, and ideas that have been re‑implemented or directly adapted from the following sources (without explicit permission — this is a humble fan recreation):

- **ZazaMod (now TClient)** — for the command structure, killaura, lag, crashmobile, and the player‑zone detection method.
- **QTRHacker** — for the `.rainbow` command.  
  Developer: [Qiu233](https://github.com/Qiu233)
- **Various unknown Cheat Engine script authors** — for the ideas behind `.god`, `.heal`, `.noclip`, `.tp`, etc.
- **TShock** — for the plugin logic behind `.citem`, `.citem+`, `.maptp`. And net packet classification.
  Repository 1: [Pryaxis/TShock](https://github.com/Pryaxis/TShock)
  Repository 2: [Interverse/CustomItems](https://github.com/Interverse/CustomItems)
  Repository 3: [Stealownz/MapTP](https://github.com/Stealownz/MapTP)
- **Public proxy list repositories** (used in the `.proxy` command):
  - `https://raw.githubusercontent.com/Skillter/ProxyGather/master/proxies/working-proxies-socks5.txt`
  - `https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt`
  - `https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt`
  - `https://raw.githubusercontent.com/watchttvv/free-proxy-list/main/proxy.txt`
- **@benzoylmethylecgonin** — for the idea that made `.item` possible.
- **Claude Code (Anthropic's agent)** — for helping analyse network traffic and generating parts of the code.

And finally, a nod to my friend on Discord who just wanted to have fun on mobile.

**IsaHacks** is maintained by [@isawicca](mailto:isa@wiccagirl.online) (Discord: @isawicca).

## Contributing

If at any time you feel like contributing to this project, please make a PR to the repo — I'll be happy to merge it. If you are the developer of any of the mods mentioned above and want me to remove your implementation from this project, please tell me on Discord and I'll be glad to do so as soon as possible.

## Web version

If you want to use the web version without installing anything, go to:  
[https://isaedits.pages.dev/](https://isaedits.pages.dev/)

---

*Thanks for using IsaHacks.*
