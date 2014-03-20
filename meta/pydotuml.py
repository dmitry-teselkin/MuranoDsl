#!/usr/bin/python

__author__ = 'dim'

import os
import pydot
import yaml
import argparse
import re


# Workaround for unknown yaml tags
def yaml_default_ctor(loader, tag_suffix, node):
    return tag_suffix + ' ' + node.value

yaml.add_multi_constructor('', yaml_default_ctor)


class UmlClassAttribute():
    def __init__(self, name, type='Private', classname='Void', formatter=None):
        self.formatter = formatter if formatter else self._formatter
        (self.name, self.type, self.classname) = (name, type, classname)

    def _formatter(self, name, type, classname):
        return '{2} {1}: {3}', name, type.capitalize(), classname.capitalize()

    def __str__(self):
        t = self.formatter(name=self.name, type=self.type, classname=self.classname)
        return t[0].format(*t)


class UmlClassOperation():
    def __init__(self, name, formatter=None):
        self.formatter = formatter if formatter else self._formatter
        self.name = name

    def _formatter(self, name):
        return '{1}()', name

    def __str__(self):
        t = self.formatter(self.name)
        return t[0].format(*t)


class UmlClassExtra():
    def __init__(self, key, value, formatter=None):
        self.formatter = formatter if formatter else self._formatter
        self.key = key
        self.value = value

    def _formatter(self, key, value):
        return '{1}: {2}', key, value

    def __str__(self):
        t = self.formatter(self.key, self.value)
        return t[0].format(*t)


class UmlClassNode():
    def __init__(self, node_dn, label):
        self.node_dn = node_dn
        self.node_id = self.node_dn.replace('.', '_')
        self.label = label
        self.attributes = []
        self.attributes_formatter = None
        self.operations = []
        self.operations_formatter = None
        self.extras = []
        self.extras_formatter = None

    def set_attributes_formatter(self, func):
        self.attributes_formatter = func

    def add_attribute(self, name, type='In', classname='String'):
        self.attributes.append(UmlClassAttribute(
            name, type=type, classname=classname, formatter=self.attributes_formatter))

    def set_operations_formatter(self, func):
        self.operations_formatter = func

    def add_operation(self, name):
        self.operations.append(UmlClassOperation(name))

    def set_extras_formatter(self, func):
        self.extras_formatter = func

    def add_extra(self, key, value):
        self.extras.append(UmlClassExtra(key, value, formatter=self.extras_formatter))

    def draw(self, graph):
        label = "{%s|{%s}|{%s}|%s}" % (
                self.label,
                '\n'.join([str(x) for x in self.attributes]),
                '\n'.join([str(x) for x in self.operations]),
                '\n'.join([str(x) for x in self.extras])
            )
        graph.add_node(pydot.Node(
            self.node_id,
            shape='record',
            fontname='Courier',
            label=label
        ))


class UmlRelationship():
    _relationship_types = {
        'default': {
            'style': 'solid',
            'arrowhead': 'normal', 'arrowtail': 'dot',
            'headport': 'n', 'tailport': 's'
        },
        'dependency': {
            'style': 'dashed',
            'arrowhead': 'open', 'arrowtail': 'dot',
            'headport': 'e', 'tailport': 'w'
        },
        'association': {
            'style': 'dashed',
            'arrowhead': 'normal', 'arrowtail': 'dot',
            'headport': 'n', 'tailport': 's'
        },
        'generalization': {
            'style': 'solid',
            'arrowhead': 'onormal', 'arrowtail': 'dot',
            'headport': 'n', 'tailport': 's'
        },
        'realization': {
            'style': 'dotted',
            'arrowhead': 'onormal', 'arrowtail': 'dot',
            'headport': 'n', 'tailport': 's'
        }
    }

    def __init__(self, id_from, id_to, type='generalization'):
        #print "id_from = '%s'" % id_from
        #print "id_to = '%s'" % id_to
        self.id_from = id_from.replace('.', '_')
        self.id_to = id_to.replace('.', '_')
        self.set_type(type)

    def set_type(self, type='generalization'):
        if type in self._relationship_types.keys():
            self.type = type
        else:
            self.type = 'default'

    def draw(self, graph):
        graph.add_edge(pydot.Edge(
            self.id_to,
            self.id_from,
            dir='back',
            headport=self._relationship_types[self.type]['headport'],
            tailport=self._relationship_types[self.type]['tailport'],
            arrowhead=self._relationship_types[self.type]['arrowhead'],
            arrowtail=self._relationship_types[self.type]['arrowhead'],
            style=self._relationship_types[self.type]['style']
        ))


