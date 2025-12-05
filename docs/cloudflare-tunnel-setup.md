# Cloudflare Tunnel Setup Guide

This guide explains how to securely expose your Raspberry Pi MCP Server to the internet using Cloudflare Tunnel and Cloudflare Access for authentication.

## Overview

Cloudflare Tunnel (`cloudflared`) creates a secure outbound connection from your Raspberry Pi to Cloudflare's edge network, allowing you to access the MCP server from anywhere without:
- Opening inbound firewall ports
- Configuring port forwarding
- Exposing your home IP address

**Architecture:**
```
AI Assistant → Cloudflare Edge → Cloudflare Tunnel → Raspberry Pi MCP Server
  (Internet)      (Global CDN)         (Encrypted)       (Local Network)
```

**Benefits:**
- Zero inbound ports required
- DDoS protection via Cloudflare
- Automatic HTTPS with Cloudflare certificates
- OAuth/OIDC authentication via Cloudflare Access
- No dynamic DNS needed

## Prerequisites

1. **Cloudflare Account**: Free or paid plan at [cloudflare.com](https://cloudflare.com)
2. **Domain Name**: Registered and using Cloudflare DNS (nameservers)
3. **Raspberry Pi**: Running Raspberry Pi OS with internet connection
4. **MCP Server**: Installed and running locally (see [getting-started.md](getting-started.md))

## Step 1: Install cloudflared

Download and install `cloudflared` for your Raspberry Pi architecture:

### ARM64 (Raspberry Pi 4, Pi 5)

```bash
# Download ARM64 binary
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64

# Move to system path
sudo mv cloudflared-linux-arm64 /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# Verify installation
cloudflared version
```

### ARM (Raspberry Pi 3, Zero 2W)

```bash
# Download ARM binary
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm

# Move to system path
sudo mv cloudflared-linux-arm /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# Verify installation
cloudflared version
```

## Step 2: Authenticate with Cloudflare

Authenticate `cloudflared` with your Cloudflare account:

```bash
# Login to Cloudflare (opens browser for OAuth)
cloudflared tunnel login
```

This will:
1. Open a browser window for Cloudflare login
2. Ask you to select a zone (domain) to authorize
3. Create credentials at `~/.cloudflared/cert.pem`

Copy credentials to system location:

```bash
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/cert.pem /etc/cloudflared/
```

## Step 3: Create a Tunnel

Create a named tunnel for your MCP server:

```bash
# Create tunnel
sudo cloudflared tunnel create raspi-mcp-server
```

This outputs:
```
Tunnel credentials written to /root/.cloudflared/<UUID>.json
Created tunnel raspi-mcp-server with id <your-tunnel-uuid>
```

**Important**: Save the tunnel UUID for the next steps.

Copy credentials to the standard location:

```bash
# Copy credentials
sudo cp /root/.cloudflared/<UUID>.json /etc/cloudflared/tunnel-credentials.json
```

## Step 4: Configure the Tunnel

Create the tunnel configuration file:

```bash
sudo nano /etc/cloudflared/config.yml
```

Add the following content (replace placeholders):

```yaml
# Cloudflare Tunnel Configuration for MCP Raspi Server
tunnel: <your-tunnel-uuid>
credentials-file: /etc/cloudflared/tunnel-credentials.json

ingress:
  # Route your domain to the local MCP server
  - hostname: mcp.yourdomain.com
    service: http://localhost:8000
    originRequest:
      noTLSVerify: false
      connectTimeout: 30s
      keepAliveConnections: 100

  # Catch-all rule (required)
  - service: http_status:404
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `hostname` | Public domain for MCP access | Required |
| `service` | Local MCP server address | `http://localhost:8000` |
| `connectTimeout` | Connection timeout | `30s` |
| `keepAliveConnections` | Max keepalive connections | `100` |

## Step 5: Configure DNS

Create a DNS record that points to your tunnel:

```bash
# Create CNAME record pointing to tunnel
sudo cloudflared tunnel route dns <your-tunnel-uuid> mcp.yourdomain.com
```

This creates a CNAME record:
```
mcp.yourdomain.com → <UUID>.cfargotunnel.com
```

You can verify in your Cloudflare Dashboard under DNS settings.

## Step 6: Test the Tunnel

Test the tunnel in foreground mode:

```bash
sudo cloudflared tunnel --config /etc/cloudflared/config.yml run
```

In another terminal (or from another device), test connectivity:

```bash
curl -I https://mcp.yourdomain.com
```

Expected response:
```
HTTP/2 200
...
```

Press `Ctrl+C` to stop the foreground tunnel.

## Step 7: Install as systemd Service

Install `cloudflared` as a systemd service:

```bash
# Install service
sudo cloudflared service install

# Enable and start
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# Check status
sudo systemctl status cloudflared
```

View logs:

```bash
sudo journalctl -u cloudflared -f
```

## Step 8: Configure Cloudflare Access (OAuth)

Cloudflare Access adds authentication to your MCP endpoint.

### 8.1: Create Access Application

1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. Navigate to **Access** → **Applications**
3. Click **Add an application** → **Self-hosted**
4. Configure:
   - **Application name**: `Raspberry Pi MCP Server`
   - **Session duration**: `24 hours`
   - **Application domain**: `mcp.yourdomain.com`

### 8.2: Add Access Policy

1. Under **Policies**, click **Add a policy**
2. Configure:
   - **Policy name**: `Allow authenticated users`
   - **Action**: `Allow`
   - **Include rules**:
     - **Emails ending in**: `@yourdomain.com`
     - Or **Specific emails**: `admin@example.com`

### 8.3: Configure Identity Provider

1. Go to **Zero Trust** → **Settings** → **Authentication**
2. Click **Add new** under Identity providers
3. Select your provider:
   - **Google**: Easy setup with Google account
   - **GitHub**: Good for developers
   - **Azure AD**: Enterprise environments
   - **One-time PIN**: Email-based verification

4. Follow the provider-specific setup instructions

### 8.4: Get Application Audience Tag

1. Go back to your application in **Access** → **Applications**
2. Click on your application
3. Find the **Application Audience (AUD) Tag**
4. Copy this value - you'll need it for MCP server configuration

### 8.5: Get Team Domain

1. Go to **Zero Trust** → **Settings** → **General**
2. Find your **Team domain**: `<team-name>.cloudflareaccess.com`
3. Note this for MCP server configuration

## Step 9: Configure MCP Server for Cloudflare Access

Update your MCP server configuration to validate Cloudflare Access JWT tokens:

```yaml
# /etc/mcp-raspi/config.yml

security:
  mode: "cloudflare"
  
  cloudflare_access:
    enabled: true
    team_domain: "<team-name>.cloudflareaccess.com"
    audience_tag: "<application-aud-from-cloudflare>"
    jwks_url: "https://<team-name>.cloudflareaccess.com/cdn-cgi/access/certs"
    jwks_cache_ttl_seconds: 3600
  
  # Map JWT claims to MCP roles
  role_mappings:
    groups_to_roles:
      "mcp-admins": "admin"
      "mcp-operators": "operator"
```

Add sensitive values to secrets file:

```bash
# /etc/mcp-raspi/secrets.env
MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__TEAM_DOMAIN=<team-name>.cloudflareaccess.com
MCP_RASPI_SECURITY__CLOUDFLARE_ACCESS__AUDIENCE_TAG=<your-audience-tag>
```

Restart MCP server:

```bash
sudo systemctl restart mcp-raspi-server
```

## Step 10: Test Complete Setup

### From a Web Browser

1. Open `https://mcp.yourdomain.com` in a browser
2. You should be redirected to Cloudflare Access login
3. Authenticate with your configured identity provider
4. After successful auth, you'll have access to the MCP server

### From an MCP Client

```bash
# Test with curl (need to handle Cloudflare Access auth)
# For CLI tools, you may need to use Service Tokens

# Or use a browser-based MCP client that handles OAuth
```

## Service Tokens (Optional)

For automated/programmatic access without browser login, create a Service Token:

1. Go to **Access** → **Service Auth** → **Service Tokens**
2. Click **Create Service Token**
3. Name it (e.g., `MCP CLI Access`)
4. Copy the **Client ID** and **Client Secret**

Use in requests:

```bash
curl -H "CF-Access-Client-Id: <client-id>" \
     -H "CF-Access-Client-Secret: <client-secret>" \
     https://mcp.yourdomain.com/api/status
```

## Troubleshooting

### Tunnel Won't Start

```bash
# Check cloudflared logs
sudo journalctl -u cloudflared -n 50

# Verify credentials
sudo ls -la /etc/cloudflared/

# Test tunnel manually
sudo cloudflared tunnel --config /etc/cloudflared/config.yml run
```

### DNS Not Resolving

1. Check DNS in Cloudflare Dashboard
2. Verify CNAME record exists
3. Wait for DNS propagation (up to 5 minutes)

```bash
# Check DNS resolution
dig mcp.yourdomain.com

# Should show CNAME to cfargotunnel.com
```

### 502 Bad Gateway

The MCP server is not running or not accessible:

```bash
# Check MCP server is running
sudo systemctl status mcp-raspi-server

# Check MCP server is listening
curl http://localhost:8000/health

# Check cloudflared config
cat /etc/cloudflared/config.yml
```

### Authentication Failed

1. Verify Access policy includes your email/group
2. Check audience tag matches
3. Verify team domain is correct

```bash
# Test JWT validation
sudo journalctl -u mcp-raspi-server | grep -i jwt
```

### Connection Timeout

1. Check local MCP server is running
2. Verify firewall isn't blocking localhost
3. Increase `connectTimeout` in cloudflared config

## Security Considerations

### Best Practices

1. **Enable Access Policies**: Never expose MCP without authentication
2. **Use Role Mapping**: Map Cloudflare groups to appropriate MCP roles
3. **Enable Audit Logging**: Track all access attempts
4. **Regular Token Rotation**: Rotate service tokens periodically
5. **Monitor Access Logs**: Check Cloudflare dashboard for unusual access

### Firewall Configuration

With Cloudflare Tunnel, no inbound ports are required:

```bash
# You can block all inbound connections (optional)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw enable
```

### Service Token Security

- Store service tokens securely (not in code)
- Use environment variables or secrets management
- Set appropriate expiration
- Revoke immediately if compromised

## Related Documentation

- [Getting Started Guide](getting-started.md)
- [Operations Runbook](operations-runbook.md)
- [Security Design](04-security-oauth-integration-and-access-control-design.md)
- [Deployment Guide](12-deployment-systemd-integration-and-operations-runbook.md)
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
