"""Outgoing email: SMTP settings from the environment and a small background sender.

Design rules:
  * SMTP credentials live in environment variables, never in the database or the API.
  * Sending never blocks a request and never makes one fail: messages go on a queue that a worker thread
    drains, retrying briefly, and the outcome is reported through a callback (Core writes it to the audit log).
  * Nothing here knows about passwords or vault contents.  Callers pass finished text.
"""
import os
import queue
import re
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from . import config

RETRY_DELAYS = (3, 20)          # seconds between attempts: three tries in all


class MailError(Exception):
    """A delivery failure, with a message that is safe to show an administrator (no credentials)."""


@dataclass(frozen=True)
class MailSettings:
    host: str = ''
    port: int = 587
    username: str = ''
    password: str = field(default='', repr=False)
    sender: str = ''                  # the From address, e.g. "Kavach <kavach@example.com>"
    security: str = 'starttls'        # starttls | ssl | none
    public_url: str = ''              # base URL for links in emails

    @property
    def configured(self) -> bool:
        return bool(self.host and parseaddr(self.sender)[1])

    @classmethod
    def from_env(cls, env=None) -> 'MailSettings':
        env = os.environ if env is None else env
        security = (env.get('KAVACH_SMTP_SECURITY') or 'starttls').strip().lower()
        if security not in ('starttls', 'ssl', 'none'):
            security = 'starttls'
        try:
            port = int(env.get('KAVACH_SMTP_PORT') or (465 if security == 'ssl' else 587))
        except ValueError:
            port = 587
        public = (env.get('KAVACH_PUBLIC_URL') or f'http://{config.HOST}:{config.PORT}').strip().rstrip('/')
        return cls(host=(env.get('KAVACH_SMTP_HOST') or '').strip(), port=port,
                   username=env.get('KAVACH_SMTP_USER') or '', password=env.get('KAVACH_SMTP_PASSWORD') or '',
                   sender=(env.get('KAVACH_MAIL_FROM') or '').strip(), security=security, public_url=public)


_ADDRESS = re.compile(r"""^[^@\s,;<>"'()\[\]\\]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z0-9-]{2,}$""")


def clean_address(value) -> str:
    """A single plain address (user@host.tld) or ''.  Refuses lists, display names and anything that could
    smuggle a second recipient or a header into the message."""
    value = str(value or '').strip()
    return value if _ADDRESS.match(value) else ''


def _one_line(value: str) -> str:
    return ' '.join(str(value).split())


def build_message(settings: MailSettings, to: str, subject: str, text: str, html: str = '') -> EmailMessage:
    msg = EmailMessage()
    msg['From'] = settings.sender
    msg['To'] = clean_address(to) or _reject(to)
    msg['Subject'] = _one_line(subject)[:200]
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=(parseaddr(settings.sender)[1].rpartition('@')[2] or 'localhost'))
    msg['Auto-Submitted'] = 'auto-generated'            # keeps auto-responders from replying to it
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype='html')
    return msg


def _reject(to):
    raise ValueError('not a single plain email address')


class SmtpTransport:
    """Delivers one message over SMTP.  A new connection per message: mail here is rare and small."""

    def __init__(self, settings: MailSettings, timeout: float = 20.0):
        self.settings = settings
        self.timeout = timeout

    def deliver(self, msg: EmailMessage):
        s = self.settings
        ctx = ssl.create_default_context()
        try:
            if s.security == 'ssl':
                smtp = smtplib.SMTP_SSL(s.host, s.port, timeout=self.timeout, context=ctx)
            else:
                smtp = smtplib.SMTP(s.host, s.port, timeout=self.timeout)
            with smtp:
                smtp.ehlo()
                if s.security == 'starttls':
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                if s.username:
                    smtp.login(s.username, s.password)
                smtp.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            raise MailError('The mail server rejected the username or password.') from None
        except smtplib.SMTPRecipientsRefused:
            raise MailError('The mail server refused the recipient address.') from None
        except smtplib.SMTPSenderRefused:
            raise MailError('The mail server refused the sender address (KAVACH_MAIL_FROM).') from None
        except ssl.SSLError as e:
            raise MailError(f'TLS problem talking to the mail server: {e.reason or "handshake failed"}.') from None
        except (smtplib.SMTPException, OSError) as e:
            raise MailError(f'Could not deliver through {s.host}:{s.port} ({type(e).__name__}).') from None


class MemoryTransport:
    """Collects messages instead of sending them (tests, and a safe stand-in for a dry run)."""

    def __init__(self):
        self.sent = []
        self.fail_with = None

    def deliver(self, msg: EmailMessage):
        if self.fail_with:
            raise MailError(self.fail_with)
        self.sent.append(msg)


class Mailer:
    """Queues messages and delivers them from a worker thread.  `sync=True` delivers inline (tests)."""

    def __init__(self, settings: MailSettings, transport=None, on_result=None, sync=False):
        self.settings = settings
        self.transport = transport or SmtpTransport(settings)
        self.on_result = on_result or (lambda kind, to, ok, error: None)
        self.sync = sync
        self._queue = queue.Queue(maxsize=200)
        self._thread = None
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return self.settings.configured

    # ── queued sending ────────────────────────────────────────────────────
    def send(self, to: str, kind: str, subject: str, text: str, html: str = '') -> bool:
        """Queue a message.  Returns whether it was accepted for delivery (False: mail is not set up, the
        address is empty, or the queue is full).  Never raises."""
        to = clean_address(to)
        if not self.configured or not to:
            return False
        try:
            msg = build_message(self.settings, to, subject, text, html)
        except ValueError:
            return False
        if self.sync:
            self._attempt(kind, to, msg, retries=False)
            return True
        try:
            self._queue.put_nowait((kind, to, msg))
        except queue.Full:
            return False
        self._ensure_worker()
        return True

    def _ensure_worker(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name='kavach-mail', daemon=True)
                self._thread.start()

    def _run(self):
        while True:
            kind, to, msg = self._queue.get()
            self._attempt(kind, to, msg, retries=True)
            self._queue.task_done()

    def _attempt(self, kind, to, msg, retries):
        delays = RETRY_DELAYS if retries else ()
        error = ''
        for attempt in range(len(delays) + 1):
            try:
                self.transport.deliver(msg)
                self._report(kind, to, True, '')
                return
            except MailError as e:
                error = str(e)
            except Exception as e:                           # a bug must not kill the worker
                error = f'Unexpected error ({type(e).__name__}).'
            if attempt < len(delays):
                time.sleep(delays[attempt])
        self._report(kind, to, False, error)

    def _report(self, kind, to, ok, error):
        try:
            self.on_result(kind, to, ok, error)
        except Exception:
            pass

    def drain(self, timeout=5.0) -> bool:
        """Wait until the queue is empty (used on shutdown and in tests)."""
        end = time.time() + timeout
        while time.time() < end:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.02)
        return False

    # ── immediate sending (the admin's "send a test email") ───────────────
    def send_now(self, to: str, subject: str, text: str, html: str = ''):
        """Deliver inline and raise MailError with the reason, so an administrator sees what is wrong."""
        if not self.configured:
            raise MailError('Email is not set up on this server (see KAVACH_SMTP_HOST in the README).')
        try:
            msg = build_message(self.settings, to, subject, text, html)
        except ValueError:
            raise MailError('That address or subject cannot be used in an email.') from None
        self.transport.deliver(msg)
