import json
import os
import uuid
import base64
import aiofiles
import aiofiles.os
import datetime

from gpt_agent.domain import Session, Question, TranscriptionQuestion


def get_session_path(session_id: uuid.UUID) -> str:
    return os.path.join("sessions", str(session_id))


async def _write_session_file(file_name: str, body: str, session: Session):
    file_path = os.path.join(get_session_path(session.id), file_name)
    async with aiofiles.open(file_path, "w") as outfile:
        await outfile.write(body)


async def _write_audio_file(file_name: str, body: str, session: Session):
    session_id_path = get_session_path(session.id)
    session_id_audio_path = os.path.join(session_id_path, "audio")

    if os.path.exists(session_id_path):
        os.makedirs(session_id_audio_path, exist_ok=True)

    audio_file_path = os.path.join(session_id_audio_path, file_name)

    async with aiofiles.open(audio_file_path, "wb") as outfile:
        await outfile.write(base64.b64decode(body))
    return audio_file_path


class SessionsRepository:
    # Ids de las sessiones en proceso de cancelación.
    # En memoria, porque el iterador del callback del agente estará consultando si la sessión canceló la operación.
    cancelled_sessions = []

    @staticmethod
    async def save_session(session: Session) -> None:
        session_path = get_session_path(session.id)
        await aiofiles.os.makedirs(session_path, exist_ok=True)
        await _write_session_file("session.json", session.model_dump_json(), session)

    @staticmethod
    async def find_session(session_id: str) -> Session | None:
        session_path = get_session_path(uuid.UUID(session_id))
        if not await aiofiles.os.path.exists(session_path):
            return None
        async with aiofiles.open(os.path.join(session_path, "session.json")) as f:
            session_dict = json.loads(await f.read())
            return Session(**session_dict)

    @staticmethod
    def register_cancelled_session(session_id: str) -> None:
        if session_id not in SessionsRepository.cancelled_sessions:
            SessionsRepository.cancelled_sessions.append(session_id)

    @staticmethod
    def unregister_cancelled_session(session_id: str) -> None:
        if session_id in SessionsRepository.cancelled_sessions:
            SessionsRepository.cancelled_sessions.remove(session_id)

    @staticmethod
    def is_session_cancelled(session_id: str) -> bool:
        return session_id in SessionsRepository.cancelled_sessions


class QuestionsRepository:

    @staticmethod
    async def save_question(question: Question) -> None:
        await _write_session_file(
            f"question-{question.id}.json", question.model_dump_json(), question.session
        )


class TranscriptionsRepository:

    @staticmethod
    async def save_audio(question: TranscriptionQuestion) -> str:
        now = datetime.datetime.now()
        formatted_date = now.strftime("%Y-%m-%d_%H-%M-%S")
        file_path = await _write_audio_file(
            f"{formatted_date}.webm", question.base64, question.session
        )
        return file_path
