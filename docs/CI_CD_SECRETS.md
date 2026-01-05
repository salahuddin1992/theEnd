# CI/CD Secrets Configuration Guide

This document explains how to configure GitHub Secrets for code signing and deployment.

## Required Secrets

### Windows Code Signing (Authenticode)

| Secret Name | Description |
|-------------|-------------|
| `CODE_SIGN_CERT_BASE64` | Base64-encoded `.pfx` certificate file |
| `CODE_SIGN_CERT_PASSWORD` | Password for the certificate |

#### How to Create Windows Signing Certificate

1. **Purchase or obtain a code signing certificate** from a trusted CA (DigiCert, Sectigo, etc.)

2. **Export as PFX file:**
   ```powershell
   # Export from Windows Certificate Store
   $cert = Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object { $_.Subject -match "Your Company" }
   Export-PfxCertificate -Cert $cert -FilePath certificate.pfx -Password (ConvertTo-SecureString -String "your-password" -Force -AsPlainText)
   ```

3. **Convert to Base64:**
   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("certificate.pfx")) | Out-File -FilePath cert-base64.txt
   ```

4. **Add to GitHub Secrets:**
   - Go to Repository → Settings → Secrets → Actions
   - Add `CODE_SIGN_CERT_BASE64` with the Base64 content
   - Add `CODE_SIGN_CERT_PASSWORD` with your certificate password

---

### macOS Code Signing & Notarization

| Secret Name | Description |
|-------------|-------------|
| `APPLE_CERT_BASE64` | Base64-encoded `.p12` Developer ID certificate |
| `APPLE_CERT_PASSWORD` | Password for the certificate |
| `APPLE_ID` | Apple Developer ID email |
| `APPLE_ID_PASSWORD` | App-specific password (NOT your Apple ID password) |
| `APPLE_TEAM_ID` | Your Apple Developer Team ID |

#### How to Create macOS Signing Certificate

1. **Create Developer ID Application certificate** in Apple Developer Portal

2. **Export from Keychain Access:**
   - Open Keychain Access
   - Find "Developer ID Application: Your Name"
   - Right-click → Export
   - Save as `.p12` with password

3. **Convert to Base64:**
   ```bash
   base64 -i certificate.p12 -o cert-base64.txt
   ```

4. **Create App-Specific Password:**
   - Go to https://appleid.apple.com
   - Sign In → Security → App-Specific Passwords
   - Generate a new password for "GitHub Actions"

5. **Find Team ID:**
   - Go to https://developer.apple.com/account
   - Membership → Team ID

6. **Add to GitHub Secrets:**
   - `APPLE_CERT_BASE64`: Base64 certificate content
   - `APPLE_CERT_PASSWORD`: Certificate export password
   - `APPLE_ID`: your-email@example.com
   - `APPLE_ID_PASSWORD`: App-specific password
   - `APPLE_TEAM_ID`: Your 10-character Team ID

---

### Linux GPG Signing

| Secret Name | Description |
|-------------|-------------|
| `GPG_PRIVATE_KEY` | ASCII-armored GPG private key |
| `GPG_PASSPHRASE` | Passphrase for the GPG key |

#### How to Create GPG Signing Key

1. **Generate GPG Key:**
   ```bash
   gpg --full-generate-key
   # Choose RSA and RSA, 4096 bits
   # Enter your name and email
   # Set a passphrase
   ```

2. **Export Private Key:**
   ```bash
   gpg --armor --export-secret-keys YOUR_KEY_ID > private-key.asc
   ```

3. **Add to GitHub Secrets:**
   - `GPG_PRIVATE_KEY`: Content of `private-key.asc`
   - `GPG_PASSPHRASE`: Your GPG passphrase

4. **Optional - Publish Public Key:**
   ```bash
   gpg --keyserver keyserver.ubuntu.com --send-keys YOUR_KEY_ID
   ```

---

### PyPI Publishing

| Secret Name | Description |
|-------------|-------------|
| `PYPI_API_TOKEN` | API token from pypi.org |

#### How to Create PyPI Token

1. Go to https://pypi.org/manage/account/token/
2. Create a new token with scope for this project
3. Add `PYPI_API_TOKEN` to GitHub Secrets

---

### Docker Registry

The workflow uses `GITHUB_TOKEN` for GitHub Container Registry (ghcr.io), which is automatically provided.

For other registries:

| Secret Name | Description |
|-------------|-------------|
| `DOCKER_USERNAME` | Docker Hub username |
| `DOCKER_PASSWORD` | Docker Hub access token |

---

## Environment Setup

Create a GitHub Environment for production deployments:

1. Go to Repository → Settings → Environments
2. Create `pypi` environment
3. Add protection rules:
   - Required reviewers
   - Wait timer (optional)
4. Add environment secrets

---

## Verification

After adding secrets, run a test build to verify:

```bash
# Trigger workflow manually
gh workflow run "Build & Release" --ref main
```

Check the Actions tab for signing status. Signed artifacts will show:
- Windows: `signtool verify` success
- macOS: `codesign -v` success
- Linux: `.asc` signature files alongside packages

---

## Security Best Practices

1. **Never commit certificates or keys** to the repository
2. **Rotate secrets annually** or after any security incident
3. **Use environment protection** for production secrets
4. **Limit secret scope** - don't share production secrets with PR builds
5. **Audit secret access** - review who has access to repository secrets

## Troubleshooting

### Windows Signing Fails
- Verify certificate is valid and not expired
- Check timestamp server is accessible
- Ensure certificate has code signing EKU

### macOS Notarization Fails
- Verify Apple ID password is app-specific
- Check Team ID matches certificate
- Ensure binary has proper entitlements

### GPG Signing Fails
- Verify key is not expired
- Check passphrase is correct
- Ensure key has signing capability
