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
)

_Data = Optional[
    Union[
        Iterable[bytes],
        str,
        bytes,
        #        SupportsRead[Union[str, bytes]],
        List[Tuple[Any, Any]],
        Tuple[Tuple[Any, Any], ...],
        Mapping[Any, Any],
    ]
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