class DslSpec():
    def __init__(self, class_dn, basepath='.'):
        self._dn = class_dn
        self._id = self._dn.replace('.', '_')
        self._name = self._dn.split('.')[-1]
        self._ns = ('=', self._dn.split('.')[:-1])
        self._graph = None
        self.is_virtual = True
        self.parent_dn = None
        self.manifest = None

        manifest_path = os.path.join(basepath, self._dn, 'manifest.yaml')
        if os.path.exists(manifest_path):
            self.manifest = yaml.load(open(manifest_path))

        if self.manifest:
            self.is_virtual = False
            self.name = self.manifest['Name']
            if 'Extends' in self.manifest:
                self.parent_dn = self.get_dn(self.manifest['Extends'])

    def get_ns(self, name=None):
        #print "get_ns(%s)" % name
        if name:
            parts = name.split(':')
            if len(parts) == 1:
                parts.insert(0, '=')
        else:
            parts = ['=', self._name]
        return {'key': parts[0], 'value': self.manifest['Namespaces'][parts[0]]}

    def get_dn(self, name=None):
        #print "get_dn(%s)" % name
        if name:
            parts = name.split(':')
            #print parts
            if len(parts) == 1:
                parts.insert(0, '=')
        else:
            parts = ['=', self._name]
        parts[0] = self.get_ns(parts[0] + ':')['value']
        return '.'.join(parts)

    def get_name(self):
        return self._name

    def draw(self, graph):
        self._graph = graph
        uml_class = UmlClassNode(self._dn, self._name)
        uml_class.attributes_formatter = dsl_class_attributes_formatter
        ext_classes = []
        if not self.is_virtual:
            namespaces = [self.get_ns(), ]
            if 'Properties' in self.manifest.keys():
                for item in self.manifest['Properties']:
                    item_type = self.manifest['Properties'][item].get('Type', 'In')
                    item_contract = str(self.manifest['Properties'][item].get('Contract', 'UNDEFINED'))
                    match = re.search('class\((.*?)\)', item_contract)
                    if match:
                        ns = self.get_ns(match.group(1))
                        ext_classes.append(self.get_dn(match.group(1)))
                        if not ns in namespaces:
                            namespaces.append(ns)
                    uml_class.add_attribute(item, type=item_type, classname=item_contract)
            if 'Workflow' in self.manifest.keys():
                for m in self.manifest['Workflow']:
                    uml_class.add_operation(m)
            for ns in namespaces:
                uml_class.add_extra(ns['key'], ns['value'])
        uml_class.draw(graph)
        return ext_classes


def dsl_class_attributes_formatter(name, type='In', classname='String'):
    type_icons = {
        'In': '--\>',
        'Out': '\<--',
        'Inout': '\<-\>',
        'Runtime': '-R-',
        'Const': '-C-',
    }

    type = type.capitalize()

    if not type in type_icons.keys():
        raise Exception("Wrong attribute type '%s'" % type)

    return '\<{2}\> {1}: {3}', name, type, classname


graph_edges = []


def add_graph_edge(from_node, to_node, type):
    edge = {'from_node': from_node, 'to_node': to_node, 'type': type}
    #print edge
    if not edge in graph_edges:
        graph_edges.append(edge)


def draw_structure(classname, graph, level=0):
    #print "draw_structure for '%s'" % classname
    if level == 0:
        print "Drawing dependency graph for '%s'" % classname
    thing = DslSpec(classname)
    ext_classes = thing.draw(graph)
    for ext_class in ext_classes:
        add_graph_edge(from_node=classname, to_node=ext_class, type='dependency')
        draw_structure(ext_class, graph, level + 1)
    if thing.is_virtual:
        #print "'%s' is virtual" % classname
        return
    if thing.parent_dn:
        #print "'%s' has parent '%s'" % (classname, thing.parent_dn)
        if graph.get_node(thing.parent_dn):
            print "Node '%s' already exists." % thing.parent_dn
        else:
            add_graph_edge(from_node=classname, to_node=thing.parent_dn, type='generalization')
            draw_structure(thing.parent_dn, graph, level + 1)

    if level == 0:
        for edge in graph_edges:
            UmlRelationship(edge['from_node'], edge['to_node'], edge['type']).draw(graph)


parser = argparse.ArgumentParser(description='Qwerty')
parser.add_argument(
    'classname',
    default='com.mirantis.murano.demoApp.DemoHost',
    help='Dsl Class Name to draw.', nargs='?'
)
args = parser.parse_args()

graph = pydot.Dot(graph_type='digraph')

draw_structure(args.classname, graph)

graph.write_png('{0}.png'.format(args.classname))
graph.write('{0}.txt'.format(args.classname))
os.system('xdg-open {0}.png'.format(args.classname))


