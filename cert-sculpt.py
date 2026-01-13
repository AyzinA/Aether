import os, sys, re
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f: f.write(data)

def get_folder_name(data, leaf_cert):
    # Try to find friendlyName in Bag Attributes (e.g., services.skynet.internal)
    fn_match = re.search(r'friendlyName:\s*([^.\s\n]+)', data)
    if fn_match:
        return fn_match.group(1).lower()

    # Fallback to Common Name from the Certificate (take first part before dot)
    try:
        cn = leaf_cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
        return cn.split('.')[0].lower()
    except:
        return "extracted_cert"

def main():
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], "r") as f: data = f.read()
    else:
        print("No file detected. Paste Certificate Data (Ctrl+D/Z to finish):")
        data = sys.stdin.read()

    key_match = re.search(r'-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----', data, re.DOTALL)
    certs_raw = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', data, re.DOTALL)

    if not key_match or not certs_raw:
        return print("Error: Missing Key or Certificates.")

    l_obj = x509.load_pem_x509_certificate(certs_raw[0].encode())
    folder = get_folder_name(data, l_obj)
    path = os.path.join("certs", folder)

    k_pem = key_match.group(0).encode()
    l_pem = certs_raw[0].encode()
    i_pem = certs_raw[1].encode() if len(certs_raw) > 1 else b""
    r_pem = certs_raw[2].encode() if len(certs_raw) > 2 else b""
    chain_inter_root = b"\n".join([c.encode() for c in certs_raw[1:]])

    print(f"\nTarget Folder: {path}")
    print("="*30)
    print("1. Split: FullChain (Leaf + Inter) and Key")
    print("2. Split: Leaf, Chain (Inter + Root), and Key")
    print("3. Split: Leaf and Key Only")
    print("4. Full Split: Leaf, Inter, Root and Key")
    print("5. P12: Export PKCS12 (.p12)")

    choice = input("\nSelect an option (1-5): ")

    if choice == '1': # Modern Bundle
        save(f"{path}/fullchain.crt", l_pem + b"\n" + i_pem)
        save(f"{path}/private.key", k_pem)
    elif choice == '2': # Standard Linux/Nginx
        save(f"{path}/leaf.crt", l_pem)
        save(f"{path}/chain.crt", chain_inter_root)
        save(f"{path}/private.key", k_pem)
    elif choice == '3': # Minimalist
        save(f"{path}/leaf.crt", l_pem)
        save(f"{path}/private.key", k_pem)
    elif choice == '4': # Debug/Manual
        save(f"{path}/leaf.crt", l_pem)
        if i_pem: save(f"{path}/intermediate.crt", i_pem)
        if r_pem: save(f"{path}/root.crt", r_pem)
        save(f"{path}/private.key", k_pem)
    elif choice == '5': # Windows/Java
        pwd = input("P12 Password (empty for none): ").encode() or None
        p12 = pkcs12.serialize_key_and_certificates(
            b"cert", serialization.load_pem_private_key(k_pem, None),
            l_obj, [x509.load_pem_x509_certificate(c.encode()) for c in certs_raw[1:]],
            serialization.BestAvailableEncryption(pwd) if pwd else serialization.NoEncryption()
        )
        save(f"{path}/certificate.p12", p12)

    print(f"\n[+] Done! Files created in: {os.path.abspath(path)}")

if __name__ == "__main__":
    main()
