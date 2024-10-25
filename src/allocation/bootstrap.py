import inspect
from typing import Callable

from src.allocation.adapters import orm, redis_eventpublisher
from src.allocation.adapters.notifications import (
    AbstractNotifications,
    EmailNotifications,
)
from src.allocation.service_layer import handlers, messagebus, unit_of_work


def bootstrap(
    start_orm: bool = True,  #(1)
    uow: unit_of_work.AbstractUnitOfWork = unit_of_work.SqlAlchemyUnitOfWork(),  #(2)
    notifications: AbstractNotifications = None,
    publish: Callable = redis_eventpublisher.publish,
) -> messagebus.MessageBus:

    if notifications is None:
        notifications = EmailNotifications()

    if start_orm:
        orm.start_mappers()  #(1)

    dependencies = {"uow": uow, "notifications": notifications, "publish": publish}
    injected_event_handlers = {  #(3)
        event_type: [
            inject_dependencies(handler, dependencies)
            for handler in event_handlers
        ]
        for event_type, event_handlers in handlers.EVENT_HANDLERS.items()
    }
    injected_command_handlers = {  #(3)
        command_type: inject_dependencies(handler, dependencies)
        for command_type, handler in handlers.COMMAND_HANDLERS.items()
    }

    return messagebus.MessageBus(  #(4)
        uow=uow,
        event_handlers=injected_event_handlers,
        command_handlers=injected_command_handlers,
    )


def inject_dependencies(handler, dependencies):
    params = inspect.signature(handler).parameters  #(1)
    deps = {
        name: dependency
        for name, dependency in dependencies.items()  #(2)
        if name in params
    }
    return lambda message: handler(message, **deps)  #(3)


    # # Manually creating partial functions inline:
    # injected_event_handlers = {
    #     events.Allocated: [
    #         lambda e: handlers.publish_allocated_event(e, publish),
    #         lambda e: handlers.add_allocation_to_read_model(e, uow),
    #     ],
    #     events.Deallocated: [
    #         lambda e: handlers.remove_allocation_from_read_model(e, uow),
    #         lambda e: handlers.reallocate(e, uow),
    #     ],
    #     events.OutOfStock: [
    #         lambda e: handlers.send_out_of_stock_notification(e, send_mail)
    #     ],
    # }
    # injected_command_handlers = {
    #     commands.Allocate: lambda c: handlers.allocate(c, uow),
    #     commands.CreateBatch: lambda c: handlers.add_batch(c, uow),
    #     commands.ChangeBatchQuantity: \
    #         lambda c: handlers.change_batch_quantity(c, uow),
    # }
