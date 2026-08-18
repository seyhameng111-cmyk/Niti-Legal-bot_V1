from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.gas_client import GasClient
from app.handlers import BotHandlers
from app.processor import QueueFullError, UpdateProcessor
from app.rate_limit import SlidingWindowRateLimiter
from app.state import MemoryStateStore
from app.telegram_api import TelegramAPI, TelegramApiError

APP_VERSION = "2.1.0"

logging.basicConfig(
    level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
# httpx logs the full Telegram Bot API URL, which contains the bot token.
# Keep transport logs disabled in production to prevent credential disclosure.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        telegram = TelegramAPI(config.telegram_bot_token.get_secret_value())
        gas = GasClient(config)
        state_store = MemoryStateStore()
        rate_limiter = SlidingWindowRateLimiter(
            config.rate_limit_questions, config.rate_limit_window_seconds
        )
        handlers = BotHandlers(config, telegram, gas, state_store, rate_limiter)
        processor = UpdateProcessor(
            handlers, config.webhook_queue_size, config.worker_count
        )
        app.state.telegram = telegram
        app.state.gas = gas
        app.state.state_store = state_store
        app.state.processor = processor
        app.state.bot_ready = False
        await processor.start()
        logger.info("Starting %s version %s", config.app_name, APP_VERSION)

        try:
            bot = await telegram.get_me()
            logger.info("Telegram bot connected: @%s", bot.get("username"))
            if config.auto_set_webhook:
                if config.webhook_url:
                    await telegram.set_webhook(
                        config.webhook_url,
                        config.telegram_webhook_secret.get_secret_value(),
                    )
                    logger.info("Telegram webhook configured: %s", config.webhook_url)
                else:
                    logger.warning(
                        "Webhook not configured: expose a Northflank public port, "
                        "or set PUBLIC_BASE_URL/RENDER_EXTERNAL_HOSTNAME"
                    )
            app.state.bot_ready = True
        except TelegramApiError:
            logger.exception("Telegram startup configuration failed")

        if app.state.bot_ready and config.configure_bot_profile:
            try:
                await telegram.set_commands()
                await telegram.set_description(config.bot_brand_name)
            except TelegramApiError:
                # Profile cosmetics must never prevent the webhook from working.
                logger.exception("Telegram profile configuration failed")

        yield

        await processor.stop()
        await gas.close()
        await telegram.close()

    app = FastAPI(
        title=config.app_name,
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = config

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "service": config.app_name,
            "version": APP_VERSION,
            "status": "online",
        }

    @app.get("/health")
    async def health(request: Request) -> JSONResponse:
        processor: UpdateProcessor | None = getattr(
            request.app.state, "processor", None
        )
        store: MemoryStateStore | None = getattr(request.app.state, "state_store", None)
        platform = (
            "northflank"
            if config.nf_hosts
            else "render"
            if config.render_external_hostname
            else "custom"
        )
        payload: dict[str, Any] = {
            "status": "ok",
            "version": APP_VERSION,
            "botReady": bool(getattr(request.app.state, "bot_ready", False)),
            "platform": platform,
            "publicUrlDetected": bool(config.resolved_public_base_url),
            "storage": "memory",
            "queueSize": processor.queue.qsize() if processor else 0,
            "selectedModes": await store.count() if store else 0,
        }
        return JSONResponse(payload)

    @app.get("/telegram/webhook")
    async def telegram_webhook_info() -> dict[str, Any]:
        return {
            "status": "ready",
            "version": APP_VERSION,
            "message": (
                "Telegram delivers updates with POST; browser GET is diagnostic only."
            ),
        }

    @app.post("/telegram/webhook")
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        expected = config.telegram_webhook_secret.get_secret_value()
        if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
            x_telegram_bot_api_secret_token, expected
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook secret",
            )
        try:
            update = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON") from exc
        if not isinstance(update, dict):
            raise HTTPException(status_code=400, detail="Invalid Telegram update")
        processor: UpdateProcessor = request.app.state.processor
        try:
            accepted = processor.enqueue(update)
        except QueueFullError as exc:
            raise HTTPException(
                status_code=503, detail="Update queue is temporarily full"
            ) from exc
        return {"ok": True, "accepted": accepted}

    return app


app = create_app()
