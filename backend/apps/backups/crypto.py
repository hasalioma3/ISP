"""
Streaming encryption for backup archives: AES-256-GCM in 1 MiB chunks, key
from the passphrase with scrypt. Chunked (rather than one Fernet token) so a
multi-hundred-MB archive never has to sit in the Pi's RAM.

File layout:
    b'ISPBK1\n' | salt (16) | nonce prefix (8) | chunks...
    chunk = length (4, big-endian, of ciphertext) | ciphertext+tag
Each chunk's nonce is prefix + 4-byte counter, and its AAD marks whether it
is the last chunk -- so reordering, dropping or truncating chunks makes
decryption fail instead of yielding a silently short archive.
"""
import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b'ISPBK1\n'
CHUNK = 1024 * 1024


def _key(passphrase, salt):
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(passphrase.encode())


def is_encrypted(path):
    with open(path, 'rb') as f:
        return f.read(len(MAGIC)) == MAGIC


def encrypt_file(src, dst, passphrase):
    salt, prefix = os.urandom(16), os.urandom(8)
    aes = AESGCM(_key(passphrase, salt))
    with open(src, 'rb') as fin, open(dst, 'wb') as fout:
        fout.write(MAGIC + salt + prefix)
        counter = 0
        chunk = fin.read(CHUNK)
        while True:
            nxt = fin.read(CHUNK)
            last = not nxt
            ct = aes.encrypt(prefix + struct.pack('>I', counter), chunk, b'last' if last else b'more')
            fout.write(struct.pack('>I', len(ct)) + ct)
            if last:
                break
            chunk, counter = nxt, counter + 1


class DecryptionError(Exception):
    pass


def decrypt_file(src, dst, passphrase):
    from cryptography.exceptions import InvalidTag
    with open(src, 'rb') as fin, open(dst, 'wb') as fout:
        if fin.read(len(MAGIC)) != MAGIC:
            raise DecryptionError('Not an encrypted backup')
        salt, prefix = fin.read(16), fin.read(8)
        aes = AESGCM(_key(passphrase, salt))
        counter, done = 0, False
        while True:
            head = fin.read(4)
            if not head:
                break
            if done:
                raise DecryptionError('Data after the final chunk -- the file was tampered with')
            ct = fin.read(struct.unpack('>I', head)[0])
            nonce = prefix + struct.pack('>I', counter)
            try:
                try:
                    fout.write(aes.decrypt(nonce, ct, b'more'))
                except InvalidTag:
                    fout.write(aes.decrypt(nonce, ct, b'last'))
                    done = True
            except InvalidTag:
                raise DecryptionError('Wrong passphrase, or the file is damaged')
            counter += 1
        if not done:
            raise DecryptionError('The file is incomplete (truncated)')
