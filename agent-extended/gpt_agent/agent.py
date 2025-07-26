import asyncio
import datetime
import enum
import logging
import os

from typing import List, AsyncIterator, Optional
from pydantic import BaseModel
from langchain.agents import Tool, OpenAIFunctionsAgent, AgentExecutor
from langchain.agents.mrkl.base import ZeroShotAgent
from langchain.callbacks import AsyncIteratorCallbackHandler
from langchain.memory import ConversationBufferMemory, FileChatMessageHistory
from langchain.schema.runnable import RunnableConfig
from langchain.tools import tool
from langchain_community.chat_models import AzureChatOpenAI, ChatOpenAI
from openai import OpenAI, AzureOpenAI

from gpt_agent.domain import Session, MessageChunk
from gpt_agent.file_system_repos import get_session_path, SessionsRepository

logging.getLogger("openai").level = logging.DEBUG


# just a sample tool to showcase how you can create your own set of tools
@tool
def clock() -> str:
    """gets the current time"""
    return str(datetime.datetime.now())


class AgentAction(enum.Enum):
    MESSAGE = "message"
    CLICK = "click"
    FILL = "fill"
    GOTO = "goto"


class AgentStep(BaseModel):
    action: AgentAction
    selector: Optional[str] = None
    value: Optional[str] = None


class AgentFlow(BaseModel):
    steps: List[AgentStep]

    @staticmethod
    def message(text: str) -> "AgentFlow":
        return AgentFlow(steps=[AgentStep(action=AgentAction.MESSAGE, value=text)])


# a sample tool to showcase how you can automate navigation in the browser
@tool(return_direct=True)
def contact_abstracta(full_name: str) -> str:
    """navigates to abstracta.us and fills the contact form with the given full name"""
    return AgentFlow(
        steps=[
            AgentStep(action=AgentAction.GOTO, value="https://abstracta.us"),
            AgentStep(
                action=AgentAction.CLICK, selector='xpath://a[@href="./contact-us"]'
            ),
            AgentStep(action=AgentAction.FILL, selector="#fullname", value=full_name),
            AgentStep(
                action=AgentAction.MESSAGE,
                value="I have filled the contact form with your name.",
            ),
        ]
    ).model_dump_json()


