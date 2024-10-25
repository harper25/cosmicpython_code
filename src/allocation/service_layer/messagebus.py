import logging
from typing import List, Dict, Callable, Type, Union, TYPE_CHECKING

from src.allocation.domain import commands, events
from src.allocation.service_layer import unit_of_work

from tenacity import Retrying, RetryError, stop_after_attempt, wait_exponential


if TYPE_CHECKING:
    from . import unit_of_work

logger = logging.getLogger(__name__)

Message = Union[commands.Command, events.Event]


class MessageBus:  #(1)
    def __init__(
        self,
        uow: unit_of_work.AbstractUnitOfWork,
        event_handlers: Dict[Type[events.Event], List[Callable]],  #(2)
        command_handlers: Dict[Type[commands.Command], Callable],  #(2)
    ):
        self.uow = uow
        self.event_handlers = event_handlers
        self.command_handlers = command_handlers

    def handle(self, message: Message):  #(3)
        self.queue = [message]  #(4)
        while self.queue:
            message = self.queue.pop(0)
            if isinstance(message, events.Event):
                self.handle_event(message)
            elif isinstance(message, commands.Command):
                self.handle_command(message)
            else:
                raise Exception(f"{message} was not an Event or Command")

    def handle_event(self, event: events.Event):
        for handler in self.event_handlers[type(event)]:  #(1)
            try:
                logger.debug("handling event %s with handler %s", event, handler)
                handler(event)  #(2)
                new_events = self.uow.collect_new_events()
                if new_events:
                    self.queue.extend(new_events)
            except Exception:
                logger.exception("Exception handling event %s", event)
                continue

    def handle_command(self, command: commands.Command):
        logger.debug("handling command %s", command)
        try:
            handler = self.command_handlers[type(command)]  #(1)
            handler(command)  #(2)
            new_events = self.uow.collect_new_events()
            if new_events:
                self.queue.extend(new_events)
        except Exception:
            logger.exception("Exception handling command %s", command)
            raise


# def handle(
#     message: Message,
#     uow: unit_of_work.AbstractUnitOfWork,
# ):
#     results = []
#     queue = [message]
#     while queue:
#         message = queue.pop(0)
#         if isinstance(message, events.Event):
#             handle_event(message, queue, uow)
#         elif isinstance(message, commands.Command):
#             cmd_result = handle_command(message, queue, uow)
#             results.append(cmd_result)
#         else:
#             raise Exception(f"{message} was not an Event or Command")
#     return results # ugly hack, will be fixed later


# def handle_event(
#     event: events.Event,
#     queue: List[Message],
#     uow: unit_of_work.AbstractUnitOfWork,
# ):
#     for handler in EVENT_HANDLERS[type(event)]:  #(1)
#         try:
#             logger.debug("handling event %s with handler %s", event, handler)
#             handler(event, uow=uow)
#             queue.extend(uow.collect_new_events())
#         except Exception:
#             logger.exception("Exception handling event %s", event)
#             continue  #(2)


# def handle_event(
#     event: events.Event,
#     queue: List[Message],
#     uow: unit_of_work.AbstractUnitOfWork,
# ):
#     for handler in EVENT_HANDLERS[type(event)]:
#         try:
#             for attempt in Retrying(  #(2)
#                 stop=stop_after_attempt(3),
#                 wait=wait_exponential()
#             ):
#                 with attempt:
#                     logger.debug("handling event %s with handler %s", event, handler)
#                     handler(event, uow=uow)
#                     new_events = uow.collect_new_events()
#                     if new_events:
#                         queue.extend(new_events)
#         except RetryError as retry_failure:
#             logger.error(
#                 "Failed to handle event %s times, giving up!",
#                 retry_failure.last_attempt.attempt_number
#             )
#             continue


# def handle_command(
#     command: commands.Command,
#     queue: List[Message],
#     uow: unit_of_work.AbstractUnitOfWork,
# ):
#     logger.debug("handling command %s", command)
#     try:
#         handler = COMMAND_HANDLERS[type(command)]  #(1)
#         result = handler(command, uow=uow)
#         new_events = uow.collect_new_events()
#         if new_events:
#             queue.extend(new_events)
#         return result  #(3)
#     except Exception:
#         logger.exception("Exception handling command %s", command)
#         raise  #(2)
