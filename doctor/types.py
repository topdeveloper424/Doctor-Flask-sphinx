"""
Copyright © 2017, Encode OSS Ltd. All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this
list of conditions and the following disclaimer.

Redistributions in binary form must reproduce the above copyright notice, this
list of conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.

Neither the name of the copyright holder nor the names of its contributors may
be used to endorse or promote products derived from this software without
specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

This file is a modified version of the typingsystem.py module in apistar.
https://github.com/encode/apistar/blob/973c6485d8297c1bcef35a42221ac5107dce25d5/apistar/typesystem.py
"""
import math
import re
import typing
from datetime import datetime
from typing import Any

import isodate
import rfc3987

from doctor.errors import SchemaError, SchemaValidationError, TypeSystemError
from doctor.parsers import parse_value


StrOrList = typing.Union[str, typing.List[str]]


class classproperty(object):
    """A decorator that allows a class to contain a class property.

    This is a function that can be executed on a non-instance but accessed
    via a property.

    >>> class Foo(object):
    ...   a = 1
    ...   @classproperty
    ...   def b(cls):
    ...     return cls.a + 1
    ...
    >>> Foo.b
    2
    """

    def __init__(self, fget):
        self.fget = fget

    def __get__(self, owner_self, owner_cls):
        return self.fget(owner_cls)


class MissingDescriptionError(ValueError):
    """An exception raised when a type is missing a description."""
    pass


class SuperType(object):
    """A super type all custom types must extend from.

    This super type requires all subclasses define a description attribute
    that describes what the type represents.  A `ValueError` will be raised
    if the subclass does not define a `description` attribute.
    """
    #: The description of what the type represents.
    description = None  # type: str

    #: An example value for the type.
    example: Any = None

    #: Indicates if the value of this type is allowed to be None.
    nullable = False  # type: bool

    #: An optional name of where to find the request parameter if it does not
    #: match the variable name in your logic function.
    param_name = None  # type: str

    #: An optional callable to parse a request paramter before it gets validated
    #: by a type.  It should accept a single value paramter and return the
    #: parsed value.
    parser = None  # type: typing.Callable

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.description is None:
            cls = self.__class__
            raise MissingDescriptionError(
                '{} did not define a description attribute'.format(cls))

    @classmethod
    def validate(cls, value: typing.Any):
        """Additional validation for a type.

        All types will have a validate method where custom validation logic
        can be placed.  The implementor should return nothing if the value is
        valid, otherwise a `TypeSystemError` should be raised.

        :param value: The value to be validated.
        """
        pass


class UnionType(SuperType):
    """A type that can be one of any of the defined `types`.

    The first type that does not raise a :class:`~doctor.errors.TypeSystemError`
    will be used as the type for the variable.
    """
    #: A list of allowed types.
    types = []

    _native_type = None

    def __new__(cls, *args, **kwargs):
        if not cls.types:
            raise TypeSystemError(
                'Sub-class must define a `types` list attribute containing at '
                'least 1 type.', cls=cls)

        valid = False
        value = None
        errors = {}
        for obj_class in cls.types:
            try:
                value = obj_class(*args, **kwargs)
                valid = True
                # Dynamically change the native_type based on that of the value.
                cls._native_type = obj_class.native_type
                break
            except TypeSystemError as e:
                errors[obj_class.__name__] = str(e)
                continue

        if not valid:
            klasses = [klass.__name__ for klass in cls.types]
            raise TypeSystemError('Value is not one of {}. {}'.format(
                klasses, errors))

        cls.validate(value)
        return value

    @classmethod
    def get_example(cls):
        """Returns an example value for the UnionType."""
        return cls.types[0].get_example()

    @classproperty
    def native_type(cls):
        """Returns the native type.

        Since UnionType can have multiple types, simply return the native type
        of the first type defined in the types attribute.

        If _native_type is set based on initializing a value with the class,
        then we return the dynamically modified type that matches that of the
        value used during instantiation.  e.g.

        >>> from doctor.types import UnionType, string, boolean
        >>> class BoolOrStr(UnionType):
        ...   description = 'bool or str'
        ...   types = [boolean('a bool'), string('a string')]
        ...
        >>> BoolOrStr.native_type
        <class 'bool'>
        >>> BoolOrStr('str')
        'str'
        >>> BoolOrStr.native_type
        <class 'str'>
        >>> BoolOrStr(False)
        False
        >>> BoolOrStr.native_type
        <class 'bool'>
        """
        if cls._native_type is not None:
            return cls._native_type
        return cls.types[0].native_type


