from typing import TypedDict, Literal

RequestType = Literal["buy", "sell", "price", "maintain"]


class OrchestratorState(TypedDict):
    request: str
    request_type: RequestType
    response: str
