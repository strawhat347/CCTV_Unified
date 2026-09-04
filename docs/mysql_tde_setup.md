# MySQL Transparent Data Encryption (TDE) Setup Guide

This guide documents how to enable Transparent Data Encryption (TDE) on
MySQL 8.0+ for the CCTV Unified database. TDE encrypts table data at rest
so that if the physical disk (or a database backup file) is stolen, the
attacker cannot read the license plate records, user credentials, or
alert history without the encryption key.

> **Important**: TDE is configured at the MySQL **server** level, not in
> application code. These commands are run once by the DBA.

---

## Prerequisites

- MySQL 8.0.16+ (InnoDB tablespace encryption GA)
- The `keyring_file` plugin (ships with MySQL, no extra install)

---

## Step 1: Enable the Keyring Plugin

Edit `my.cnf` (Linux) or `my.ini` (Windows) and add:

```ini
[mysqld]
early-plugin-load = keyring_file.so          # Linux
# early-plugin-load = keyring_file.dll       # Windows

keyring_file_data = /var/lib/mysql-keyring/keyring
```

Restart MySQL:

```bash
sudo systemctl restart mysql
```

Verify:

```sql
SELECT PLUGIN_NAME, PLUGIN_STATUS FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME = 'keyring_file';
-- Should show: keyring_file | ACTIVE
```

---

## Step 2: Enable Default Table Encryption

For MySQL 8.0.16+, you can enable encryption by default for the entire
database schema so that every new table is automatically encrypted:

```sql
ALTER DATABASE cctv_unified DEFAULT ENCRYPTION = 'Y';
```

---

## Step 3: Encrypt Existing Tables

Run these ALTER statements to encrypt each existing table in-place.
InnoDB rebuilds the tablespace file with AES-256-CBC encryption. This is
an **online** operation — the table stays readable during conversion.

```sql
-- Core surveillance data
ALTER TABLE cameras       ENCRYPTION = 'Y';
ALTER TABLE detections    ENCRYPTION = 'Y';
ALTER TABLE alerts        ENCRYPTION = 'Y';

-- User credentials and audit trail
ALTER TABLE users         ENCRYPTION = 'Y';
ALTER TABLE audit_logs    ENCRYPTION = 'Y';

-- Uploaded video metadata
ALTER TABLE video_files   ENCRYPTION = 'Y';
```

Verify encryption status:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME, CREATE_OPTIONS
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'cctv_unified';
-- Every row should show: ENCRYPTION="Y"
```

---

## Step 4: Encrypt the Redo Log and Undo Log

These logs can contain plaintext copies of encrypted table data:

```sql
ALTER INSTANCE ROTATE INNODB MASTER KEY;
```

In `my.cnf`:

```ini
[mysqld]
innodb_redo_log_encrypt = ON
innodb_undo_log_encrypt = ON
```

Restart MySQL for redo/undo log encryption to take effect.

---

## Step 5: Encrypt Binary Logs (Optional, for replication setups)

```sql
SET PERSIST binlog_encryption = ON;
```

---

## Key Rotation

Rotate the master encryption key periodically (e.g., quarterly):

```sql
ALTER INSTANCE ROTATE INNODB MASTER KEY;
```

This re-wraps all per-table keys with a new master key. No table rebuild
required — instant operation.

---

## Verification Checklist

- [ ] `keyring_file` plugin shows as ACTIVE
- [ ] `DEFAULT ENCRYPTION = 'Y'` on the `cctv_unified` database
- [ ] All 6 tables show `ENCRYPTION="Y"` in `CREATE_OPTIONS`
- [ ] `innodb_redo_log_encrypt = ON`
- [ ] `innodb_undo_log_encrypt = ON`
- [ ] Key rotation schedule documented in ops runbook
