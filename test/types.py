"""
This module contains custom types used by tests.
"""
from doctor.types import (
    array, boolean, enum, integer, new_type, number, string, Object, UnionType)


def parse_comma_separated_str(value):
    return value.split(',')


Age = integer('age', minimum=1, maximum=120, example=34)
Auth = string('auth token', example='testtoken')
Color = enum('Color', enum=['blue', 'green'], example='blue',
             case_insensitive=True)
Colors = array('colors', items=Color, example=['green'])
ExampleArray = array('ex description e', items=Auth, example=['ex', 'array'])
TwoItems = array('two items', items=[Age, Color])


class ExampleObject(Object):
    description = 'ex description f'
    properties = {'str': Auth}
    additional_properties = False
    example = {'str': 'ex str'}


ExampleObjects = array(
    'ex objects', items=ExampleObject, example=[{'str': 'e'}])
ExampleObjectsAndAge = array(
    'ex obj and age', items=[Age, ExampleObject])
Foo = string('foo', example='foo')
FooId = integer('foo id', example=1)
Foos = array('foos', items=Foo, example=['foo'])
FoosWithParser = array('foos with parser', items=Foo,
                       parser=parse_comma_separated_str)
IsAlive = boolean('Is alive?', example=True)
ItemId = integer('item id', minimum=1, example=1, nullable=True)
Item = new_type(Object, description='item', properties={'item_id': ItemId},
                additional_properties=False, required=['item_id'],
                example={'item_id': 1})
IncludeDeleted = boolean('indicates if deleted items should be included.',
                         example=False)
IsDeleted = boolean('Indicates if the item should be marked as deleted',
                    example=False)
Latitude = number('The latitude.', example=44.322804,
                  param_name='location.lat', nullable=True)
Longitude = number('the longitude.', example=-122.34232,
                   param_name='locationLon', nullable=True)
Name = string('name', min_length=1, example='John')
OptIn = boolean('If the user has opted in to gps tracking.',
                param_name='opt-in')


class FooInstance(Object):
    description = 'An instance of foo.'
    properties = {
        'foo': Foo,
        'foo_id': FooId,
    }
    required = ['foo_id']


class AgeOrColor(UnionType):
    description = 'age or color'
    types = [Age, Color]


class ColorsOrObject(UnionType):
    description = 'Colors or an example object.'
    types = [Colors, ExampleObject]