class Agent:
    def __init__(self, session: Session):
        self._session = session
        message_history = FileChatMessageHistory(
            get_session_path(session.id) + "/chat_history.json"
        )
        self._memory = ConversationBufferMemory(
            memory_key="chat_history",
            chat_memory=message_history,
            return_messages=True,
            output_key="output",
        )
        self._agent = self._build_agent(self._memory, [contact_abstracta])

    def _build_agent(
        self, memory: ConversationBufferMemory, tools: List[Tool]
    ) -> AgentExecutor:
        llm = self._build_llm()

        # Zero-shot significa que el agente no tiene memoria ni entrenamiento en las tareas,
        # sino que basa sus decisiones únicamente en el prompt y las descripciones de las herramientas.
        # En cada paso el agente sigue el patrón Thought → Action → Action Input → Observation, repitiendo hasta generar la respuesta final.
        prompt = ZeroShotAgent.create_prompt(
            tools=tools,
            prefix=os.getenv("SYSTEM_PROMPT"),
        )

        agent = OpenAIFunctionsAgent(llm=llm, tools=tools, prompt=prompt)

        return AgentExecutor(
            agent=agent,
            tools=tools,
            memory=memory,
            # verbose=True,
            # return_intermediate_steps=True,
            max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "3")),
        )

    def _build_llm(self):
        temperature = float(os.getenv("TEMPERATURE"))
        base_url = os.getenv("OPENAI_API_BASE")
        if self._is_azure(base_url):
            return AzureChatOpenAI(
                deployment_name=os.getenv("AZURE_DEPLOYMENT_NAME"),
                temperature=temperature,
                verbose=True,
                streaming=True,
                callbacks=[],
            )  # ,callbacks=[RazonamientoCallback()]
        else:
            return ChatOpenAI(
                model_name=os.getenv("MODEL_NAME"),
                temperature=temperature,
                verbose=True,
                streaming=True,
            )

    @staticmethod
    def _is_azure(base_url: str) -> bool:
        return base_url and ".openai.azure.com" in base_url

    def start_session(self):
        self._memory.chat_memory.add_user_message(
            "this is my locale: " + self._session.locales[0]
        )

    def transcript(self, audio_file_path: str) -> str:
        base_url = os.getenv("OPENAI_WHISPER_API_BASE", os.getenv("OPENAI_API_BASE"))
        api_key = os.getenv("OPENAI_WHISPER_API_KEY", os.getenv("OPENAI_API_KEY"))
        api_version = os.getenv(
            "OPENAI_WHISPER_API_VERSION", os.getenv("OPENAI_API_VERSION")
        )
        deployment_name = os.getenv(
            "AZURE_WHISPER_DEPLOYMENT_NAME", os.getenv("AZURE_DEPLOYMENT_NAME")
        )
        client = (
            AzureOpenAI(
                azure_endpoint=base_url,
                api_version=api_version,
                api_key=api_key,
                azure_deployment=deployment_name,
            )
            if self._is_azure(base_url)
            else OpenAI(base_url=base_url, api_key=api_key)
        )
        locale = self._session.locales[0]
        lang_separator_pos = locale.find("-")
        language = locale[0:lang_separator_pos] if lang_separator_pos >= 0 else locale
        ret = client.audio.transcriptions.create(
            model="whisper-1", file=open(audio_file_path, "rb"), language=language
        )
        return ret.text

    async def ask(self, question: str) -> AsyncIterator[AgentFlow | str | MessageChunk]:
        # Convertir el UUID de la sesión a str.
        session_id = str(self._session.id)

        try:
            # Crear async callback para capturar los tokens generados por la pregunta.
            invoke_callback = AsyncIteratorCallbackHandler()

            # Crear rutina (langchain) para preguntar al agente.
            # TODO: Revisar .stream
            invoke_coroutine = self._agent.ainvoke(
                input=question,
                config=RunnableConfig(callbacks=[invoke_callback]),
            )

            # Crear la tarea asyncio para ejecutar la rutina.
            invoke_task = asyncio.create_task(invoke_coroutine)

            # Crear el async iterator para capturar el resultado de la tarea.
            invoke_async_iterator = invoke_callback.aiter()

            try:
                # Iterar por los resultados de la tarea, cuando se ejecute.
                async for token in invoke_async_iterator:
                    # Comprobar que el usuario no ha cancelado la sesión.
                    if not SessionsRepository.is_session_cancelled(session_id):
                        # Si no se ha cancelado se devuelve el token actual.

                        # Devolver el fragmento del mensaje
                        yield MessageChunk(
                            type="token", value=token
                        )  # "value": re.sub(r'\n+', '\n', token)
                    else:
                        # Si se canceló, se interrumpe el iterador, se cancela la tarea y se interrumpe el loop.

                        # Eliminar el identificador de la sesión actual de la lista de sesiones en cancelación.
                        SessionsRepository.unregister_cancelled_session(session_id)

                        # Cerrar el iterador para no obtener más elementos de la tarea.
                        await invoke_async_iterator.aclose()

                        # Detener la tarea en ejecución.
                        invoke_task.cancel()

                        break
            finally:
                try:
                    # Iniciar la tarea
                    invoke_result = await invoke_task

                    # Extraer la respuesta final del agente.
                    # TODO: buscar otro agente MRKL que devuelva razonamiento con la respuesta separada del razonamiento.
                    output = (
                        invoke_result.get("output", "Final Answer: No response")
                        .split("Final Answer:")[-1]
                        .strip()
                    )

                    yield AgentFlow(
                        steps=[AgentStep(action=AgentAction.MESSAGE, value=output)]
                    )
                except asyncio.CancelledError:
                    yield MessageChunk(type="event", value="cancellation")
                except Exception as exc:
                    logging.exception(exc)

                    SessionsRepository.unregister_cancelled_session(session_id)

                    yield AgentFlow(
                        steps=[
                            AgentStep(action=AgentAction.MESSAGE, value="No response")
                        ]
                    )

        except Exception as exc:
            # logging.exception("Error parsing agent response", exc)

            yield MessageChunk(type="error", value=str(exc))
