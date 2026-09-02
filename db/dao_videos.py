from typing import List, Dict, Optional
from db.connection_pool import get_connection

def create_videos_table():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS video_files (
                id INT AUTO_INCREMENT PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                filepath VARCHAR(512) NOT NULL,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def insert_video(filename: str, filepath: str) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO video_files (filename, filepath) VALUES (%s, %s)', (filename, filepath))
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()

def get_all_videos() -> List[Dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM video_files ORDER BY uploaded_at DESC')
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

def get_video_by_id(video_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM video_files WHERE id = %s', (video_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def delete_video(video_id: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM video_files WHERE id = %s', (video_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()
