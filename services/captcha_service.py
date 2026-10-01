"""Image captcha (letters + digits) used on signup and, adaptively, on login.

Design (no third-party captcha service, no e-mail):
* ``issue_challenge`` draws a random code (default 6 chars, unambiguous alphabet, always at least one
  letter and one digit), renders it as a distorted PNG (per-character rotation/offset, sine warp,
  noise lines and dots) and stores only an HMAC of the answer (keyed with SECRET_KEY) plus an expiry.
* ``verify`` is **single use**: the challenge row is deleted on the first attempt, right or wrong,
  so a challenge can never be brute-forced or replayed. Answers are case-insensitive.
* Issuing is rate limited per client IP, so a bot cannot mint unlimited challenges (each signup needs one).
"""
import base64
import hashlib
import hmac
import io
import secrets
from datetime import timedelta

from api.settings import get_settings
from models import security_queries as sq
from services.auth_service import ValidationError

LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ"  # no I, L, O (look like 1/0)
DIGITS = "23456789"                  # no 0, 1
WIDTH, HEIGHT = 240, 84

_rng = secrets.SystemRandom()


class CaptchaError(ValidationError):
    """Missing / expired / wrong captcha -> HTTP 400 with fields.captcha."""

    def __init__(self, message="The captcha is incorrect."):
        super().__init__(message, "captcha")


class CaptchaRateLimitError(ValidationError):
    """Too many captchas requested from this IP -> HTTP 429."""


def normalize_answer(answer):
    return "".join((answer or "").split()).upper()


def _hash_answer(challenge_id, answer):
    key = str(get_settings().secret_key).encode("utf-8")
    return hmac.new(key, f"captcha:{challenge_id}:{answer}".encode("utf-8"), hashlib.sha256).hexdigest()


def _random_text(length):
    chars = [_rng.choice(LETTERS), _rng.choice(DIGITS)]
    chars += [_rng.choice(LETTERS + DIGITS) for _ in range(max(0, length - 2))]
    _rng.shuffle(chars)
    return "".join(chars)


def _render_png(text):
    """Distorted captcha image for ``text`` as PNG bytes."""
    import math

    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    def rc(lo, hi):
        return (_rng.randint(lo, hi), _rng.randint(lo, hi), _rng.randint(lo, hi))

    img = Image.new("RGB", (WIDTH, HEIGHT), rc(225, 245))
    draw = ImageDraw.Draw(img)
    for _ in range(6):  # background clutter
        draw.line([(_rng.randint(0, WIDTH), _rng.randint(0, HEIGHT)),
                   (_rng.randint(0, WIDTH), _rng.randint(0, HEIGHT))], fill=rc(150, 210), width=_rng.randint(1, 3))

    font = ImageFont.load_default(size=46)
    step = (WIDTH - 30) / len(text)
    for i, ch in enumerate(text):
        layer = Image.new("RGBA", (70, 70), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((12, 8), ch, font=font, fill=rc(10, 110) + (255,), stroke_width=1,
                                   stroke_fill=rc(0, 60) + (255,))
        layer = layer.rotate(_rng.uniform(-28, 28), resample=Image.BICUBIC, expand=False)
        img.paste(layer, (int(12 + i * step), _rng.randint(-2, 12)), layer)

    for _ in range(4):  # strike-through lines on top of the text
        draw.line([(0, _rng.randint(10, HEIGHT - 10)), (WIDTH, _rng.randint(10, HEIGHT - 10))],
                  fill=rc(40, 140), width=2)
    for _ in range(260):
        draw.point((_rng.randint(0, WIDTH - 1), _rng.randint(0, HEIGHT - 1)), fill=rc(0, 200))

    warped = Image.new("RGB", (WIDTH, HEIGHT), rc(225, 245))  # sine warp, column by column
    amp, period, phase = _rng.uniform(2.5, 4.5), _rng.uniform(40, 70), _rng.uniform(0, 6.28)
    for x in range(WIDTH):
        dy = int(amp * math.sin(2 * math.pi * x / period + phase))
        warped.paste(img.crop((x, 0, x + 1, HEIGHT)), (x, dy))
    warped = warped.filter(ImageFilter.SMOOTH)

    buf = io.BytesIO()
    warped.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def issue_challenge(ip=None):
    """Create a challenge. Returns {"captcha_id", "image" (data URL), "expires_in_seconds"}."""
    cfg = get_settings()
    if ip and sq.count_recent_captchas_for_ip(ip, 60) >= cfg.captcha_max_per_ip_per_hour:
        raise CaptchaRateLimitError("Too many captcha requests. Please try again later.")
    text = _random_text(cfg.captcha_length)
    challenge_id = secrets.token_urlsafe(24)
    expires_at = sq.fmt(sq.utcnow() + timedelta(minutes=cfg.captcha_expiry_minutes))
    sq.create_captcha(challenge_id, _hash_answer(challenge_id, text), expires_at, ip)
    image = "data:image/png;base64," + base64.b64encode(_render_png(text)).decode("ascii")
    return {"captcha_id": challenge_id, "image": image, "expires_in_seconds": cfg.captcha_expiry_minutes * 60}


def verify(challenge_id, answer):
    """Consume the challenge and check the answer. Raises CaptchaError unless it is correct.
    The challenge is deleted on the first attempt, so each one gets exactly one guess."""
    if not challenge_id or not isinstance(challenge_id, str) or not normalize_answer(answer):
        raise CaptchaError("Please type the characters shown in the image.")
    row = sq.consume_captcha(challenge_id)
    if row is None:
        raise CaptchaError("This captcha has expired or was already used. A new one has been loaded.")
    expires = sq.parse_ts(row["expires_at"])
    if expires is None or sq.utcnow() > expires:
        raise CaptchaError("This captcha has expired. A new one has been loaded.")
    expected = _hash_answer(challenge_id, normalize_answer(answer))
    if not hmac.compare_digest(expected, row["answer_hash"]):
        raise CaptchaError("Incorrect captcha. A new one has been loaded.")
