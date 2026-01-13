## Project Aether: Air-Gapped PKI Lab

**A Two-Tier Public Key Infrastructure (PKI) using EJBCA Community Edition on Docker.**

This project demonstrates the deployment of a secure, production-grade certificate authority hierarchy. It utilizes an Offline Root CA (Trust Anchor) to sign a Subordinate Intermediate CA, which handles day-to-day certificate issuance. This architecture ensures that even if the online CA is compromised, the Root private key remains physically isolated and safe.

---

## Architecture Overview

* **Tier 1: Root CA (VM 1)** - The Offline Trust Anchor.
* **Tier 2: Intermediate CA (VM 2)** - The Online Issuing CA.

---

## Docker Deployment

To ensure persistence and security, we use separate `docker-compose.yml` files for each tier. Use a `.env` file to manage `${MYSQL_ROOT_PASSWORD}` and `${MYSQL_PASSWORD}`.

### VM 1: Root CA Configuration

This instance is configured with `restart: "no"` to enforce the offline policy and binds to `127.0.0.1` to prevent unauthorized network access.

```yaml
services:
  root-db:
    image: mariadb:11
    container_name: ejbca-root-db
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
      - MYSQL_DATABASE=ejbca_root
      - MYSQL_USER=ejbca_root
      - MYSQL_PASSWORD=${MYSQL_PASSWORD}
    volumes:
      - root_db:/var/lib/mysql:rw
    networks:
      - app

  ejbca-root:
    image: keyfactor/ejbca-ce:9.3.7
    container_name: ejbca-root
    hostname: ejbca-root
    depends_on:
      - root-db
    restart: "no" # keep it offline by default; start manually when needed
    environment:
      - DATABASE_JDBC_URL=jdbc:mariadb://root-db:3306/ejbca_root?characterEncoding=UTF-8
      - DATABASE_USER=ejbca_root
      - DATABASE_PASSWORD=${MYSQL_PASSWORD}
      - TLS_SETUP_ENABLED=simple
      - LOG_LEVEL_APP=INFO
      - LOG_LEVEL_SERVER=INFO
    networks:
      - app
      - access
    # IMPORTANT: don't expose to the world. Bind to localhost or a mgmt-only interface.
    ports:
      - "127.0.0.1:8080:8080"
      - "127.0.0.1:8443:8443"
    volumes:
      - root_ejbca:/opt/ejbca/p12 # optional (keep your PKCS#12 exports safe)

networks:
  app:
    driver: bridge
  access:
    driver: bridge

volumes:
  root_db:
  root_ejbca:

```

### VM 2: Issuing (Intermediate) CA Configuration

This instance is the "workhorse" and exposes ports 80/443 for certificate enrollment services (ACME, SCEP, etc.).

```yaml
services:
  issuing-db:
    image: mariadb:11
    container_name: ejbca-issuing-db
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
      - MYSQL_DATABASE=ejbca_issuing
      - MYSQL_USER=ejbca_issuing
      - MYSQL_PASSWORD=${MYSQL_PASSWORD}
    volumes:
      - issuing_db:/var/lib/mysql:rw
    networks:
      - app

  ejbca-issuing:
    image: keyfactor/ejbca-ce:9.3.7
    container_name: ejbca-issuing
    hostname: ejbca-issuing
    depends_on:
      - issuing-db
    restart: unless-stopped
    environment:
      - DATABASE_JDBC_URL=jdbc:mariadb://issuing-db:3306/ejbca_issuing?characterEncoding=UTF-8
      - DATABASE_USER=ejbca_issuing
      - DATABASE_PASSWORD=${MYSQL_PASSWORD}
      - TLS_SETUP_ENABLED=simple
      - LOG_LEVEL_APP=INFO
      - LOG_LEVEL_SERVER=INFO
    networks:
      - app
      - access
    ports:
      - "80:8080"
      - "443:8443"

networks:
  app:
    driver: bridge
  access:
    driver: bridge

volumes:
  issuing_db:

```

### 1. Secure Access

Establish an SSH tunnel from your workstation:

```bash
ssh -L 8443:127.0.0.1:8443 <user>@<VM1_IP_ADDRESS>

```

Visit https://localhost:8443/ejbca/adminweb.

### 2. Create the Crypto Token and Dual Keys

1. In the EJBCA menu, go to **CA Functions** and select **Crypto Tokens**.
2. Click **Create New**.
3. **Name**: RootCryptoToken.
4. **Type**: Soft Crypto Token.
5. **Authentication Code**: Enter a secure passphrase.
6. Once created, generate two separate key pairs:
    * **signKey**: RSA 4096 (Used for signing certificates and CRLs).
    * **encryptKey**: RSA 4096 (Used for data encryption/key recovery).



