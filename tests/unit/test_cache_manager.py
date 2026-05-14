"""Tests unitarios para utils/cache_manager.py — testea la API real."""
import time
import threading
import pytest
from utils.cache_manager import CacheManager


class TestCacheManager:

    @pytest.fixture
    def cache_manager(self):
        return CacheManager()

    # ── Inicialización ─────────────────────────────────────────────────────

    def test_cache_initialization_has_default_keys(self, cache_manager):
        for key in ('cpu', 'memory', 'processes', 'disk'):
            assert key in cache_manager.cache

    def test_initial_timestamp_is_zero(self, cache_manager):
        assert cache_manager.cache['cpu']['timestamp'] == 0

    # ── update_cache / get_cache_data ──────────────────────────────────────

    def test_update_cache_disk_stores_value(self, cache_manager):
        cache_manager.update_cache('disk', {'used': 40, 'free': 60})
        data = cache_manager.get_cache_data('disk')
        assert data == {'used': 40, 'free': 60}

    def test_update_cache_processes_stores_list(self, cache_manager):
        procs = [{'name': 'python.exe', 'pid': '1234', 'cpu': 5.0}]
        cache_manager.update_cache('processes', procs)
        assert cache_manager.get_cache_data('processes') == procs

    def test_update_cache_cpu_builds_history(self, cache_manager):
        cache_manager.update_cache('cpu', 45.0)
        data = cache_manager.get_cache_data('cpu')
        assert data['value'] == 45.0
        assert 45.0 in data['history']
        assert len(data['history']) == 15

    def test_update_cache_memory_builds_history(self, cache_manager):
        cache_manager.update_cache('memory', 70.0)
        data = cache_manager.get_cache_data('memory')
        assert data['value'] == 70.0
        assert len(data['history']) == 15

    def test_cpu_history_circular_buffer(self, cache_manager):
        for i in range(20):
            cache_manager.update_cache('cpu', float(i))
        data = cache_manager.get_cache_data('cpu')
        assert len(data['history']) == 15
        assert data['history'][-1] == 19.0

    def test_update_cache_updates_timestamp(self, cache_manager):
        cache_manager.update_cache('disk', {'used': 1, 'free': 99})
        ts = cache_manager.cache['disk']['timestamp']
        assert ts > 0

    # ── is_cache_valid ─────────────────────────────────────────────────────

    def test_is_cache_valid_fresh_data(self, cache_manager):
        cache_manager.update_cache('disk', {'used': 1, 'free': 99})
        assert cache_manager.is_cache_valid('disk') is True

    def test_is_cache_valid_stale_timestamp(self, cache_manager):
        cache_manager.update_cache('disk', {'used': 1, 'free': 99})
        cache_manager.cache['disk']['timestamp'] = 0
        assert cache_manager.is_cache_valid('disk') is False

    # ── get_all_system_data ────────────────────────────────────────────────

    def test_get_all_system_data_returns_four_keys(self, cache_manager):
        data = cache_manager.get_all_system_data()
        assert set(data.keys()) == {'cpu', 'memory', 'processes', 'disk'}

    # ── Concurrencia ───────────────────────────────────────────────────────

    def test_concurrent_disk_updates(self, cache_manager):
        def update():
            for i in range(50):
                cache_manager.update_cache('disk', {'used': i, 'free': 100 - i})

        threads = [threading.Thread(target=update) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        result = cache_manager.get_cache_data('disk')
        assert 'used' in result
