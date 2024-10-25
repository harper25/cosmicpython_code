from datetime import datetime
from flask import Flask, jsonify, request

import logging
import os
import sys

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
logging.basicConfig(level=LOGLEVEL)

logger = logging.getLogger(__name__)

logger.debug(f"PYTHONPATH={os.environ.get('PYTHONPATH')}")
logger.debug(f"sys.path={sys.path}")
logger.debug(f"{os.getcwd()=}")

from src.allocation import bootstrap, views
from src.allocation.domain import commands
# from src.allocation.service_layer import messagebus, unit_of_work # no longer required
from src.allocation.service_layer.handlers import InvalidSku


app = Flask(__name__)
bus = bootstrap.bootstrap()
# orm.start_mappers()


@app.route("/add_batch", methods=["POST"])
def add_batch():
    eta = request.json["eta"]
    if eta is not None:
        eta = datetime.fromisoformat(eta).date()
    cmd = commands.CreateBatch(
        request.json["ref"], request.json["sku"], request.json["qty"], eta
    )
    # uow = unit_of_work.SqlAlchemyUnitOfWork()
    # messagebus.handle(cmd, uow)
    bus.handle(cmd)  #(3)
    return "OK", 201


@app.route("/allocate", methods=["POST"])
def allocate_endpoint():
    try:
        cmd = commands.Allocate(
            request.json["orderid"], request.json["sku"], request.json["qty"]
        )
        # uow = unit_of_work.SqlAlchemyUnitOfWork()
        # results = messagebus.handle(cmd, uow)
        # batchref = results.pop(0)
        bus.handle(cmd)
    except InvalidSku as e:
        return {"message": str(e)}, 400

    return "OK", 202


@app.route("/allocations/<orderid>", methods=["GET"])
def allocations_view_endpoint(orderid):
    # uow = unit_of_work.SqlAlchemyUnitOfWork()
    result = views.allocations(orderid, bus.uow)
    if not result:
        return "not found", 404
    return jsonify(result), 200
