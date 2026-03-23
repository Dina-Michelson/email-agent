from dataclasses import dataclass, field


@dataclass
class EmailData:
    message_id: str       # Gmail internal ID
    thread_id: str
    from_: str
    subject: str
    body: str
    date: str
    message_id_header: str = ""  # RFC 2822 Message-ID header (for threading)
    thread_messages: list = field(default_factory=list)  # [{from_, date, body}, ...] oldest-first


@dataclass
class SendResult:
    success: bool
    sent_message_id: str


class EmailNotFoundError(Exception):
    pass


class GmailAPIError(Exception):
    pass


class OpenAIError(Exception):
    pass


class SendFailedError(Exception):
    pass


@dataclass
class ReplyResult:
    reply: str      # generated reply body, plain text
    recipient: str  # resolved recipient email address
