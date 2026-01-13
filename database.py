import sqlite3
import os
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

class DatabaseManager:
    def __init__(self, db_path: str = "karwa_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with required tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Users allowed table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users_allowed (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    added_by_user_id INTEGER,
                    is_owner BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Generation logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS generation_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    generation_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    command_used TEXT,
                    output_type TEXT,
                    prompt_used TEXT,
                    success BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users_allowed (user_id)
                )
            ''')
            
            # Daily usage table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_usage (
                    user_id INTEGER PRIMARY KEY,
                    last_generation_date DATE,
                    generations_count INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users_allowed (user_id)
                )
            ''')
            
            # Add owner if not exists
            owner_id = int(os.getenv('OWNER_USER_ID', '6942195606'))
            owner_username = os.getenv('OWNER_USERNAME', 'Escobaar100x')
            
            cursor.execute('''
                INSERT OR IGNORE INTO users_allowed 
                (user_id, username, added_by_user_id, is_owner)
                VALUES (?, ?, ?, TRUE)
            ''', (owner_id, owner_username, owner_id))
            
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def is_user_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to use the bot"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users_allowed WHERE user_id = ?', (user_id,))
            return cursor.fetchone() is not None
    
    def add_user(self, user_id: int, username: str, added_by: int) -> bool:
        """Add user to allowed list"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users_allowed (user_id, username, added_by_user_id)
                    VALUES (?, ?, ?)
                ''', (user_id, username, added_by))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False
    
    def remove_user(self, user_id: int) -> bool:
        """Remove user from allowed list (cannot remove owner)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Check if user is owner
            cursor.execute('SELECT is_owner FROM users_allowed WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            if result and result['is_owner']:
                return False
            
            cursor.execute('DELETE FROM users_allowed WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM daily_usage WHERE user_id = ?', (user_id,))
            conn.commit()
            return True
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all allowed users"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, added_date, added_by_user_id, is_owner
                FROM users_allowed
                ORDER BY added_date DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def can_user_generate(self, user_id: int) -> Dict[str, Any]:
        """Check if user can generate and return status"""
        owner_id = int(os.getenv('OWNER_USER_ID', '6942195606'))
        
        # Owner has unlimited access
        if user_id == owner_id:
            return {'can_generate': True, 'is_owner': True, 'remaining': 999}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get or create daily usage record
            cursor.execute('SELECT * FROM daily_usage WHERE user_id = ?', (user_id,))
            usage = cursor.fetchone()
            
            today = date.today()
            
            if not usage:
                # First time user
                cursor.execute('''
                    INSERT INTO daily_usage (user_id, last_generation_date, generations_count)
                    VALUES (?, ?, 0)
                ''', (user_id, today))
                conn.commit()
                return {'can_generate': True, 'remaining': 1, 'last_reset': today}
            
            # Check if we need to reset counter
            if usage['last_generation_date'] != today:
                cursor.execute('''
                    UPDATE daily_usage 
                    SET last_generation_date = ?, generations_count = 0
                    WHERE user_id = ?
                ''', (today, user_id))
                conn.commit()
                return {'can_generate': True, 'remaining': 1, 'last_reset': today}
            
            # Check daily limit
            if usage['generations_count'] >= 1:
                return {
                    'can_generate': False, 
                    'remaining': 0, 
                    'last_reset': usage['last_generation_date']
                }
            
            return {
                'can_generate': True, 
                'remaining': 1 - usage['generations_count'], 
                'last_reset': usage['last_generation_date']
            }
    
    def record_generation(self, user_id: int, command_used: str, output_type: str, prompt_used: str = None):
        """Record a generation and update daily usage"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Log generation
            cursor.execute('''
                INSERT INTO generation_logs 
                (user_id, command_used, output_type, prompt_used)
                VALUES (?, ?, ?, ?)
            ''', (user_id, command_used, output_type, prompt_used))
            
            # Update daily usage (skip owner)
            owner_id = int(os.getenv('OWNER_USER_ID', '6942195606'))
            if user_id != owner_id:
                cursor.execute('''
                    UPDATE daily_usage 
                    SET generations_count = generations_count + 1,
                        last_generation_date = ?
                    WHERE user_id = ?
                ''', (date.today(), user_id))
            
            conn.commit()
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Today's stats
            today = date.today()
            cursor.execute('''
                SELECT COUNT(*) as total_today, COUNT(DISTINCT user_id) as active_today
                FROM generation_logs 
                WHERE DATE(generation_timestamp) = ?
            ''', (today,))
            today_stats = cursor.fetchone()
            
            # All time stats
            cursor.execute('''
                SELECT COUNT(*) as total_all, COUNT(DISTINCT user_id) as users_all
                FROM generation_logs
            ''')
            all_stats = cursor.fetchone()
            
            # Most active today
            cursor.execute('''
                SELECT u.username, COUNT(*) as count
                FROM generation_logs gl
                JOIN users_allowed u ON gl.user_id = u.user_id
                WHERE DATE(gl.generation_timestamp) = ?
                GROUP BY gl.user_id, u.username
                ORDER BY count DESC
                LIMIT 1
            ''', (today,))
            most_active_today = cursor.fetchone()
            
            # Top user all time
            cursor.execute('''
                SELECT u.username, COUNT(*) as count
                FROM generation_logs gl
                JOIN users_allowed u ON gl.user_id = u.user_id
                GROUP BY gl.user_id, u.username
                ORDER BY count DESC
                LIMIT 1
            ''')
            top_user_all = cursor.fetchone()
            
            return {
                'today': {
                    'total_generations': today_stats['total_today'],
                    'active_users': today_stats['active_today'],
                    'most_active': {
                        'username': most_active_today['username'] if most_active_today else None,
                        'count': most_active_today['count'] if most_active_today else 0
                    }
                },
                'all_time': {
                    'total_generations': all_stats['total_all'],
                    'total_users': all_stats['users_all'],
                    'top_user': {
                        'username': top_user_all['username'] if top_user_all else None,
                        'count': top_user_all['count'] if top_user_all else 0
                    }
                }
            }
    
    def get_user_daily_count(self, user_id: int) -> int:
        """Get user's generation count for today"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT generations_count FROM daily_usage WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            return result['generations_count'] if result else 0
