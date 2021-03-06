import types
import sys
import uuid
import helpers
import murano_object
from yaql_expression import YaqlExpression
from yaql.context import Context, EvalArg

NoValue = object()


class TypeScheme(object):
    class ObjRef(object):
        def __init__(self, object_id):
            self.object_id = object_id

    def __init__(self, spec):
        self._spec = spec

    @staticmethod
    def prepare_context(root_context, this, object_store,
                        namespace_resolver, default):
        def _int(value):
            value = value()
            if value is NoValue:
                value = default
            if value is None:
                return None
            try:
                return int(value)
            except Exception:
                raise TypeError()

        def _string(value):
            value = value()
            if value is NoValue:
                value = default
            if value is None:
                return None
            try:
                return unicode(value)
            except Exception:
                raise TypeError()

        def _bool(value):
            value = value()
            if value is NoValue:
                value = default
            if value is None:
                return None
            return True if value else False

        def _not_null(value):
            value = value()

            if isinstance(value, TypeScheme.ObjRef):
                return value

            if value is None:
                raise TypeError()
            return value

        def _error():
            raise TypeError()

        def _check(value, predicate):
            value = value()
            if isinstance(value, TypeScheme.ObjRef) or predicate(value):
                return value
            else:
                raise TypeError(value)

        @EvalArg('obj', arg_type=(murano_object.MuranoObject,
                                  TypeScheme.ObjRef, types.NoneType))
        def _owned(obj):
            if isinstance(obj, TypeScheme.ObjRef):
                return obj

            if obj is None:
                return None
            elif obj.parent is this:
                return obj
            else:
                raise TypeError()

        @EvalArg('obj', arg_type=(murano_object.MuranoObject,
                                  TypeScheme.ObjRef, types.NoneType))
        def _not_owned(obj):
            if isinstance(obj, TypeScheme.ObjRef):
                return obj

            if obj is None:
                return None
            elif obj.parent is this:
                raise TypeError()
            else:
                return obj

        @EvalArg('name', arg_type=str)
        def _class(value, name):
            return _class2(value, name, None)

        @EvalArg('name', arg_type=str)
        @EvalArg('default_name', arg_type=(str, types.NoneType))
        def _class2(value, name, default_name):
            name = namespace_resolver.resolve_name(name)
            if not default_name:
                default_name = name
            else:
                default_name = namespace_resolver.resolve_name(default_name)
            value = value()
            if value is NoValue:
                value = default
                if isinstance(default, types.DictionaryType):
                    value = {'?': {
                        'id': uuid.uuid4().hex,
                        'type': default_name
                    }}
            class_loader = helpers.get_class_loader(root_context)
            murano_class = class_loader.get_class(name)
            if not murano_class:
                raise TypeError()
            if value is None:
                return None
            if isinstance(value, murano_object.MuranoObject):
                obj = value
            elif isinstance(value, types.DictionaryType):
                obj = object_store.load(value, this, root_context,
                                        defaults=default)
            elif isinstance(value, types.StringTypes):
                obj = object_store.get(value)
                if obj is None:
                    if not object_store.initializing:
                        raise TypeError('Object %s not found' % value)
                    else:
                        return TypeScheme.ObjRef(value)
            else:
                raise TypeError()
            if not murano_class.is_compatible(obj):
                raise TypeError()
            return obj

        @EvalArg('prefix', str)
        @EvalArg('name', str)
        def _validate(prefix, name):
            return namespace_resolver.resolve_name(
                '%s:%s' % (prefix, name))

        context = Context(parent_context=root_context)
        context.register_function(_validate, '#validate')
        context.register_function(_int, 'int')
        context.register_function(_string, 'string')
        context.register_function(_bool, 'bool')
        context.register_function(_check, 'check')
        context.register_function(_not_null, 'notNull')
        context.register_function(_error, 'error')
        context.register_function(_class, 'class')
        context.register_function(_class2, 'class')
        context.register_function(_owned, 'owned')
        context.register_function(_not_owned, 'notOwned')
        return context


    def _map_dict(self, data, spec, context):
        if data is None or data is NoValue:
            data = {}
        if not isinstance(data, types.DictionaryType):
            raise TypeError()
        if not spec:
            return data
        result = {}
        yaql_key = None
        for key, value in spec.iteritems():
            if isinstance(key, YaqlExpression):
                if yaql_key is not None:
                    raise SyntaxError()
                else:
                    yaql_key = key
            else:
                result[key] = self._map(data.get(key), value, context)

        if yaql_key is not None:
            yaql_value = spec[yaql_key]
            for key, value in data.iteritems():
                if key in result:
                    continue
                result[self._map(key, yaql_key, context)] = \
                    self._map(value, yaql_value, context)

        return result

    def _map_list(self, data, spec, context):
        if not isinstance(data, types.ListType):
            if data is None or data is NoValue:
                data = []
            else:
                data = [data]
        if len(spec) < 1:
            return data
        result = []
        shift = 0
        max_length = sys.maxint
        min_length = 0
        if isinstance(spec[-1], types.IntType):
            min_length = spec[-1]
            shift += 1
        if len(spec) >= 2 and isinstance(spec[-2], types.IntType):
            max_length = min_length
            min_length = spec[-2]
            shift += 1

        if not min_length <= len(data) <= max_length:
            raise TypeError()

        for index, item in enumerate(data):
            spec_item = spec[-1 - shift] \
                if index >= len(spec) - shift else spec[index]
            result.append(self._map(item, spec_item, context))
        return result

    def _map_scalar(self, data, spec):
        if data != spec:
            raise TypeError()
        else:
            return data

    def _map(self, data, spec, context):
        child_context = Context(parent_context=context)
        if isinstance(spec, YaqlExpression):
            child_context.set_data(data)
            return spec.evaluate(context=child_context)
        elif isinstance(spec, types.DictionaryType):
            return self._map_dict(data, spec, child_context)
        elif isinstance(spec, types.ListType):
            return self._map_list(data, spec, child_context)
        elif isinstance(spec, (types.IntType,
                               types.StringTypes,
                               types.NoneType)):
            return self._map_scalar(data, spec)

    def __call__(self, data, context, this, object_store,
                 namespace_resolver, default):
        context = self.prepare_context(
            context, this, object_store, namespace_resolver,
            default)
        result = self._map(data, self._spec, context)
        if result is NoValue:
            raise TypeError('No type specified')
        return result
