import requests
from typing import (
    Union,
    Tuple,
    Optional,
    Mapping,
    Text,
    Callable,
    List,
    MutableMapping,
    Iterable,
    Any,
    IO,
)

_Data = Union[
    None,
    Text,
    bytes,
    Mapping[str, Any],
    Mapping[Text, Any],
    Iterable[Tuple[Text, Optional[Text]]],
    IO,
]


RequestsCookieJar = requests.cookies.RequestsCookieJar
Response = requests.models.Response
Request = requests.models.Request
PreparedRequest = requests.models.PreparedRequest
_Hook = Callable[[Response], Any]
_Hooks = MutableMapping[Text, List[_Hook]]
_HooksInput = MutableMapping[Text, Union[Iterable[_Hook], _Hook]]

_AuthType = Union[
    None,
    Tuple[str, str],
    requests.auth.AuthBase,
    Callable[[Request], Request],
]