class String(SuperType, str):
    """Represents a `str` type."""
    native_type = str
    errors = {
        'blank': 'Must not be blank.',
        'max_length': 'Must have no more than {max_length} characters.',
        'min_length': 'Must have at least {min_length} characters.',
        'pattern': 'Must match the pattern /{pattern}/.',
    }
    #: Will check format of the string for `date`, `date-time`, `email`,
    #: `time` and `uri`.
    format = None
    #: The maximum length of the string.
    max_length = None  # type: int
    #: The minimum length of the string.
    min_length = None  # type: int
    #: A regex pattern that the string should match.
    pattern = None  # type: str
    #: Whether to trim whitespace on a string.  Defaults to `True`.
    trim_whitespace = True

    def __new__(cls, *args, **kwargs):
        if cls.nullable and args[0] is None:
            return None

        value = super().__new__(cls, *args, **kwargs)

        if cls.trim_whitespace:
            value = value.strip()

        if cls.min_length is not None:
            if len(value) < cls.min_length:
                if cls.min_length == 1:
                    raise TypeSystemError(cls=cls, code='blank')
                else:
                    raise TypeSystemError(cls=cls, code='min_length')

        if cls.max_length is not None:
            if len(value) > cls.max_length:
                raise TypeSystemError(cls=cls, code='max_length')

        if cls.pattern is not None:
            if not re.search(cls.pattern, value):
                raise TypeSystemError(cls=cls, code='pattern')

        # Validate format, if specified
        if cls.format == 'date':
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError as e:
                raise TypeSystemError(str(e), cls=cls)
        elif cls.format == 'date-time':
            try:
                value = isodate.parse_datetime(value)
            except (ValueError, isodate.ISO8601Error) as e:
                raise TypeSystemError(str(e), cls=cls)
        elif cls.format == 'email':
            if '@' not in value:
                raise TypeSystemError('Not a valid email address.', cls=cls)
        elif cls.format == 'time':
            try:
                value = datetime.strptime(value, "%H:%M:%S")
            except ValueError as e:
                raise TypeSystemError(str(e), cls=cls)
        elif cls.format == 'uri':
            try:
                rfc3987.parse(value, rule='URI')
            except ValueError as e:
                raise TypeSystemError(str(e), cls=cls)

        # Coerce value to the native str type.  We only do this if the value
        # is an instance of the class.  It could be a datetime instance or
        # a str already if `trim_whitespace` is True.
        if isinstance(value, cls):
            value = cls.native_type(value)

        cls.validate(value)
        return value

    @classmethod
    def get_example(cls) -> str:
        """Returns an example value for the String type."""
        if cls.example is not None:
            return cls.example
        return 'string'


class _NumericType(SuperType):
    """
    Base class for both `Number` and `Integer`.
    """
    native_type = None  # type: type
    errors = {
        'type': 'Must be a valid number.',
        'finite': 'Must be a finite number.',
        'minimum': 'Must be greater than or equal to {minimum}.',
        'exclusive_minimum': 'Must be greater than {minimum}.',
        'maximum': 'Must be less than or equal to {maximum}.',
        'exclusive_maximum': 'Must be less than {maximum}.',
        'multiple_of': 'Must be a multiple of {multiple_of}.',
    }
    #: The minimum value allowed.
    minimum = None  # type: typing.Union[float, int]
    #: The maximum value allowed.
    maximum = None  # type: typing.Union[float, int]
    #: The minimum value should be treated as exclusive or not.
    exclusive_minimum = False
    #: The maximum value should be treated as exclusive or not.
    exclusive_maximum = False
    #: The value is required to be a multiple of this value.
    multiple_of = None  # type: typing.Union[float, int]

    def __new__(cls, *args, **kwargs):
        if cls.nullable and args[0] is None:
            return None

        try:
            value = cls.native_type.__new__(cls, *args, **kwargs)
        except (TypeError, ValueError):
            raise TypeSystemError(cls=cls, code='type') from None

        if not math.isfinite(value):
            raise TypeSystemError(cls=cls, code='finite')

        if cls.minimum is not None:
            if cls.exclusive_minimum:
                if value <= cls.minimum:
                    raise TypeSystemError(cls=cls, code='exclusive_minimum')
            else:
                if value < cls.minimum:
                    raise TypeSystemError(cls=cls, code='minimum')

        if cls.maximum is not None:
            if cls.exclusive_maximum:
                if value >= cls.maximum:
                    raise TypeSystemError(cls=cls, code='exclusive_maximum')
            else:
                if value > cls.maximum:
                    raise TypeSystemError(cls=cls, code='maximum')

        if cls.multiple_of is not None:
            if isinstance(cls.multiple_of, float):
                failed = not (value * (1 / cls.multiple_of)).is_integer()
            else:
                failed = value % cls.multiple_of
            if failed:
                raise TypeSystemError(cls=cls, code='multiple_of')

        # Coerce value to the native type.  We only do this if the value
        # is an instance of the class.
        if isinstance(value, cls):
            value = cls.native_type(value)

        cls.validate(value)
        return value


