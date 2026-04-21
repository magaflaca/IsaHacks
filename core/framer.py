
from dataclasses import dataclass, field

@dataclass
class TerrariaFramer:
    buffer: bytearray = field(default_factory=bytearray)
    
    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        frames: list[bytes] = []
        while len(self.buffer) >= 2:
            frame_len = int.from_bytes(self.buffer[0:2], "little")
            if frame_len < 3: 
                self.buffer.clear()
                break
            if len(self.buffer) < frame_len: 
                break
            frames.append(bytes(self.buffer[:frame_len]))
            del self.buffer[:frame_len]
        return frames