from dataclasses import dataclass


class Event:  #(1)
    pass


@dataclass
class OutOfStock(Event):  #(2)
    sku: str