class Number(_NumericType, float):
    """Represents a `float` type."""
    native_type = float

    @classmethod
    def get_example(cls) -> float:
        """Returns an example value for the Number type."""
        if cls.example is not None:
            return cls.example
        return 3.14


class Integer(_NumericType, int):
    """Represents an `int` type."""
    native_type = int

    @classmethod
    def get_example(cls) -> int:
        """Returns an example value for the Integer type."""
        if cls.example is not None:
            return cls.example
        return 1


class Boolean(SuperType):
    """Represents a `bool` type."""
    native_type = bool
    errors = {
        'type': 'Must be a valid boolean.'
    }

    def __new__(cls, *args, **kwargs) -> bool:
        value = args[0]
        if cls.nullable and value is None:
            return None

        if args and isinstance(value, str):
            try:
                value = {
                    'true': True,
                    'false': False,
                    'on': True,
                    'off': False,
                    '1': True,
                    '0': False,
                    '': False
                }[value.lower()]
            except KeyError:
                raise TypeSystemError(cls=cls, code='type') from None
            cls.validate(value)
            return value

        cls.validate(value)
        return bool(*args, **kwargs)

    @classmethod
    def get_example(cls) -> bool:
        """Returns an example value for the Boolean type."""
        if cls.example is not None:
            return cls.example
        return True


class Enum(SuperType, str):
    """
    Represents a `str` type that must be one of any defined allowed values.
    """
    native_type = str
    errors = {
        'invalid': 'Must be one of: {enum}',
    }
    #: A list of valid values.
    enum = []  # type: typing.List[str]

    #: Indicates if the values of the enum are case insensitive or not.
    case_insensitive = False

    #: If True the input value will be lowercased before validation.
    lowercase_value = False

    #: If True the input value will be uppercased before validation.
    uppercase_value = False

    def __new__(cls, value: typing.Union[None, str]):
        if cls.nullable and value is None:
            return None

        if cls.case_insensitive:
            if cls.uppercase_value:
                cls.enum = [v.upper() for v in cls.enum]
            else:
                cls.enum = [v.lower() for v in cls.enum]
                value = value.lower()
        if cls.lowercase_value:
            value = value.lower()
        if cls.uppercase_value:
            value = value.upper()
        if value not in cls.enum:
            raise TypeSystemError(cls=cls, code='invalid')

        cls.validate(value)
        return value

    @classmethod
    def get_example(cls) -> str:
        """Returns an example value for the Enum type."""
        if cls.example is not None:
            return cls.example
        return cls.enum[0]


