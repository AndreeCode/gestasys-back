import argparse
import os
import sys

from src.core.config.config import config
from src.core.security.backup_crypto import BackupCryptoError, decrypt_stream, generate_key


def decrypt(source: str, target: str) -> int:
    key = config.backup_key()
    if key is None:
        print("BACKUP_ENCRYPTION_KEY no esta definido en el .env")
        return 1
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with open(source, "rb") as src, os.fdopen(fd, "wb") as dst:
            total = decrypt_stream(key, src, dst)
    except BackupCryptoError as err:
        os.unlink(target)
        print(f"No se pudo descifrar: {err}")
        return 1
    print(f"Backup descifrado en {target} ({total} bytes). Restaurar con: pg_restore --clean --if-exists -d <bd> {target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Clave de cifrado de los backups (AES-256-GCM)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="imprime una clave nueva para BACKUP_ENCRYPTION_KEY")
    group.add_argument("--decrypt", nargs=2, metavar=("ORIGEN.dump.enc", "DESTINO.dump"), help="descifra un backup")
    args = parser.parse_args()
    if args.generate:
        print(generate_key())
        return 0
    return decrypt(*args.decrypt)


if __name__ == "__main__":
    sys.exit(main())
