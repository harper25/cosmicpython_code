from datetime import date
from unittest import mock
import pytest

from src.allocation.adapters import repository
from src.allocation.domain import commands, events
from src.allocation.service_layer import handlers, messagebus, unit_of_work


class FakeRepository(repository.AbstractRepository):
    def __init__(self, products):
        super().__init__()
        self._products = set(products)

    def _add(self, product):
        self._products.add(product)

    def _get(self, sku):
        return next((p for p in self._products if p.sku == sku), None)

    def list(self):
        return list(self._products)

    def _get_by_batchref(self, batchref):
        return next(
            (p for p in self._products for b in p.batches if b.reference == batchref),
            None,
        )


# class TrackingRepository:
#     seen: Set[model.Product]

#     def __init__(self, repo: AbstractRepository):
#         self.seen = set()  # type: Set[model.Product]
#         self._repo = repo

#     def add(self, product: model.Product):  #(1)
#         self._repo.add(product)  #(1)
#         self.seen.add(product)

#     def get(self, sku) -> model.Product:
#         product = self._repo.get(sku)
#         if product:
#             self.seen.add(product)
#         return product


class FakeUnitOfWork(unit_of_work.AbstractUnitOfWork):
    def __init__(self):
        self.products = FakeRepository([])
        self.committed = False

    def _commit(self):
        self.committed = True

    def rollback(self):
        pass


class TestAddBatch:
    def test_for_new_product(self):
        uow = FakeUnitOfWork()
        messagebus.handle(
            commands.CreateBatch("b1", "CRUNCHY-ARMCHAIR", 100, None), uow
        )
        assert uow.products.get("CRUNCHY-ARMCHAIR") is not None
        assert uow.committed

    def test_for_existing_product(self):
        uow = FakeUnitOfWork()
        messagebus.handle(commands.CreateBatch("b1", "GARISH-RUG", 100, None), uow)
        messagebus.handle(commands.CreateBatch("b2", "GARISH-RUG", 99, None), uow)
        assert "b2" in [b.reference for b in uow.products.get("GARISH-RUG").batches]


class TestAllocate:
    def test_allocates(self):
        uow = FakeUnitOfWork()
        messagebus.handle(
            commands.CreateBatch("batch1", "COMPLICATED-LAMP", 100, None), uow
        )
        messagebus.handle(
            commands.Allocate("o1", "COMPLICATED-LAMP", 10), uow
        )
        # assert results.pop(0) == "batch1" # no more returns!
        [batch] = uow.products.get("COMPLICATED-LAMP").batches
        assert batch.available_quantity == 90

    def test_errors_for_invalid_sku(self):
        # uow = FakeUnitOfWork()
        # handlers.add_batch(commands.CreateBatch("b1", "AREALSKU", 100, None), uow)

        # with pytest.raises(handlers.InvalidSku, match="Invalid sku NONEXISTENTSKU"):
        #     handlers.allocate(commands.Allocate("o1", "NONEXISTENTSKU", 10), uow)
        uow = FakeUnitOfWork()
        messagebus.handle(commands.CreateBatch("b1", "AREALSKU", 100, None), uow)

        with pytest.raises(handlers.InvalidSku, match="Invalid sku NONEXISTENTSKU"):
            messagebus.handle(commands.Allocate("o1", "NONEXISTENTSKU", 10), uow)

    def test_commits(self):
        uow = FakeUnitOfWork()
        messagebus.handle(commands.CreateBatch("b1", "OMINOUS-MIRROR", 100, None), uow)
        messagebus.handle(commands.Allocate("o1", "OMINOUS-MIRROR", 10), uow)
        assert uow.committed

    def test_sends_email_on_out_of_stock_error(self):
        uow = FakeUnitOfWork()
        messagebus.handle(commands.CreateBatch("b1", "POPULAR-CURTAINS", 9, None), uow)

        with mock.patch("src.allocation.adapters.email.send") as mock_send_mail:
            messagebus.handle(commands.Allocate("o1", "POPULAR-CURTAINS", 10), uow)
            assert mock_send_mail.call_args == mock.call(
                "stock@made.com", f"Out of stock for POPULAR-CURTAINS"
            )


