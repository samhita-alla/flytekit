import datetime as _datetime
import typing
from typing import Dict
from flytekit import typing as flyte_typing
from flytekit.common.exceptions import system as system_exceptions, user as user_exceptions
import abc

from flytekit.common.types import primitives as _primitives
from flytekit.models import types as _type_models, interface as _interface_models
from flytekit.models.core import types as _core_types

# This is now in three different places. This here, the one that the notebook task uses, and the main in that meshes
# with the engine loader. I think we should get rid of the loader (can add back when/if we ever have more than one).
# All three should be merged into the existing one.
# TODO: Change the values to reference the literal model type directly.
BASE_TYPES: Dict[type, _type_models.LiteralType] = {
    int: _primitives.Integer.to_flyte_literal_type(),
    float: _primitives.Float.to_flyte_literal_type(),
    bool: _primitives.Boolean,
    _datetime.datetime: _primitives.Datetime.to_flyte_literal_type(),
    _datetime.timedelta: _primitives.Timedelta.to_flyte_literal_type(),
    str: _primitives.String.to_flyte_literal_type(),
    # TODO: Not sure what to do about this yet
    dict: _primitives.Generic.to_flyte_literal_type(),
    None: _type_models.LiteralType(
        simple=_type_models.SimpleType.NONE,
    ),
    typing.TextIO: _type_models.LiteralType(
        blob=_core_types.BlobType(
            format=flyte_typing.FlyteFileFormats.TEXT_IO.value,
            dimensionality=_core_types.BlobType.BlobDimensionality.SINGLE
        )
    ),
    typing.BinaryIO: _type_models.LiteralType(
        blob=_core_types.BlobType(
            format=flyte_typing.FlyteFileFormats.BINARY_IO.value,
            dimensionality=_core_types.BlobType.BlobDimensionality.SINGLE
        )
    ),
    flyte_typing.FlyteFilePath: _type_models.LiteralType(
        blob=_core_types.BlobType(
            format=flyte_typing.FlyteFileFormats.BASE_FORMAT.value,
            dimensionality=_core_types.BlobType.BlobDimensionality.SINGLE
        )
    ),
    flyte_typing.FlyteCSVFilePath: _type_models.LiteralType(
        blob=_core_types.BlobType(
            format=flyte_typing.FlyteFileFormats.CSV.value,
            dimensionality=_core_types.BlobType.BlobDimensionality.SINGLE
        )
    ),
}

CONTAINER_TYPES = [typing.Dict, typing.List]

# These are not supported in the context of Flyte's type management, because there is no way to peek into what the
# inner type is. Also unsupported are typing's Tuples. Even though you can look inside them, Flyte's type system
# doesn't support these currently.
UNSUPPORTED_CONTAINERS = [tuple, list, dict, typing.Tuple, typing.NamedTuple]


def outputs(**kwargs) -> tuple:
    """
    Returns an outputs object that strongly binds the types of the outputs retruned by any executable unit (e.g. task,
    workflow).

    :param kwargs:
    :return:

    >>> @task
    >>> def my_task() -> outputs(a=int, b=str):
    >>>    pass
    """

    return typing.NamedTuple("Outputs", **kwargs)


# This only goes one way for now, is there any need to go the other way?
class BaseEngine(object):
    def native_type_to_literal_type(self, native_type: type) -> _type_models.LiteralType:
        if native_type in BASE_TYPES:
            return BASE_TYPES[native_type]

        # Handle container types like typing.List and Dict. However, since these are implemented as Generics, and
        # you can't just do runtime object comparison. i.e. if:
        #   t = typing.List[int]
        #   t in [typing.List]  # False
        #   isinstance(t, typing.List)  # False
        # so we have to look inside the type's hidden attributes
        if hasattr(native_type, '__origin__') and native_type.__origin__ == list:
            return self._type_unpack_list(native_type)

        if hasattr(native_type, '__origin__') and native_type.__origin__ == dict:
            return self._type_unpack_dict(native_type)

        raise user_exceptions.FlyteTypeException(f"Python type {native_type} is not supported")

    def _type_unpack_dict(self, t) -> _type_models.LiteralType:
        if t.__origin__ != dict:
            raise user_exceptions.FlyteTypeException(f"Attempting to analyze dict but non-dict "
                                                     f"type given {t.__origin__}")
        if t.__args__[0] != str:
            raise user_exceptions.FlyteTypeException(f"Key type for hash tables must be of type str, given: {t}")

        sub_type = self.native_type_to_literal_type(t.__args__[1])
        return _type_models.LiteralType(map_value_type=sub_type)

    def _type_unpack_list(self, t) -> _type_models.LiteralType:
        if t.__origin__ != list:
            raise user_exceptions.FlyteTypeException(f"Attempting to analyze list but non-list "
                                                     f"type given {t.__origin__}")

        sub_type = self.native_type_to_literal_type(t.__args__[0])
        return _type_models.LiteralType(collection_type=sub_type)

    def named_tuple_to_variable_map(self, t: typing.NamedTuple) -> _interface_models.VariableMap:
        variables = {}
        for var_name, var_type in t._field_types.item():
            literal_type = self.native_type_to_literal_type(var_type)
            variables[var_name] = _interface_models.Variable(type=literal_type)
        return _interface_models.VariableMap(variables=variables)