from typing import List, Dict, Callable, Type, TYPE_CHECKING
from src.allocation.domain import events
from src.allocation.service_layer import unit_of_work, handlers


if TYPE_CHECKING:
    from . import unit_of_work


def handle(
    event: events.Event,
    uow: unit_of_work.AbstractUnitOfWork,  #(1)
):
    results = []
    queue = [event]  #(2)
    while queue:
        event = queue.pop(0)  #(3)
        for handler in HANDLERS[type(event)]:  #(3)
            results.append(handler(event, uow=uow))
            queue.extend(uow.collect_new_events())  #(5)
    return results # ugly hack, will be fixed later


HANDLERS = {
    events.BatchCreated: [handlers.add_batch],
    events.BatchQuantityChanged: [handlers.change_batch_quantity],
    events.AllocationRequired: [handlers.allocate],
    events.OutOfStock: [handlers.send_out_of_stock_notification],
}  # type: Dict[Type[events.Event], List[Callable]]
