import logging
from datetime import datetime

import pytz
import requests
from ask_sdk_core.dispatch_components import (
    AbstractExceptionHandler,
    AbstractRequestHandler,
)
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import is_intent_name, is_request_type
from ask_sdk_model import Response
from typing import Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

API_BASE_URL = "https://bandeco-unicamp.up.railway.app/cardapio/"
TIMEZONE = pytz.timezone("America/Sao_Paulo")
LUNCH_CUTOFF_HOUR = 14


def get_today_date() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


def get_default_meal() -> str:
    hour = datetime.now(TIMEZONE).hour
    return "almoco" if hour < LUNCH_CUTOFF_HOUR else "jantar"


def fetch_menu(date: str) -> dict:
    # TODO: Add verification of date format to avoid errors
    try:
        response = requests.get(API_BASE_URL + date, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error("Erro ao buscar cardápio: %s", exc)
        return None


def resolve_slot_id(handler_input: HandlerInput, slot_name: str) -> Optional[str]:
    """Return the canonical slot ID (e.g. 'almoco', 'vegano') or None."""
    intent = handler_input.request_envelope.request.intent
    slot = intent.slots.get(slot_name)
    if not slot or not slot.value:
        return None
    resolutions = slot.resolutions
    if resolutions and resolutions.resolutions_per_authority:
        for authority in resolutions.resolutions_per_authority:
            if authority.values:
                return authority.values[0].value.id
    return None


def get_slot_value(handler_input: HandlerInput, slot_name: str) -> Optional[str]:
    """Return the raw slot value or None. Use for built-in types like AMAZON.DATE."""
    intent = handler_input.request_envelope.request.intent
    slot = intent.slots.get(slot_name)
    if not slot or not slot.value:
        return None
    return slot.value


def build_meal_speech(menu: dict, meal_key: str, diet_key: str, meal_label: str, diet_label: str, date_label: str) -> Optional[str]:
    # TODO: insert day of week to the speech
    # TODO: use past verbs when the date is in the past or if the meal is in the past
    if menu.get(meal_key, {}) is None:
        return f"Não há cardápio cadastrado para {meal_label} {date_label}."
    
    meal_data = menu.get(meal_key, {}).get(diet_key)
    if meal_data is None:
        return f"Não encontrei o cardápio {diet_label} para {meal_label} {date_label}."

    prato = meal_data.get("prato_principal", "").capitalize()
    guarnicao = meal_data.get("guarnicao", "").capitalize()
    salada = meal_data.get("salada", "").capitalize()
    sobremesa = meal_data.get("sobremesa", "").lower()
    suco = meal_data.get("suco", "").lower()

    parts = [f"O {meal_label} {diet_label} {date_label} é:"]
    parts.append(f"{prato}.")
    parts.append(f"{guarnicao} de guarnição.")
    parts.append(f"{salada}, suco de {suco} e {sobremesa} de sobremesa.")

    return "\n".join(parts)


MEAL_LABELS = {
    "almoco": "almoço",
    "jantar": "jantar",
}

DIET_LABELS = {
    "regular": "",
    "vegano": "vegano",
}


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = (
            "Olá! Eu sou o Bandéco Unicamp. "
            "Você pode me perguntar o que tem no almoço ou no jantar de hoje, "
            "incluindo a opção vegana. O que você quer saber?"
        )
        reprompt = "Pergunte, por exemplo: qual é o almoço de hoje?"
        return (
            handler_input.response_builder
            .speak(speech)
            .ask(reprompt)
            .response
        )


class CardapioIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("CardapioIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        meal_id = resolve_slot_id(handler_input, "meal") or get_default_meal()
        diet_id = resolve_slot_id(handler_input, "diet") or "regular"
        date = get_slot_value(handler_input, "date") or get_today_date()

        menu = fetch_menu(date)

        if menu is None:
            speech = (
                "Desculpe, não consegui acessar o cardápio agora. "
                "Tente novamente em alguns instantes."
            )
        else:
            meal_label = MEAL_LABELS.get(meal_id, meal_id)
            diet_label = DIET_LABELS.get(diet_id, diet_id)
            today = get_today_date()
            date_label = "de hoje" if date == today else f"do dia {date}"
            speech = build_meal_speech(menu, meal_id, diet_id, meal_label, diet_label, date_label)

        return (
            handler_input.response_builder
            .speak(speech)
            .set_should_end_session(True)
            .response
        )


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = (
            "Você pode me perguntar sobre o cardápio de hoje. "
            "Por exemplo: qual é o almoço? O que tem no jantar vegano? "
            "Ou simplesmente: o que tem no bandeco?"
        )
        return (
            handler_input.response_builder
            .speak(speech)
            .ask(speech)
            .response
        )


class CancelAndStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.CancelIntent")(handler_input) or is_intent_name("AMAZON.StopIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return (
            handler_input.response_builder
            .speak("Até logo! Bom apetite!")
            .set_should_end_session(True)
            .response
        )


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = (
            "Não entendi o que você perguntou. "
            "Tente perguntar: qual é o almoço de hoje? ou o que tem no jantar vegano?"
        )
        return (
            handler_input.response_builder
            .speak(speech)
            .ask(speech)
            .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        logger.error("Exceção não tratada: %s", exception, exc_info=True)
        speech = "Ocorreu um erro inesperado. Por favor, tente novamente."
        return (
            handler_input.response_builder
            .speak(speech)
            .set_should_end_session(True)
            .response
        )


sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(CardapioIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelAndStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()
