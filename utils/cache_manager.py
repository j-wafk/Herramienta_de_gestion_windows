# utils/cache_manager.py
import time
import threading
from config import Config

class CacheManager:
    def __init__(self):
        self.cache = {
            "cpu": {"timestamp": 0, "data": {"value": 0, "history": [0]*15}},
            "memory": {"timestamp": 0, "data": {"value": 0, "history": [0]*15}},
            "processes": {"timestamp": 0, "data": []},
            "disk": {"timestamp": 0, "data": {"used": 0, "free": 100}},
            "disks": {"timestamp": 0, "data": []},
            "partitions": {"timestamp": 0, "data": {}}
        }
        self.lock = threading.Lock()
    
    def is_cache_valid(self, cache_key):
        """Verifica si el caché es válido"""
        current_time = time.time()
        return (current_time - self.cache[cache_key]["timestamp"]) <= Config.CACHE_TIME
    
    def get_cache_data(self, cache_key):
        """Obtiene datos del caché"""
        with self.lock:
            return self.cache[cache_key]["data"]
    
    def update_cache(self, cache_key, data):
        """Actualiza el caché con nuevos datos"""
        with self.lock:
            self.cache[cache_key]["timestamp"] = time.time()
            
            if cache_key in ["cpu", "memory"]:
                # Para CPU y memoria, mantener historial
                self.cache[cache_key]["data"]["value"] = data
                self.cache[cache_key]["data"]["history"].pop(0)
                self.cache[cache_key]["data"]["history"].append(data)
            else:
                # Para otros datos, simplemente actualizar
                self.cache[cache_key]["data"] = data
    
    def get_all_system_data(self):
        """Obtiene todos los datos del sistema desde el caché"""
        with self.lock:
            return {
                "cpu": self.cache["cpu"]["data"],
                "memory": self.cache["memory"]["data"],
                "processes": self.cache["processes"]["data"],
                "disk": self.cache["disk"]["data"]
            }