class Object(SuperType, dict):
    """Represents a `dict` type."""
    native_type = dict
    errors = {
        'type': 'Must be an object.',
        'invalid_key': 'Object keys must be strings.',
        'required': 'This field is required.',
        'additional_properties': 'Additional properties are not allowed.',
    }
    #: A mapping of property name to expected type.
    properties = {}  # type: typing.Dict[str, typing.Any]
    #: A list of required properties.
    required = []  # type: typing.List[str]
    #: If True additional properties will be allowed, otherwise they will not.
    additional_properties = True  # type: bool
    #: A human readable title for the object.
    title = None
    #: A mapping of property name to a list of other properties it requires
    #: when the property name is present.
    property_dependencies = {}  # type: typing.Dict[str, typing.List[str]]

    def __init__(self, *args, **kwargs):
        if self.nullable and args[0] is None:
            return

        try:
            super().__init__(*args, **kwargs)
        except MissingDescriptionError:
            raise
        except (ValueError, TypeError):
            if (len(args) == 1 and not kwargs and
                    hasattr(args[0], '__dict__')):
                value = dict(args[0].__dict__)
            else:
                raise TypeSystemError(
                    cls=self.__class__, code='type') from None
        value = self

        # Ensure all property keys are strings.
        errors = {}
        if any(not isinstance(key, str) for key in value.keys()):
            raise TypeSystemError(cls=self.__class__, code='invalid_key')

        # Properties
        for key, child_schema in self.properties.items():
            try:
                item = value[key]
            except KeyError:
                if hasattr(child_schema, 'default'):
                    # If a key is missing but has a default, then use that.
                    self[key] = child_schema.default
                elif key in self.required:
                    exc = TypeSystemError(cls=self.__class__, code='required')
                    errors[key] = exc.detail
            else:
                # Coerce value into the given schema type if needed.
                if isinstance(item, child_schema):
                    self[key] = item
                else:
                    try:
                        self[key] = child_schema(item)
                    except TypeSystemError as exc:
                        errors[key] = exc.detail

        # If additional properties are allowed set any other key/value(s) not
        # in the defined properties.
        if self.additional_properties:
            for key, value in value.items():
                if key not in self:
                    self[key] = value

        # Raise an exception if additional properties are defined and
        # not allowed.
        if not self.additional_properties:
            properties = list(self.properties.keys())
            for key in self.keys():
                if key not in properties:
                    detail = '{key} not in {properties}'.format(
                        key=key, properties=properties)
                    exc = TypeSystemError(detail, cls=self.__class__,
                                          code='additional_properties')
                    errors[key] = exc.detail

        # Check for any property dependencies that are defined.
        if self.property_dependencies:
            err = 'Required properties {} for property `{}` are missing.'
            for prop, dependencies in self.property_dependencies.items():
                if prop in self:
                    for dep in dependencies:
                        if dep not in self:
                            raise TypeSystemError(err.format(
                                dependencies, prop))

        if errors:
            raise TypeSystemError(errors)

        self.validate(self.copy())

    @classmethod
    def get_example(cls) -> dict:
        """Returns an example value for the Dict type.

        If an example isn't a defined attribute on the class we return
        a dict of example values based on each property's annotation.
        """
        if cls.example is not None:
            return cls.example
        return {k: v.get_example() for k, v in cls.properties.items()}


class Array(SuperType, list):
    """Represents a `list` type."""
    native_type = list
    errors = {
        'type': 'Must be a list.',
        'min_items': 'Not enough items.',
        'max_items': 'Too many items.',
        'unique_items': 'This item is not unique.',
    }
    #: The type each item should be, or a list of types where the position
    #: of the type in the list represents the type at that position in the
    #: array the item should be.
    items = None  # type: typing.Union[type, typing.List[type]]
    #: If `items` is a list and this is `True` then additional items whose
    #: types aren't defined are allowed in the list.
    additional_items = False  # type: bool
    #: The minimum number of items allowed in the list.
    min_items = 0  # type: typing.Optional[int]
    #: The maxiimum number of items allowed in the list.
    max_items = None  # type: typing.Optional[int]
    #: If `True` items in the array should be unique from one another.
    unique_items = False  # type: bool

    def __init__(self, *args, **kwargs):
        if self.nullable and args[0] is None:
            return

        if args and isinstance(args[0], (str, bytes)):
            raise TypeSystemError(cls=self.__class__, code='type')

        try:
            value = list(*args, **kwargs)
        except TypeError:
            raise TypeSystemError(cls=self.__class__, code='type') from None

        if isinstance(self.items, list) and len(self.items) > 1:
            if len(value) < len(self.items):
                raise TypeSystemError(cls=self.__class__, code='min_items')
            elif len(value) > len(self.items) and not self.additional_items:
                raise TypeSystemError(cls=self.__class__, code='max_items')

        if len(value) < self.min_items:
            raise TypeSystemError(cls=self.__class__, code='min_items')
        elif self.max_items is not None and len(value) > self.max_items:
            raise TypeSystemError(cls=self.__class__, code='max_items')

        # Ensure all items are of the right type.
        errors = {}
        if self.unique_items:
            seen_items = set()

        for pos, item in enumerate(value):
            try:
                if isinstance(self.items, list):
                    if pos < len(self.items):
                        item = self.items[pos](item)
                elif self.items is not None:
                    item = self.items(item)

                if self.unique_items:
                    if item in seen_items:
                        raise TypeSystemError(
                            cls=self.__class__, code='unique_items')
                    else:
                        seen_items.add(item)

                self.append(item)
            except TypeSystemError as exc:
                errors[pos] = exc.detail

        if errors:
            raise TypeSystemError(errors)

        self.validate(value)

    @classmethod
    def get_example(cls) -> list:
        """Returns an example value for the Array type.

        If an example isn't a defined attribute on the class we return
        a list of 1 item containing the example value of the `items` attribute.
        If `items` is None we simply return a `[1]`.
        """
        if cls.example is not None:
            return cls.example
        if cls.items is not None:
            if isinstance(cls.items, list):
                return [item.get_example() for item in cls.items]
            else:
                return [cls.items.get_example()]
        return [1]