### 3. Create the Root CA

1. Go to **CA Functions** and select **Certification Authorities**.
2. **Name**: My Root CA.
3. **CA Type**: Root CA.
4. **Crypto Token**: Select RootCryptoToken.
5. **Key Pair Aliases**: Signature Key: **signKey**, Encryption Key: **encryptKey**.
6. **Subject DN**: CN=My Root CA, O=My Org, C=US.
7. **Validity**: 7300d (20 years).
8. Click **Create**.

---

## Phase 2: Intermediate CA and Crypto Token Initialization (VM 2)

The Intermediate CA must be prepared on the second VM before it can be signed by the Root.

### 1. Create the Intermediate Crypto Token

1. Access the EJBCA Admin Web on VM 2.
2. Go to **CA Functions** > **Crypto Tokens**.
3. **Name**: IntermediateCryptoToken.
4. **Type**: Soft Crypto Token.
5. **Authentication Code**: Enter a secure passphrase.
6. Generate two separate key pairs:
    * **signKey**: RSA 4096.
    * **encryptKey**: RSA 4096.



### 2. Create the Intermediate CA Stub

1. Go to **CA Functions** > **Certification Authorities**.
2. **Name**: My Intermediate CA.
3. **CA Type**: Subordinate CA.
4. **Crypto Token**: Select IntermediateCryptoToken.
5. **Key Pair Aliases**: Signature Key: **signKey**, Encryption Key: **encryptKey**.
6. **Subject DN**: CN=My Intermediate CA, O=My Org, C=US.
7. **Signed By**: External CA.
8. Click **Create**.

---

## Phase 3: The Signing Ceremony

### 1. Generate Request (VM 2)

1. On VM 2, click **Edit** on the My Intermediate CA.
2. Click **Make Certificate Request**.
3. Copy the resulting CSR text from the screen.

### 2. Sign Request (VM 1)

1. Open the **RA Web** on VM 1.
2. Select **Make New Request** and choose a Sub-CA profile.
3. Paste the CSR text into the **Certificate Request** box.
4. Ensure **Signing CA** is set to My Root CA.
5. Click **Issue** and download the PEM certificate.

### 3. Finalize and Air-Gap

1. On VM 2, edit the Intermediate CA and upload the signed certificate received from the Root.
2. Once the status shows as **Active**, shut down VM 1:
    ```bash
    docker compose stop
    ```



---

## Phase 4: Administrator Lockdown

Perform these steps on both CAs to ensure only authorized administrators can access the system.

1. **Issue SuperAdmin**: Use RA Web to issue a PKCS#12 certificate with Common Name: **SuperAdmin**.
2. **Map Role**: Add the SuperAdmin certificate (Match Value: SuperAdmin) to the **Super Administrator Role** under **Roles and Access Rules**.
3. **Restart**: `docker compose restart`.
4. **Verification**: Refresh the browser and ensure the SuperAdmin certificate is requested and accepted.
5. **Lockdown**: Delete the **Public Access Role** and the **PublicAccessAuthenticationToken** member.

---

## Troubleshooting: The Unique DN Error

If signing fails with "Subject DN already exists":

1. Navigate to **CA Functions** > **Certification Authorities**.
2. Edit **My Root CA**.
3. Uncheck **Enforce unique DN** and click Save.

---

## CertSculpt

A smart CLI tool to restructure SSL certificates. It automatically extracts project names from the metadata and organizes files into clean directories.

### Features
- **Smart Directory Naming**: Extracts the first part of the `friendlyName` or `Common Name` as the folder name.
- **Auto-Parsing**: Separates the Private Key from the Certificate stack automatically.
- **Hierarchical Detection**: Correctly identifies the **Leaf**, **Intermediate**, and **Root** certificates based on position.

### Option Breakdown
| Option | Files Produced | Description |
| :--- | :--- | :--- |
| **1. FullChain** | `fullchain.crt`, `private.key` | Leaf + Intermediate bundle. Standard for Nginx. |
| **2. Split Chain** | `leaf.crt`, `chain.crt`, `private.key`| Separate identity and authority files. |
| **3. Leaf/Key Only**| `leaf.crt`, `private.key` | Minimalist; assumes server has the chain. |
| **4. Full Split** | `leaf.crt`, `inter.crt`, `root.crt`, `key`| Every component in its own file. |
| **5. PKCS12** | `certificate.p12` | All-in-one binary for Windows/Java. |

### Installation
```bash
pip install cryptography

```

### Usage

```bash
python cert-sculpt.py your_cert_file.pem

```
