import json
import logging
import redis

import os
import sys

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
logging.basicConfig(level=LOGLEVEL)

logger = logging.getLogger(__name__)

logger.debug(f"PYTHONPATH={os.environ.get('PYTHONPATH')}")
logger.debug(f"sys.path={sys.path}")
logger.debug(f"{os.getcwd()=}")

from src.allocation import bootstrap, config
from src.allocation.domain import commands
# from src.allocation.adapters import orm
# from src.allocation.service_layer import messagebus, unit_of_work

r = redis.Redis(**config.get_redis_host_and_port())


def main():
    logger.info("Redis pubsub starting")
    bus = bootstrap.bootstrap()
    # orm.start_mappers()
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe("change_batch_quantity")  #(1)

    for m in pubsub.listen():
        handle_change_batch_quantity(m, bus)


def handle_change_batch_quantity(m, bus):
    logging.debug("handling %s", m)
    data = json.loads(m["data"])  #(2)
    cmd = commands.ChangeBatchQuantity(ref=data["batchref"], qty=data["qty"])  #(2)
    # messagebus.handle(cmd, uow=unit_of_work.SqlAlchemyUnitOfWork())
    bus.handle(cmd)


if __name__ == "__main__":
    main()