class JsonSchema(SuperType):
    """Represents a type loaded from a json schema.

    NOTE: This class should not be used directly.  Instead use
    :func:`~doctor.types.json_schema_type` to create a new class based on
    this one.
    """
    json_type = None
    native_type = None
    #: The loaded ResourceSchema
    schema = None  # type: doctor.resource.ResourceSchema
    #: The full path to the schema file.
    schema_file = None  # type: str
    #: The key from the definitions in the schema file that the type should
    #: come from.
    definition_key = None  # type: str

    def __new__(cls, value):
        # Attempt to parse the value if it came from a query string
        try:
            _, value = parse_value(value, [cls.json_type])
        except ValueError:
            pass
        request_schema = None
        if cls.definition_key is not None:
            params = [cls.definition_key]
            request_schema = cls.schema._create_request_schema(params, params)
            data = {cls.definition_key: value}
        else:
            data = value

        super().__new__(cls)
        # Validate the data against the schema and raise an error if it
        # does not validate.
        validator = cls.schema.get_validator(request_schema)
        try:
            cls.schema.validate(data, validator)
        except SchemaValidationError as e:
            raise TypeSystemError(e.args[0], cls=cls)

        return value

    @classmethod
    def get_example(cls) -> typing.Any:
        """Returns an example value for the JsonSchema type."""
        return cls.example


#: A mapping of json types to native python types.
JSON_TYPES_TO_NATIVE = {
    'array': list,
    'boolean': bool,
    'integer': int,
    'object': dict,
    'number': float,
    'string': str,
}


def get_value_from_schema(schema, definition: dict, key: str,
                          definition_key: str):
    """Gets a value from a schema and definition.

    If the value has references it will recursively attempt to resolve them.

    :param ResourceSchema schema: The resource schema.
    :param dict definition: The definition dict from the schema.
    :param str key: The key to use to get the value from the schema.
    :param str definition_key: The name of the definition.
    :returns: The value.
    :raises TypeSystemError: If the key can't be found in the schema/definition
        or we can't resolve the definition.
    """
    resolved_definition = definition.copy()
    if '$ref' in resolved_definition:
        try:
            # NOTE: The resolve method recursively resolves references, so
            # we don't need to worry about that in this function.
            resolved_definition = schema.resolve(definition['$ref'])
        except SchemaError as e:
            raise TypeSystemError(str(e))
    try:
        value = resolved_definition[key]
    except KeyError:
        # Before raising an error, the resolved definition may have an array
        # or object inside it that needs to be resolved in order to get
        # values.  Attempt that here and then fail if we still can't find
        # the key we are looking for.

        # If the key was missing and this is an array, try to resolve it
        # from the items key.
        if resolved_definition['type'] == 'array':
            return [
                get_value_from_schema(schema, resolved_definition['items'], key,
                                      definition_key)
            ]
        # If the key was missing and this is an object, resolve it from it's
        # properties.
        elif resolved_definition['type'] == 'object':
            value = {}
            for prop, definition in resolved_definition['properties'].items():
                value[prop] = get_value_from_schema(
                    schema, definition, key, definition_key)
            return value
        raise TypeSystemError(
            'Definition `{}` is missing a {}.'.format(
                definition_key, key))
    return value


def get_types(json_type: StrOrList) -> typing.Tuple[str, str]:
    """Returns the json and native python type based on the json_type input.

    If json_type is a list of types it will return the first non 'null' value.

    :param json_type: A json type or a list of json types.
    :returns: A tuple containing the json type and native python type.
    """
    # If the type is a list, use the first non 'null' value as the type.
    if isinstance(json_type, list):
        for j_type in json_type:
            if j_type != 'null':
                json_type = j_type
                break
    return (json_type, JSON_TYPES_TO_NATIVE[json_type])