# Unit test event handlers in isolation with a FakeMessageBus - nice!
# Needed for test: TestChangeBatchQuantity::test_reallocates_if_necessary_isolated
class FakeUnitOfWorkWithFakeMessageBus(FakeUnitOfWork):
    def __init__(self):
        super().__init__()
        self.events_published = []  # type: List[events.Event] - attribute added only for testing!

    def collect_new_events(self):
        for product in self.products.seen:
            while product.events:
                # a change in handle() function is required, not to extend queue with None events
                self.events_published.append(product.events.pop(0))


class TestChangeBatchQuantity:
    def test_changes_available_quantity(self):
        uow = FakeUnitOfWork()
        messagebus.handle(
            commands.CreateBatch("batch1", "ADORABLE-SETTEE", 100, None), uow
        )
        [batch] = uow.products.get(sku="ADORABLE-SETTEE").batches
        assert batch.available_quantity == 100  #(1)

        messagebus.handle(commands.ChangeBatchQuantity("batch1", 50), uow)

        assert batch.available_quantity == 50  #(1)

    def test_reallocates_if_necessary(self):
        uow = FakeUnitOfWork()
        history = [
            commands.CreateBatch("batch1", "INDIFFERENT-TABLE", 50, None),
            commands.CreateBatch("batch2", "INDIFFERENT-TABLE", 50, date.today()),
            commands.Allocate("order1", "INDIFFERENT-TABLE", 20),
            commands.Allocate("order2", "INDIFFERENT-TABLE", 20),
        ]
        for msg in history:
            messagebus.handle(msg, uow)
        [batch1, batch2] = uow.products.get(sku="INDIFFERENT-TABLE").batches
        assert batch1.available_quantity == 10
        assert batch2.available_quantity == 50

        messagebus.handle(commands.ChangeBatchQuantity("batch1", 25), uow)

        # order1 or order2 will be deallocated, so we'll have 25 - 20
        assert batch1.available_quantity == 5  #(2)
        # and 20 will be reallocated to the next batch
        assert batch2.available_quantity == 30  #(2)

    # ADDITOINAL TEST, testing the handler in isolation (not required by the book)
    # We do not need to test the whole system, we can test the handlers in isolation.
    # Instead of collecting and handling events, we just record them in a list.
    # BatchQuantityChanged event optionally triggers AllocationRequired event.
    # Command:
    # pytest -vvv tests/unit/test_handlers.py::TestChangeBatchQuantity::test_reallocates_if_necessary_isolated
    def test_reallocates_if_necessary_isolated(self):
        uow = FakeUnitOfWorkWithFakeMessageBus()

        # test setup as before
        history = [
            commands.CreateBatch("batch1", "INDIFFERENT-TABLE", 50, None),
            commands.CreateBatch("batch2", "INDIFFERENT-TABLE", 50, date.today()),
            commands.Allocate("order1", "INDIFFERENT-TABLE", 20),
            commands.Allocate("order2", "INDIFFERENT-TABLE", 20),
        ]
        for msg in history:
            messagebus.handle(msg, uow)
        [batch1, batch2] = uow.products.get(sku="INDIFFERENT-TABLE").batches
        assert batch1.available_quantity == 10
        assert batch2.available_quantity == 50

        messagebus.handle(commands.ChangeBatchQuantity("batch1", 25), uow)

        # assert on new events emitted rather than downstream side-effects
        [allocate_order1, allocate_order2, reallocate] = uow.events_published
        assert isinstance(reallocate, commands.Allocate)
        assert reallocate.orderid in {"order1", "order2"}
        assert reallocate.sku == "INDIFFERENT-TABLE"

        assert batch1.available_quantity == 5   # deallocated successfully
        assert batch2.available_quantity == 50  # reallocation is not done, we are testing in isolation
