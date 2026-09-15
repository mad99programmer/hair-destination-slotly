import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

encrypted_aes_key = "ZrN7C4g1+gS4Tv5sGT60eJNlj1uin8xbCp5v+w41TaWw9WeMHwNQQiQoeV7Q4/usnpl5AxUZ5vTPvnPvYiLaOd2rydZ+Mc9Akt2DdxPuv4KIpMn3+MYlkkLvt7otB5pVYDNtb6IYhj1V70rTU2tDM922NFIpMXUMA47wTTQ+QVfsdgfowFISWTQTx4whK2hm/mJNtd+jouXDBwJ/GTI0L9EXFh3DQfTGAjofrs1YKQmEvZEuj1pEK1hhoLM14wbk/ac4m9jSvE3doWVnnG4RMobazLJWnCAlTQI/cR1d37hf3soSzLPAHtA4mlikQoe3nlB4r5Xt2qQRH/8r/Gs/1A=="

with open("private.pem", "rb") as f:
    private_key = serialization.load_pem_private_key(
        f.read(),
        password=input("Password: ").encode()
    )

encrypted = base64.b64decode(encrypted_aes_key)

print("Encrypted AES key length:", len(encrypted))
print("RSA key size:", private_key.key_size)

aes_key = private_key.decrypt(
    encrypted,
    padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None
    )
)

print("SUCCESS")
print("AES key length:", len(aes_key))
print("AES key:", aes_key.hex())