def json_schema_type(schema_file: str, **kwargs) -> typing.Type:
    """Create a :class:`~doctor.types.JsonSchema` type.

    This function will automatically load the schema and set it as an attribute
    of the class along with the description and example.

    :param schema_file: The full path to the json schema file to load.
    :param kwargs: Can include any attribute defined in
        :class:`~doctor.types.JsonSchema`
    """
    # Importing here to avoid circular dependencies
    from doctor.resource import ResourceSchema
    schema = ResourceSchema.from_file(schema_file)
    kwargs['schema'] = schema

    # Look up the description, example and type in the schema.
    definition_key = kwargs.get('definition_key')
    if definition_key:
        params = [definition_key]
        request_schema = schema._create_request_schema(params, params)
        try:
            definition = request_schema['definitions'][definition_key]
        except KeyError:
            raise TypeSystemError(
                'Definition `{}` is not defined in the schema.'.format(
                    definition_key))
        description = get_value_from_schema(
            schema, definition, 'description', definition_key)
        example = get_value_from_schema(
            schema, definition, 'example', definition_key)
        json_type = get_value_from_schema(
            schema, definition, 'type', definition_key)
        json_type, native_type = get_types(json_type)
        kwargs['description'] = description
        kwargs['example'] = example
        kwargs['json_type'] = json_type
        kwargs['native_type'] = native_type
    else:
        try:
            kwargs['description'] = schema.schema['description']
        except KeyError:
            raise TypeSystemError('Schema is missing a description.')
        try:
            json_type = schema.schema['type']
        except KeyError:
            raise TypeSystemError('Schema is missing a type.')
        json_type, native_type = get_types(json_type)
        kwargs['json_type'] = json_type
        kwargs['native_type'] = native_type
        try:
            kwargs['example'] = schema.schema['example']
        except KeyError:
            # Attempt to load from properties, if defined.
            if schema.schema.get('properties'):
                example = {}
                for prop, definition in schema.schema['properties'].items():
                    example[prop] = get_value_from_schema(
                        schema, definition, 'example', 'root')
                kwargs['example'] = example
            else:
                raise TypeSystemError('Schema is missing an example.')

    return type('JsonSchema', (JsonSchema,), kwargs)


def string(description: str, **kwargs) -> Any:
    """Create a :class:`~doctor.types.String` type.

    :param description: A description of the type.
    :param kwargs: Can include any attribute defined in
        :class:`~doctor.types.String`
    """
    kwargs['description'] = description
    return type('String', (String,), kwargs)


def integer(description, **kwargs) -> Any:
    """Create a :class:`~doctor.types.Integer` type.

    :param description: A description of the type.
    :param kwargs: Can include any attribute defined in
        :class:`~doctor.types.Integer`
    """
    kwargs['description'] = description
    return type('Integer', (Integer,), kwargs)


def number(description, **kwargs) -> Any:
    """Create a :class:`~doctor.types.Number` type.

    :param description: A description of the type.
    :param kwargs: Can include any attribute defined in
        :class:`~doctor.types.Number`
    """
    kwargs['description'] = description
    return type('Number', (Number,), kwargs)


def boolean(description, **kwargs) -> Any:
    """Create a :class:`~doctor.types.Boolean` type.

    :param description: A description of the type.
    :param kwargs: Can include any attribute defined in
        :class:`~doctor.types.Boolean`
    """
    kwargs['description'] = description
    return type('Boolean', (Boolean,), kwargs)


def enum(description, **kwargs) -> Any:
    """Create a :class:`~doctor.types.Enum` type.

    :param description: A description of the type.
    :param kwargs: Can include any attribute defined in
        :class:`~doctor.types.Enum`
    """
    kwargs['description'] = description
    return type('Enum', (Enum,), kwargs)


def array(description, **kwargs) -> Any:
    """Create a :class:`~doctor.types.Array` type.

    :param description: A description of the type.
    :param kwargs: Can include any attribute defined in
        :class:`~doctor.types.Array`
    """
    kwargs['description'] = description
    return type('Array', (Array,), kwargs)


def new_type(cls, **kwargs) -> Any:
    """Create a user defined type.

    The new type will contain all attributes of the `cls` type passed in.
    Any attribute's value can be overwritten using kwargs.

    :param kwargs: Can include any attribute defined in
        the provided user defined type.
    """
    props = dict(cls.__dict__)
    props.update(kwargs)
    return type(cls.__name__, (cls,), props)
