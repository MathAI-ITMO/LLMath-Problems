"""
Конфигурация для LLMath-Problems Backend
Все настройки можно переопределить через переменные окружения
"""
import os


class Config:
    """Конфигурация приложения"""
    
    # CORS настройки
    CORS_ORIGINS = os.environ.get(
        'PROBLEMS_CORS_ORIGINS',
        'http://localhost:8080,https://localhost:8080'
    ).split(',')
    
    # MongoDB настройки
    MONGO_HOST = os.environ.get('MONGO_HOST', 'mongo')
    MONGO_PORT = os.environ.get('MONGO_PORT', '27017')
    MONGO_USER = os.environ.get('MONGO_USER', 'mongoadmin')
    MONGO_PASSWORD = os.environ.get('MONGO_PASSWORD', 'mongoadmin')
    MONGO_DB = os.environ.get('MONGO_DB', 'my_database')
    MONGO_AUTH_SOURCE = os.environ.get('MONGO_AUTH_SOURCE', 'admin')
    
    @property
    def MONGO_DETAILS(self):
        """Строка подключения к MongoDB"""
        return (
            f"mongodb://{self.MONGO_USER}:{self.MONGO_PASSWORD}@"
            f"{self.MONGO_HOST}:{self.MONGO_PORT}/{self.MONGO_DB}?authSource={self.MONGO_AUTH_SOURCE}"
        )


# Создаем экземпляр конфигурации
config = Config()

