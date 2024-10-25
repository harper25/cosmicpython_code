from __future__ import annotations
from typing import Optional
from dataclasses import asdict
from datetime import date

# from src.allocation.adapters import email, redis_eventpublisher
from src.allocation.adapters import notifications
from src.allocation.domain import commands, events, model
from src.allocation.domain.model import OrderLine
# from src.allocation.service_layer import unit_of_work


# if TYPE_CHECKING:
#     from . import unit_of_work


class InvalidSku(Exception):
    pass


def add_batch(
    cmd: commands.CreateBatch,
    uow: unit_of_work.AbstractUnitOfWork,
):
    with uow:
        product = uow.products.get(sku=cmd.sku)
        if product is None:
            product = model.Product(cmd.sku, batches=[])
            uow.products.add(product)
        product.batches.append(
            model.Batch(cmd.ref, cmd.sku, cmd.qty, cmd.eta)
        )
        uow.commit()


def allocate(
    cmd: commands.Allocate,
    uow: unit_of_work.AbstractUnitOfWork,
):
    line = OrderLine(cmd.orderid, cmd.sku, cmd.qty)
    with uow:
        product = uow.products.get(sku=line.sku)
        if product is None:
            raise InvalidSku(f"Invalid sku {line.sku}")
        print(f"Allocating {line=}")
        product.allocate(line)
        uow.commit()


def reallocate(
    event: events.Deallocated,
    uow: unit_of_work.AbstractUnitOfWork,
):
    print(f"Running reallocate for {event=}")
    allocate(commands.Allocate(**asdict(event)), uow=uow)
    # with uow:
    #     product = uow.products.get(sku=event.sku)
    #     product.events.append(commands.Allocate(**asdict(event)))
    #     uow.commit()


def change_batch_quantity(
    cmd: commands.ChangeBatchQuantity,
    uow: unit_of_work.AbstractUnitOfWork,
):
    with uow:
        product = uow.products.get_by_batchref(batchref=cmd.ref)
        product.change_batch_quantity(ref=cmd.ref, qty=cmd.qty)
        uow.commit()


def send_out_of_stock_notification(
    event: events.OutOfStock,
    notifications: notifications.AbstractNotifications,
):
    notifications.send(
        "stock@made.com",
        f"Out of stock for {event.sku}",
    )


def publish_allocated_event(
    event: events.Allocated,
    publish: Callable,
):
    publish("line_allocated", event)


def add_allocation_to_read_model(
    event: events.Allocated,
    uow: unit_of_work.SqlAlchemyUnitOfWork,
):
    with uow:
        uow.session.execute(
            """
            INSERT INTO allocations_view (orderid, sku, batchref)
            VALUES (:orderid, :sku, :batchref)
            """,
            dict(orderid=event.orderid, sku=event.sku, batchref=event.batchref),
        )
        uow.commit()


def remove_allocation_from_read_model(
    event: events.Deallocated,
    uow: unit_of_work.SqlAlchemyUnitOfWork,
):
    print(f"Running remove_allocation_from_read_model")
    with uow:
        uow.session.execute(
            """
            DELETE FROM allocations_view
            WHERE orderid = :orderid AND sku = :sku
            """,
            dict(orderid=event.orderid, sku=event.sku),
        )
        uow.commit()


EVENT_HANDLERS = {
    events.Allocated: [publish_allocated_event, add_allocation_to_read_model],
    events.Deallocated: [remove_allocation_from_read_model, reallocate],
    events.OutOfStock: [send_out_of_stock_notification],
}  # type: Dict[Type[events.Event], List[Callable]]

COMMAND_HANDLERS = {
    commands.Allocate: allocate,
    commands.CreateBatch: add_batch,
    commands.ChangeBatchQuantity: change_batch_quantity,
}  # type: Dict[Type[commands.Command], Callable]


# # DI with classes:
# class AllocateHandler:
#     def __init__(self, uow: unit_of_work.AbstractUnitOfWork):  #(2)
#         self.uow = uow

#     def __call__(self, cmd: commands.Allocate):  #(1)
#         line = OrderLine(cmd.orderid, cmd.sku, cmd.qty)
#         with self.uow:
#             # rest of handler method as before
#             ...

# # bootstrap script prepares actual UoW
# uow = unit_of_work.SqlAlchemyUnitOfWork()

# # then prepares a version of the allocate fn with dependencies already injected
# allocate = AllocateHandler(uow)

# ...
# # later at runtime, we can call the handler instance, and it will have
# # the UoW already injected
# allocate(cmd)
