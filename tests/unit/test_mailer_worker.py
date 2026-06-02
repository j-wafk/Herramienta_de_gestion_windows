"""Tests unitarios para utils/mailer_worker.py."""
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pytest

os.environ.setdefault('SECRET_KEY', 'test_secret')
os.environ.setdefault('ADMIN_PASSWORD', 'Admin12345678!')
os.environ.setdefault('FIELD_ENCRYPTION_KEY', 'test_field_encryption_key_32bytes!!')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')


@pytest.fixture(scope='module')
def app():
    from main import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def cleanup_queue(app):
    """Limpia EmailQueue antes y después de cada test."""
    with app.app_context():
        from database import db
        from database.models import EmailQueue
        EmailQueue.query.delete()
        db.session.commit()
    yield
    with app.app_context():
        from database import db
        from database.models import EmailQueue
        EmailQueue.query.delete()
        db.session.commit()


class TestNextRetry:
    def test_first_retry_30s(self):
        from utils.mailer_worker import _next_retry
        before = datetime.utcnow()
        result = _next_retry(1)
        delta = (result - before).total_seconds()
        assert 28 <= delta <= 32

    def test_second_retry_2min(self):
        from utils.mailer_worker import _next_retry
        before = datetime.utcnow()
        result = _next_retry(2)
        delta = (result - before).total_seconds()
        assert 118 <= delta <= 122

    def test_third_retry_10min(self):
        from utils.mailer_worker import _next_retry
        before = datetime.utcnow()
        result = _next_retry(3)
        delta = (result - before).total_seconds()
        assert 598 <= delta <= 602

    def test_unknown_uses_3600(self):
        from utils.mailer_worker import _next_retry
        before = datetime.utcnow()
        result = _next_retry(99)
        delta = (result - before).total_seconds()
        assert 3598 <= delta <= 3602


class TestRunOneCycle:
    def test_empty_queue_returns_zero(self, app, cleanup_queue):
        from utils.mailer_worker import run_one_cycle
        assert run_one_cycle(app) == 0

    @patch('utils.mailer.send_email', return_value=True)
    def test_successful_send(self, mock_send, app, cleanup_queue):
        from utils.mailer_worker import run_one_cycle
        from database import db
        from database.models import EmailQueue

        with app.app_context():
            q = EmailQueue(
                to_addr='test@example.com',
                subject='Hello',
                body_html='<p>hi</p>',
                body_text='hi',
                status='queued',
            )
            db.session.add(q)
            db.session.commit()
            qid = q.id

        result = run_one_cycle(app)
        assert result == 1

        with app.app_context():
            sent = EmailQueue.query.get(qid)
            assert sent.status == 'sent'
            assert sent.sent_at is not None

    @patch('utils.mailer.send_email', return_value=False)
    def test_failed_send_increments_tries(self, mock_send, app, cleanup_queue):
        from utils.mailer_worker import run_one_cycle
        from database import db
        from database.models import EmailQueue

        with app.app_context():
            q = EmailQueue(
                to_addr='test@example.com',
                subject='Hello',
                body_html='<p>hi</p>',
                status='queued',
            )
            db.session.add(q)
            db.session.commit()
            qid = q.id

        result = run_one_cycle(app)
        assert result == 0

        with app.app_context():
            failed = EmailQueue.query.get(qid)
            assert failed.tries == 1
            assert failed.status == 'queued'  # Reprogramada
            assert failed.last_error is not None

    @patch('utils.mailer.send_email', return_value=False)
    def test_max_tries_marks_failed(self, mock_send, app, cleanup_queue):
        from utils.mailer_worker import run_one_cycle
        from database import db
        from database.models import EmailQueue

        with app.app_context():
            q = EmailQueue(
                to_addr='test@example.com',
                subject='Final',
                body_html='<p>hi</p>',
                status='queued',
                tries=4,  # next try will be 5 → MAX
            )
            db.session.add(q)
            db.session.commit()
            qid = q.id

        run_one_cycle(app)

        with app.app_context():
            final = EmailQueue.query.get(qid)
            assert final.status == 'failed'
            assert final.tries == 5

    @patch('utils.mailer.send_email', side_effect=RuntimeError('boom'))
    def test_exception_during_send_records_error(self, mock_send, app, cleanup_queue):
        from utils.mailer_worker import run_one_cycle
        from database import db
        from database.models import EmailQueue

        with app.app_context():
            q = EmailQueue(
                to_addr='test@example.com',
                subject='Exc',
                body_html='<p>hi</p>',
                status='queued',
            )
            db.session.add(q)
            db.session.commit()
            qid = q.id

        run_one_cycle(app)

        with app.app_context():
            errored = EmailQueue.query.get(qid)
            assert errored.last_error is not None
            assert 'RuntimeError' in errored.last_error

    @patch('utils.mailer.send_email', return_value=True)
    def test_future_scheduled_not_processed(self, mock_send, app, cleanup_queue):
        from utils.mailer_worker import run_one_cycle
        from database import db
        from database.models import EmailQueue

        with app.app_context():
            future = datetime.utcnow() + timedelta(hours=1)
            q = EmailQueue(
                to_addr='test@example.com',
                subject='Future',
                body_html='<p>hi</p>',
                status='queued',
                scheduled_at=future,
            )
            db.session.add(q)
            db.session.commit()
            qid = q.id

        result = run_one_cycle(app)
        assert result == 0

        with app.app_context():
            still_queued = EmailQueue.query.get(qid)
            assert still_queued.status == 'queued'
            assert still_queued.tries == 0
