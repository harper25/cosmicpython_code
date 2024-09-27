import json
import pytest
from tenacity import Retrying, RetryError, stop_after_delay

from tests.e2e import api_client, redis_client
from tests.random_refs import random_batchref, random_orderid, random_sku


@pytest.mark.usefixtures("postgres_db")
@pytest.mark.usefixtures("restart_api")
@pytest.mark.usefixtures("restart_redis_pubsub")
def test_change_batch_quantity_leading_to_reallocation():
    # start with two batches and an order allocated to one of them  #(1)
    orderid, sku = random_orderid(), random_sku()
    earlier_batch, later_batch = random_batchref("old"), random_batchref("newer")
    api_client.post_to_add_batch(earlier_batch, sku, qty=10, eta="2011-01-01")  #(2)
    api_client.post_to_add_batch(later_batch, sku, qty=10, eta="2011-01-02")
    response = api_client.post_to_allocate(orderid, sku, 10)  #(2)
    assert response.ok
    response = api_client.get_allocation(orderid)
    assert response.json()[0]["batchref"] == earlier_batch

    subscription = redis_client.subscribe_to("line_allocated")  #(3)

    # change quantity on allocated batch so it's less than our order  #(1)
    redis_client.publish_message(  #(3)
        "change_batch_quantity",
        {"batchref": earlier_batch, "qty": 5},
    )

    # wait until we see a message saying the order has been reallocated  #(1)
    messages = []
    for attempt in Retrying(stop=stop_after_delay(3), reraise=True):  #(4)
        with attempt:
            message = subscription.get_message(timeout=1)
            print(f"{message=}")
            if message:
                messages.append(message)
                print(f"{messages=}")
            data = json.loads(messages[-1]["data"])
            # asserts within Retrying block will try to assert until until
            # `stop` condition is met or assert goes through
            assert data["orderid"] == orderid
            assert data["batchref"] == later_batch # reallocated to the later batch
