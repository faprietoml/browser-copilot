import logging
from typing import Union

import dotenv
import pytest
from httpx import AsyncClient, ASGITransport
from pydantic import TypeAdapter

from .agent import AgentFlow
from .api import app
from .domain import Session, MessageChunk
from .file_system_repos import SessionsRepository

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

dotenv.load_dotenv()

ModelAdapter = TypeAdapter(Union[MessageChunk, AgentFlow])


@pytest.mark.asyncio
async def test_answers():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        # Create session
        session = Session(locales=["en"], user="")
        await SessionsRepository().save_session(session)
        logger.info(f"Session created: {session.model_dump_json()}")

        # Send `POST` request.
        response = await async_client.post(
            "/sessions/{session_id}/questions".format(session_id=str(session.id)),
            json={"question": "Hello 0"},
        )

        assert "text/event-stream" in response.headers["content-type"]

        messages: list[str] = []
        for chunk in response.iter_bytes():
            lines = chunk.decode("utf-8").splitlines()
            for line in lines:
                if line.startswith("data:"):
                    messages.append(line[len("data:") :].strip())
                elif line.startswith("event:"):
                    # Handle event types if needed
                    pass

        for message in messages:
            model_obj: MessageChunk | AgentFlow = ModelAdapter.validate_json(message)

            assert isinstance(model_obj, MessageChunk) or isinstance(
                model_obj, AgentFlow
            )
            logger.info(
                f"{model_obj.__class__.__name__}: {model_obj.model_dump_json()}"
            )
