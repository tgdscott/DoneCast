# Database Connection Troubleshooting Guide

## Quick Diagnosis

Run the diagnostic script to check your database configuration:

```bash
cd backend
python test_db_connection.py
```

This will show:
1. What environment variables are set
2. Whether .env.local exists and contains DATABASE_URL
3. Whether the database connection works

## Common Issues and Solutions

### 1. Connection Timeout Error

**Symptoms:**
```
psycopg.errors.ConnectionTimeout: connection timeout expired
sqlalchemy.exc.OperationalError: (psycopg.errors.ConnectionTimeout) connection timeout expired
```

**Causes:**
- DATABASE_URL is set but points to an unreachable database
- Cloud SQL Proxy is not running (for local development)
- Firewall/network blocking the connection
- Wrong host/port in DATABASE_URL

**Solutions:**

#### For Local Development with Cloud SQL:

1. **Start Cloud SQL Proxy:**
   ```powershell
   # Windows
   scripts\start_sql_proxy.ps1
   ```

2. **Verify DATABASE_URL is set correctly:**
   ```bash
   # Format: postgresql+psycopg://USER:PASSWORD@localhost:PORT/DATABASE
   # Example:
   DATABASE_URL=postgresql+psycopg://myuser:mypass@localhost:5433/mydb
   ```

3. **Test connection directly:**
   ```bash
   # Using psql (if installed)
   psql "$DATABASE_URL" -c "SELECT 1"
   
   # Or using the diagnostic script
   python backend/test_db_connection.py
   ```

#### For Direct Database Connection:

1. **Verify database is running:**
   ```bash
   # Check if PostgreSQL is running
   # Windows: Check Services
   # Linux/Mac: sudo systemctl status postgresql
   ```

2. **Verify DATABASE_URL format:**
   ```
   postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
   ```

3. **Check firewall/network:**
   - Ensure database port is open
   - Verify IP allowlist (if using Cloud SQL)
   - Check VPN connection (if required)

### 2. Missing DATABASE_URL

**Symptoms:**
```
[db] ⚠️  PostgreSQL database configuration missing!
Database configuration missing. Set DATABASE_URL or provide INSTANCE_CONNECTION_NAME + DB_USER + DB_PASS + DB_NAME.
```

**Solutions:**

1. **Set DATABASE_URL in .env.local:**
   ```bash
   # Create or edit backend/.env.local
   DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
   ```

2. **Or set environment variables:**
   ```bash
   # Windows PowerShell
   $env:DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE"
   
   # Linux/Mac
   export DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE"
   ```

3. **Or use Cloud SQL discrete config:**
   ```bash
   INSTANCE_CONNECTION_NAME=PROJECT:REGION:INSTANCE
   DB_USER=your_user
   DB_PASS=your_password
   DB_NAME=your_database
   DB_HOST=localhost  # or Cloud SQL Proxy host
   DB_PORT=5433
   ```

### 3. Invalid DATABASE_URL Format

**Symptoms:**
```
Invalid DATABASE_URL format: ...
Only PostgreSQL is supported, got: ...
```

**Solutions:**

1. **Ensure DATABASE_URL starts with `postgresql://` or `postgresql+psycopg://`:**
   ```
   ✅ Correct: postgresql+psycopg://user:pass@host:port/db
   ❌ Wrong: mysql://user:pass@host:port/db
   ❌ Wrong: postgres://user:pass@host:port/db  (missing +psycopg)
   ```

2. **Verify all components are present:**
   - User
   - Password (URL-encoded if special characters)
   - Host
   - Port (default: 5432)
   - Database name

### 4. Connection Refused

**Symptoms:**
```
connection refused
could not connect to server
```

**Solutions:**

1. **Verify database is running:**
   ```bash
   # Check PostgreSQL service status
   ```

2. **Verify host and port:**
   - Check DATABASE_URL has correct host:port
   - For Cloud SQL Proxy, usually localhost:5433
   - For direct connection, use database server host:port

3. **Check Cloud SQL Proxy (if using):**
   ```bash
   # Verify proxy is running
   # Check if port is correct in DATABASE_URL
   ```

## Configuration Checklist

- [ ] DATABASE_URL is set in .env.local or environment
- [ ] DATABASE_URL format is correct (postgresql+psycopg://...)
- [ ] Database host is reachable from your machine
- [ ] Database port is correct (5432 for direct, 5433 for Cloud SQL Proxy)
- [ ] Database credentials are correct
- [ ] Cloud SQL Proxy is running (if using Cloud SQL locally)
- [ ] Firewall/network allows connection
- [ ] IP allowlist includes your IP (if using Cloud SQL)

## Testing the Connection

### Method 1: Diagnostic Script
```bash
cd backend
python test_db_connection.py
```

### Method 2: Direct psql Test
```bash
# Linux/Mac
psql "$DATABASE_URL" -c "SELECT 1"

# Windows PowerShell
$env:DATABASE_URL="your_connection_string"
psql $env:DATABASE_URL -c "SELECT 1"
```

### Method 3: Python Test
```python
from sqlalchemy import create_engine, text

engine = create_engine("your_database_url")
with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    print(result.fetchone())
```

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| DATABASE_URL | Full database connection string | `postgresql+psycopg://user:pass@host:port/db` |
| INSTANCE_CONNECTION_NAME | Cloud SQL instance name | `project:region:instance` |
| DB_USER | Database user | `myuser` |
| DB_PASS | Database password | `mypassword` |
| DB_NAME | Database name | `mydatabase` |
| DB_HOST | Database host | `localhost` or Cloud SQL host |
| DB_PORT | Database port | `5432` or `5433` |
| DB_CONNECT_TIMEOUT | Connection timeout (seconds) | `10` |
| DB_POOL_SIZE | Connection pool size | `10` |
| DB_MAX_OVERFLOW | Max overflow connections | `10` |

## Getting Help

If you're still having issues:

1. Run the diagnostic script and check the output
2. Check the application logs for detailed error messages
3. Verify your DATABASE_URL format matches the examples above
4. Test the connection using psql or the diagnostic script
5. Check if Cloud SQL Proxy is running (if using Cloud SQL)

## Related Files

- `backend/api/core/database.py` - Database connection configuration
- `backend/test_db_connection.py` - Diagnostic script
- `backend/.env.local` - Local environment variables (create if missing)
- `docs/cloud-run-deploy.md` - Production deployment configuration






