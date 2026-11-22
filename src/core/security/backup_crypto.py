import base64
import os
import struct
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"GSBK\x01"
PREFIX_SIZE = 8
CHUNK_SIZE = 1024 * 1024
HEADER_SIZE = len(MAGIC) + PREFIX_SIZE
FRAME = struct.Struct(">IB")
AAD = struct.Struct(">IB")
MAX_CHUNKS = 2**32


class BackupCryptoError(ValueError):
    pass


def generate_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def load_key(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value.strip() + "=" * (-len(value.strip()) % 4))
    except (ValueError, TypeError) as err:
        raise BackupCryptoError("BACKUP_ENCRYPTION_KEY no es base64 valido") from err
    if len(raw) != 32:
        raise BackupCryptoError("BACKUP_ENCRYPTION_KEY debe decodificar a 32 bytes (AES-256)")
    return raw


def _nonce(prefix: bytes, index: int) -> bytes:
    return prefix + struct.pack(">I", index)


class Encryptor:
    def __init__(self, key: bytes, out: BinaryIO):
        self.aead = AESGCM(key)
        self.prefix = os.urandom(PREFIX_SIZE)
        self.header = MAGIC + self.prefix
        self.out = out
        self.index = 0
        self.buffer = bytearray()
        out.write(self.header)

    def _seal(self, data: bytes, final: bool) -> None:
        if self.index >= MAX_CHUNKS:
            raise BackupCryptoError("Backup demasiado grande para cifrar")
        flag = 1 if final else 0
        sealed = self.aead.encrypt(_nonce(self.prefix, self.index), data, self.header + AAD.pack(self.index, flag))
        self.out.write(FRAME.pack(len(sealed), flag))
        self.out.write(sealed)
        self.index += 1

    def write(self, data: bytes) -> None:
        self.buffer += data
        while len(self.buffer) > CHUNK_SIZE:
            self._seal(bytes(self.buffer[:CHUNK_SIZE]), False)
            del self.buffer[:CHUNK_SIZE]

    def finish(self) -> None:
        self._seal(bytes(self.buffer), True)
        self.buffer.clear()


def decrypt_stream(key: bytes, src: BinaryIO, dst: BinaryIO) -> int:
    header = src.read(HEADER_SIZE)
    if len(header) != HEADER_SIZE or not header.startswith(MAGIC):
        raise BackupCryptoError("El archivo no es un backup cifrado de GestaSys")
    aead = AESGCM(key)
    prefix = header[len(MAGIC):]
    index = 0
    total = 0
    while True:
        frame = src.read(FRAME.size)
        if len(frame) != FRAME.size:
            raise BackupCryptoError("El backup esta truncado o incompleto")
        size, flag = FRAME.unpack(frame)
        if size > CHUNK_SIZE + 16 or flag not in (0, 1):
            raise BackupCryptoError("El backup esta danado")
        sealed = src.read(size)
        if len(sealed) != size:
            raise BackupCryptoError("El backup esta truncado o incompleto")
        try:
            data = aead.decrypt(_nonce(prefix, index), sealed, header + AAD.pack(index, flag))
        except InvalidTag as err:
            raise BackupCryptoError("Clave incorrecta o backup alterado") from err
        dst.write(data)
        total += len(data)
        index += 1
        if flag == 1:
            if src.read(1):
                raise BackupCryptoError("El backup tiene datos extra despues del final")
            return total
