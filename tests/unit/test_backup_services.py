# tests/unit/test_backup_services.py
"""Tests unitarios para utilidades del módulo de backup que no requieren Flask app."""
from datetime import datetime

from modules.backup.services import compute_next_run
from utils.validators import (
    validate_id, validate_enum, validate_schedule_time,
    ALLOWED_DESTINATION_TYPES, ALLOWED_JOB_SCHEDULES,
)


class TestComputeNextRun:
    def test_daily_misma_hora_aun_no_pasada(self):
        # Si ahora son las 10:00 y schedule_time es 23:00 → hoy mismo
        now = datetime(2026, 5, 8, 10, 0, 0)
        nxt = compute_next_run('daily', '23:00', now=now)
        assert nxt == datetime(2026, 5, 8, 23, 0, 0)

    def test_daily_hora_ya_pasada_va_a_manana(self):
        now = datetime(2026, 5, 8, 23, 30, 0)
        nxt = compute_next_run('daily', '02:00', now=now)
        assert nxt == datetime(2026, 5, 9, 2, 0, 0)

    def test_weekly_lanza_lunes(self):
        # 2026-05-08 es viernes; el lunes siguiente es 2026-05-11
        now = datetime(2026, 5, 8, 10, 0, 0)
        nxt = compute_next_run('weekly', '02:00', now=now)
        assert nxt.weekday() == 0
        assert nxt == datetime(2026, 5, 11, 2, 0, 0)

    def test_monthly_dia_1_mes_siguiente(self):
        now = datetime(2026, 5, 8, 10, 0, 0)
        nxt = compute_next_run('monthly', '02:00', now=now)
        assert nxt == datetime(2026, 6, 1, 2, 0, 0)

    def test_monthly_diciembre_pasa_a_enero_siguiente_anio(self):
        now = datetime(2026, 12, 15, 10, 0, 0)
        nxt = compute_next_run('monthly', '02:00', now=now)
        assert nxt == datetime(2027, 1, 1, 2, 0, 0)

    def test_manual_devuelve_none(self):
        assert compute_next_run('manual', '02:00') is None


class TestValidators:
    def test_validate_id_ok(self):
        assert validate_id(5) == 5
        assert validate_id('42') == 42

    def test_validate_id_negativo(self):
        import pytest
        with pytest.raises(ValueError):
            validate_id(-1)

    def test_validate_id_no_numero(self):
        import pytest
        with pytest.raises(ValueError):
            validate_id('foo')

    def test_destination_types_completos(self):
        assert validate_enum('local', ALLOWED_DESTINATION_TYPES, 't') == 'local'
        assert validate_enum('network', ALLOWED_DESTINATION_TYPES, 't') == 'network'

    def test_job_schedules_incluyen_manual(self):
        assert 'manual' in ALLOWED_JOB_SCHEDULES
        assert 'daily' in ALLOWED_JOB_SCHEDULES

    def test_schedule_time(self):
        assert validate_schedule_time('02:00') == '02:00'
        assert validate_schedule_time('23:59') == '23:59'

    def test_schedule_time_invalido(self):
        import pytest
        with pytest.raises(ValueError):
            validate_schedule_time('25:00')
        with pytest.raises(ValueError):
            validate_schedule_time('abc')
