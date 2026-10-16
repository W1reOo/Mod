"""Generate the project-owned M icon without third-party assets or dependencies."""
import math
import struct
import zlib
from pathlib import Path


def inside(x, y, polygon):
    result = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1:
            result = not result
        previous = current
    return result


def png(size):
    rows = bytearray()
    polygon = [(24,74),(24,26),(35,26),(50,48),(65,26),(76,26),(76,74),(64,74),(64,48),(50,67),(36,48),(36,74)]
    for row in range(size):
        rows.append(0)
        for col in range(size):
            x, y = (col+.5)*100/size, (row+.5)*100/size
            corner = math.hypot(max(abs(x-50)-31,0),max(abs(y-50)-31,0))
            color = (103,232,195,255) if corner <= 15 else (0,0,0,0)
            if inside(x,y,polygon):
                color = (16,44,37,255)
            rows.extend(color)
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(rows),9))+chunk(b'IEND',b'')


if __name__ == '__main__':
    sizes = [16,32,48,64,128,256]
    images = [png(size) for size in sizes]
    header = struct.pack('<HHH',0,1,len(images))
    offset = 6+16*len(images)
    for size, data in zip(sizes,images):
        header += struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset)
        offset += len(data)
    output = Path(__file__).resolve().parents[1]/'packaging/windows/ModHarbor.ico'
    output.write_bytes(header+b''.join(images))
