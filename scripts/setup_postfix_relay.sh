#!/bin/bash
set -e

# setup_postfix_relay.sh
# Automated script to install and configure Postfix as a relay for Mailgun (or other SMTP auth services).
#
# Usage:
#   sudo ./setup_postfix_relay.sh [SMTP_HOST] [SMTP_USER] [SMTP_PASS]
#
# If arguments are not provided, it will attempt to read them from environment variables
# or prompt for them.

# 1. Gather Configuration
SMTP_HOST="${1:-$SMTP_HOST}"
SMTP_USER="${2:-$SMTP_USER}"
SMTP_PASS="${3:-$SMTP_PASS}"

if [ -z "$SMTP_HOST" ]; then
    read -p "Enter SMTP Host (e.g., smtp.mailgun.org): " SMTP_HOST
fi

if [ -z "$SMTP_USER" ]; then
    read -p "Enter SMTP Username: " SMTP_USER
fi

if [ -z "$SMTP_PASS" ]; then
    read -s -p "Enter SMTP Password: " SMTP_PASS
    echo ""
fi

# Extract domain from host for sasl_passwd (remove port if present)
RELAY_HOST_clean=$(echo $SMTP_HOST | cut -d: -f1)

echo ">>> Configuring Postfix to relay through $RELAY_HOST_clean"

# 2. Install Postfix and SASL libs
# Pre-seed debconf to avoid interactive prompt
debconf-set-selections <<< "postfix postfix/mailname string $(hostname -f)"
debconf-set-selections <<< "postfix postfix/main_mailer_type string 'Satellite system'"

echo ">>> Installing dependencies..."
apt-get update
apt-get install -y postfix libsasl2-modules

# 3. Configure /etc/postfix/main.cf
echo ">>> Configuring main.cf..."
postconf -e "relayhost = [$RELAY_HOST_clean]:587"
postconf -e "smtp_sasl_auth_enable = yes"
postconf -e "smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd"
postconf -e "smtp_sasl_security_options = noanonymous"
postconf -e "smtp_tls_security_level = encrypt"
postconf -e "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt"

# 4. Create SASL password map
echo ">>> Creating SASL password map..."
echo "[$RELAY_HOST_clean]:587 $SMTP_USER:$SMTP_PASS" > /etc/postfix/sasl_passwd
chmod 600 /etc/postfix/sasl_passwd
postmap /etc/postfix/sasl_passwd

# 5. Restart Postfix
echo ">>> Restarting Postfix..."
systemctl restart postfix

echo ">>> Done! Postfix is running and configured."
echo ">>> To test: echo 'Test email body' | mail -s 'Test Subject' your-email@example.com"
