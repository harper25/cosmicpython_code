import abc
from src.allocation.domain import model


class AbstractRepository(abc.ABC):
    def __init__(self):
        self.seen = set()  # type: Set[model.Product]  #(1)

    def add(self, product: model.Product):  #(2)
        self._add(product)
        self.seen.add(product)

    def get(self, sku) -> model.Product:  #(3)
        product = self._get(sku)
        if product:
            self.seen.add(product)
        return product

    @abc.abstractmethod
    def _add(self, product: model.Product):  #(2)
        raise NotImplementedError

    @abc.abstractmethod  #(3)
    def _get(self, sku) -> model.Product:
        raise NotImplementedError


class SqlAlchemyRepository(AbstractRepository):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def _add(self, product):  #(2)
        self.session.add(product)

    def _get(self, sku):  #(3)
        return self.session.query(model.Product).filter_by(sku=sku).first()

    def list(self):
        return self.session.query(model.Product).all()
