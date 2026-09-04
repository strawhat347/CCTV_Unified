-- =====================================================================
-- CCTV Unified Surveillance MVP — Database Schema
-- Engine: InnoDB (required for foreign keys + row-level locking)
-- Charset: utf8mb4 (full Unicode support, avoids truncation)
-- =====================================================================

CREATE DATABASE IF NOT EXISTS cctv_unified
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE cctv_unified;

-- ---------------------------------------------------------------------
-- cameras: one row per physical camera
-- ---------------------------------------------------------------------
CREATE TABLE cameras (
    camera_id       INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    location        VARCHAR(150),
    city            VARCHAR(100),
    district        VARCHAR(100),
    department      VARCHAR(100),
    department_id   INT,
    latitude        DECIMAL(10, 8),
    longitude       DECIMAL(11, 8),
    camera_type     VARCHAR(50),                -- Added for Hackathon Model 1 (PTZ, Bullet, etc)
    connectivity    VARCHAR(50),                -- Added for Hackathon Model 1 (LAN, 4G, Fiber)
    storage_details VARCHAR(100),               -- Added for Hackathon Model 1 (Local 7-day, Cloud 15-day)
    stream_url      VARCHAR(255) NOT NULL,
    status          ENUM('active', 'inactive', 'error') NOT NULL DEFAULT 'active',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- detections: one row per detected object per frame (high-volume)
-- ---------------------------------------------------------------------
CREATE TABLE detections (
    detection_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
    camera_id     INT NULL,
    detected_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    object_type   VARCHAR(50) NOT NULL,
    confidence    FLOAT NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    bbox_x        INT NOT NULL,
    bbox_y        INT NOT NULL,
    bbox_w        INT NOT NULL,
    bbox_h        INT NOT NULL,
    image_path    VARCHAR(255),
    plate_text    VARCHAR(20),
    location      VARCHAR(150),

    CONSTRAINT fk_detections_camera
        FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
        ON DELETE SET NULL,

    INDEX idx_camera_time (camera_id, detected_at),
    INDEX idx_object_type (object_type),
    INDEX idx_plate_text (plate_text)
) ENGINE=InnoDB
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;



-- ---------------------------------------------------------------------
-- alerts: triggered alerts, optionally linked to a detection
-- ---------------------------------------------------------------------
CREATE TABLE alerts (
    alert_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    detection_id  BIGINT NULL,
    camera_id     INT NULL,
    alert_type    VARCHAR(50) NOT NULL,
    severity      ENUM('low', 'medium', 'high') NOT NULL DEFAULT 'medium',
    message       TEXT,
    location      VARCHAR(150),
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acknowledged  BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT fk_alerts_detection
        FOREIGN KEY (detection_id) REFERENCES detections(detection_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_alerts_camera
        FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
        ON DELETE SET NULL,

    INDEX idx_ack_created (acknowledged, created_at),
    INDEX idx_alerts_camera (camera_id),
    INDEX idx_alerts_detection (detection_id)
) ENGINE=InnoDB
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- users: authentication & role-based access control
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role        ENUM('admin', 'operator', 'auditor') NOT NULL DEFAULT 'operator',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    last_login  TIMESTAMP NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_username (username)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- audit_logs: immutable log of security-relevant events
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NULL,
    event_type  VARCHAR(50) NOT NULL,
    ip_address  VARCHAR(45),
    resource    VARCHAR(255),
    details     TEXT,
    timestamp   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_event_type (event_type),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;