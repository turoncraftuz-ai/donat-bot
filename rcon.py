"""Minimal asyncio RCON klient (qo'shimcha kutubxonasiz)."""
import asyncio
import re
import struct


class RconError(Exception):
    pass


async def _send(writer, req_id: int, req_type: int, body: str):
    data = struct.pack("<ii", req_id, req_type) + body.encode("utf-8") + b"\x00\x00"
    writer.write(struct.pack("<i", len(data)) + data)
    await writer.drain()


async def _read(reader, timeout: float):
    raw_len = await asyncio.wait_for(reader.readexactly(4), timeout)
    (length,) = struct.unpack("<i", raw_len)
    if length < 10 or length > 8192:
        raise RconError("RCON noto'g'ri javob qaytardi")
    data = await asyncio.wait_for(reader.readexactly(length), timeout)
    req_id, req_type = struct.unpack("<ii", data[:8])
    body = data[8:-2].decode("utf-8", "replace")
    return req_id, req_type, body


async def rcon_command(host: str, port: int, password: str, command: str, timeout: float = 8.0) -> str:
    if not host or not password:
        raise RconError("RCON sozlanmagan (host/parol yo'q)")
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, asyncio.TimeoutError) as e:
        raise RconError(f"Serverga ulanib bo'lmadi: {e or 'timeout'}")
    try:
        await _send(writer, 1, 3, password)
        while True:
            req_id, req_type, _ = await _read(reader, timeout)
            if req_type == 2:
                break
        if req_id == -1:
            raise RconError("RCON paroli noto'g'ri")
        await _send(writer, 2, 2, command)
        _, _, body = await _read(reader, timeout)
        return re.sub(r"§.", "", body).strip()
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
        raise RconError(f"RCON xatosi: {e or 'timeout'}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
